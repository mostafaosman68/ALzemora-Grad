"""
Medication scheduler — runs as a background asyncio task.
Every 60 seconds it checks all active medications whose schedule matches the
current local time. When a match is found it:
  1. Creates a medication_due alert in the `alerts` collection.
  2. Flips system_state.mode to "medscan" so the Pi coordinator switches cameras.
  3. Sends FCM push notifications to the patient and all linked helpers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId

logger = logging.getLogger(__name__)

# Prevent the same medication from firing more than once per 5-minute window
_FIRED_CACHE: dict[str, float] = {}
REFIRE_COOLDOWN_SECONDS = 300

_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _time_matches(schedule: dict, now: datetime) -> bool:
    """Return True if the medication schedule matches the current local minute."""
    if not isinstance(schedule, dict):
        return False

    days: list = schedule.get("days") or []
    if days:
        today_short = _WEEKDAY_SHORT[now.weekday()]
        if today_short not in days:
            return False

    hour: Optional[int] = None
    minute: int = 0

    raw_hour = schedule.get("hour")
    raw_minute = schedule.get("minute")

    if raw_hour is not None:
        try:
            hour = int(raw_hour)
            minute = int(raw_minute or 0)
        except (TypeError, ValueError):
            hour = None

    if hour is None:
        time_str: str = schedule.get("time") or ""
        if time_str:
            try:
                parts = time_str.strip().split()
                hm = parts[0].split(":")
                h = int(hm[0])
                m = int(hm[1]) if len(hm) > 1 else 0
                if len(parts) > 1:
                    period = parts[1].upper()
                    if period == "PM" and h != 12:
                        h += 12
                    elif period == "AM" and h == 12:
                        h = 0
                hour, minute = h, m
            except Exception:
                return False

    if hour is None:
        return False

    # Apply AM/PM from separate field if present
    period: str = str(schedule.get("period") or "").upper()
    if period == "PM" and hour != 12:
        hour += 12
    elif period == "AM" and hour == 12:
        hour = 0

    return now.hour == hour and now.minute == minute


async def _set_system_mode(
    db,
    patient_id: str,
    mode: str,
    medication_id: Optional[str] = None,
    medication_name: Optional[str] = None,
) -> None:
    doc = {
        "patient_id": patient_id,
        "mode": mode,
        "pending_medication_id": medication_id,
        "pending_medication_name": medication_name,
        "mode_changed_at": datetime.utcnow(),
    }
    await db.system_state.update_one(
        {"patient_id": patient_id},
        {"$set": doc},
        upsert=True,
    )


async def _collect_fcm_tokens(db, patient_id: str) -> list[str]:
    """Collect FCM tokens for the patient and all linked helpers."""
    from app.services.heartbeat_service import find_notifiable_helpers

    tokens: list[str] = []

    # Patient token
    try:
        patient = await db.users.find_one({"_id": ObjectId(patient_id)})
        if patient and patient.get("fcm_token"):
            tokens.append(patient["fcm_token"])
    except Exception as exc:
        logger.warning("[SCHEDULER] Could not fetch patient FCM token: %s", exc)

    # Helper tokens — try users collection first, then role-specific collections
    try:
        helpers = await find_notifiable_helpers(db, patient_id)
        for helper in helpers:
            helper_id = helper.get("helper_id")
            if not helper_id:
                continue
            token: Optional[str] = None
            # Try users collection
            user_doc = await db.users.find_one({"_id": ObjectId(helper_id)})
            if user_doc:
                token = user_doc.get("fcm_token")
            # Fallback to role-specific collections
            if not token:
                for coll_name in ("guardians", "caregivers"):
                    coll = getattr(db, coll_name, None)
                    if coll is None:
                        continue
                    doc = await coll.find_one({"_id": ObjectId(helper_id)})
                    if doc and doc.get("fcm_token"):
                        token = doc["fcm_token"]
                        break
            if token:
                tokens.append(token)
    except Exception as exc:
        logger.warning("[SCHEDULER] Could not collect helper FCM tokens: %s", exc)

    return tokens


async def _send_medication_fcm(
    db,
    patient_id: str,
    med_name: str,
    alert_id: str,
    medication_id: str,
) -> None:
    from app.services.firebase_service import send_push_notification

    tokens = await _collect_fcm_tokens(db, patient_id)
    title = "Medication Reminder"
    body = f"Time to take {med_name}"
    data = {
        "alert_type": "medication_due",
        "alert_id": alert_id,
        "patient_id": patient_id,
        "medication_id": medication_id,
        "medication_name": med_name,
    }
    for token in tokens:
        try:
            await send_push_notification(token, title, body, data, priority="high")
        except Exception as exc:
            logger.warning("[SCHEDULER] FCM send failed for token %s…: %s", token[:12], exc)


async def check_due_medications() -> None:
    """Check all active medications; fire alerts for those due right now."""
    from app.database import get_db

    db = get_db()
    if db is None:
        return

    now = datetime.now()  # local time — schedules are stored in local time

    async for med in db.medications.find({"is_active": True}):
        schedule = med.get("schedule")
        if not _time_matches(schedule, now):
            continue

        med_id = str(med["_id"])
        patient_id = med.get("patient_id")
        if not patient_id:
            continue

        # Cooldown guard — don't fire the same med twice within 5 minutes
        last_fired = _FIRED_CACHE.get(med_id, 0.0)
        if (now.timestamp() - last_fired) < REFIRE_COOLDOWN_SECONDS:
            continue

        _FIRED_CACHE[med_id] = now.timestamp()
        med_name: str = med.get("name") or "medication"
        logger.info("[SCHEDULER] Due: '%s' for patient %s", med_name, patient_id)

        # 1. Create alert document
        alert_doc = {
            "patient_id": patient_id,
            "alert_type": "medication_due",
            "medication_id": med_id,
            "medication_name": med_name,
            "message": f"Time to take {med_name}",
            "created_at": datetime.utcnow(),
            "read": False,
        }
        result = await db.alerts.insert_one(alert_doc)
        alert_id = str(result.inserted_id)

        # 2. Flip system mode → medscan
        await _set_system_mode(db, patient_id, "medscan", med_id, med_name)

        # 3. Push notifications
        try:
            await _send_medication_fcm(db, patient_id, med_name, alert_id, med_id)
        except Exception as exc:
            logger.error("[SCHEDULER] Notification error: %s", exc)


async def run_medication_scheduler() -> None:
    """Infinite background loop — runs check_due_medications every 60 seconds."""
    logger.info("[SCHEDULER] Medication scheduler started")
    while True:
        try:
            await check_due_medications()
        except Exception as exc:
            logger.error("[SCHEDULER] Unexpected error: %s", exc)
        await asyncio.sleep(60)
