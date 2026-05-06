from datetime import datetime
from copy import deepcopy
from typing import Any

from bson import ObjectId




DEFAULT_HEART_RATE_THRESHOLD = 120
DEFAULT_SENSOR_STALE_SECONDS = 10


def normalize_patient_links(helper_account: dict[str, Any]) -> list[dict[str, str]]:
    links = helper_account.get("patient_links")
    normalized: list[dict[str, str]] = []

    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue

            patient_id = link.get("patient_id")
            if patient_id:
                normalized.append(
                    {
                        "patient_id": str(patient_id),
                        "patient_name": link.get("patient_name"),
                    }
                )

    legacy_patient_id = helper_account.get("patient_id")
    if legacy_patient_id:
        legacy_link = {
            "patient_id": str(legacy_patient_id),
            "patient_name": helper_account.get("patient_name"),
        }
        if not any(link["patient_id"] == legacy_link["patient_id"] for link in normalized):
            normalized.append(legacy_link)

    return normalized


async def find_notifiable_helpers(db, patient_id: str) -> list[dict[str, str]]:
    recipients: list[dict[str, str]] = []

    for collection_name, role in (("guardians", "Guardian"), ("caregivers", "CareGiver")):
        collection = getattr(db, collection_name, None)
        if collection is None:
            continue

        async for helper_account in collection.find({}):
            links = normalize_patient_links(helper_account)
            if any(link.get("patient_id") == patient_id for link in links):
                recipients.append(
                    {
                        "helper_id": str(helper_account.get("_id")),
                        "helper_name": helper_account.get("full_name"),
                        "role": role,
                    }
                )

    return recipients


async def evaluate_heartbeat(db, patient_id: str, heart_rate: int, threshold: int | None = None):
    effective_threshold = threshold or DEFAULT_HEART_RATE_THRESHOLD
    alert_triggered = heart_rate >= effective_threshold

    recipients = []
    alert_record = None

    if alert_triggered:
        recipients = await find_notifiable_helpers(db, patient_id)
        alert_record = {
            "patient_id": patient_id,
            "heart_rate": heart_rate,
            "threshold": effective_threshold,
            "triggered_at": datetime.utcnow(),
            "recipients": recipients,
            "status": "triggered",
        }

        alerts_collection = getattr(db, "heartbeat_alerts", None)
        if alerts_collection is not None:
            await alerts_collection.insert_one(alert_record)

    return {
        "patient_id": patient_id,
        "heart_rate": heart_rate,
        "threshold": effective_threshold,
        "alert_triggered": alert_triggered,
        "recipients": recipients,
        "alert_record": alert_record,
    }


def _build_latest_snapshot(patient_id: str, heart_rate: int, threshold: int, evaluation: dict[str, Any], source: str):
    now = datetime.utcnow()
    status = "alert_triggered" if evaluation.get("alert_triggered") else "live"

    return {
        "patient_id": patient_id,
        "heart_rate": heart_rate,
        "threshold": threshold,
        "status": status,
        "alert_triggered": bool(evaluation.get("alert_triggered")),
        "recipients": evaluation.get("recipients", []),
        "source": source,
        "recorded_at": now,
        "updated_at": now,
    }


def _to_json_safe(value: Any):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    return value


def _strip_mongo_id_fields(value: Any):
    if isinstance(value, list):
        return [_strip_mongo_id_fields(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _strip_mongo_id_fields(item)
            for key, item in value.items()
            if str(key) != "_id"
        }
    return value


async def record_heartbeat_sample(
    db,
    patient_id: str,
    heart_rate: int,
    threshold: int | None = None,
    source: str = "sensor",
):
    effective_threshold = threshold or DEFAULT_HEART_RATE_THRESHOLD
    evaluation = await evaluate_heartbeat(db, patient_id, heart_rate, threshold=effective_threshold)
    latest_snapshot = _build_latest_snapshot(patient_id, heart_rate, effective_threshold, evaluation, source)

    reading_doc = {
        "patient_id": latest_snapshot["patient_id"],
        "heart_rate": latest_snapshot["heart_rate"],
        "threshold": latest_snapshot["threshold"],
        "status": latest_snapshot["status"],
        "alert_triggered": latest_snapshot["alert_triggered"],
        "recipients": deepcopy(latest_snapshot.get("recipients", [])),
        "source": latest_snapshot["source"],
        "recorded_at": latest_snapshot["recorded_at"],
        "updated_at": latest_snapshot["updated_at"],
    }

    latest_doc = {
        "patient_id": latest_snapshot["patient_id"],
        "heart_rate": latest_snapshot["heart_rate"],
        "threshold": latest_snapshot["threshold"],
        "status": latest_snapshot["status"],
        "alert_triggered": latest_snapshot["alert_triggered"],
        "recipients": deepcopy(latest_snapshot.get("recipients", [])),
        "source": latest_snapshot["source"],
        "recorded_at": latest_snapshot["recorded_at"],
        "updated_at": latest_snapshot["updated_at"],
    }

    reading_doc = _strip_mongo_id_fields(reading_doc)
    latest_doc = _strip_mongo_id_fields(latest_doc)

    readings_collection = getattr(db, "heartbeat_readings", None)
    if readings_collection is not None:
        try:
            await readings_collection.insert_one(reading_doc)
        except Exception as exc:
            raise RuntimeError(f"heartbeat_readings insert failed: {exc}") from exc

    latest_collection = getattr(db, "heartbeat_latest", None)
    if latest_collection is not None:
        try:
            await latest_collection.update_one(
                {"patient_id": patient_id},
                {"$set": latest_doc},
                upsert=True,
            )
        except Exception as exc:
            raise RuntimeError(f"heartbeat_latest update failed: {exc}") from exc

    users_collection = getattr(db, "users", None)
    if users_collection is not None:
        heartbeat_state = _strip_mongo_id_fields(
            {
                "heart_rate": heart_rate,
                "threshold": effective_threshold,
                "status": latest_snapshot["status"],
                "alert_triggered": latest_snapshot["alert_triggered"],
                "source": source,
                "recorded_at": latest_snapshot["recorded_at"],
                "updated_at": latest_snapshot["updated_at"],
            }
        )
        try:
            await users_collection.update_one(
                {"_id": ObjectId(patient_id)},
                {"$set": {"heartbeat_state": heartbeat_state}},
            )
        except Exception as exc:
            raise RuntimeError(f"users heartbeat_state update failed: {exc}") from exc

    return {
        **evaluation,
        "status": latest_snapshot["status"],
        "source": source,
        "recorded_at": latest_snapshot["recorded_at"],
        "updated_at": latest_snapshot["updated_at"],
    }


async def get_latest_heartbeat_state(db, patient_id: str, stale_after_seconds: int = DEFAULT_SENSOR_STALE_SECONDS):
    latest_collection = getattr(db, "heartbeat_latest", None)
    latest = None

    if latest_collection is not None:
        latest = await latest_collection.find_one({"patient_id": patient_id})

    if latest is None:
        readings_collection = getattr(db, "heartbeat_readings", None)
        if readings_collection is not None:
            latest = await readings_collection.find_one(
                {"patient_id": patient_id},
                sort=[("recorded_at", -1)],
            )

    if latest is None:
        return {
            "patient_id": patient_id,
            "sensor_connected": False,
            "status": "no_data",
            "heart_rate": None,
            "threshold": DEFAULT_HEART_RATE_THRESHOLD,
            "alert_triggered": False,
            "last_seen_at": None,
            "last_seen_seconds_ago": None,
            "source": None,
        }

    recorded_at = latest.get("recorded_at") or latest.get("updated_at")
    seconds_ago = None
    sensor_connected = False

    if isinstance(recorded_at, datetime):
        seconds_ago = max(int((datetime.utcnow() - recorded_at).total_seconds()), 0)
        sensor_connected = seconds_ago <= stale_after_seconds

    status = latest.get("status") or ("live" if sensor_connected else "stale")

    return {
        "patient_id": patient_id,
        "sensor_connected": sensor_connected,
        "status": status,
        "heart_rate": latest.get("heart_rate"),
        "threshold": latest.get("threshold", DEFAULT_HEART_RATE_THRESHOLD),
        "alert_triggered": bool(latest.get("alert_triggered")),
        "last_seen_at": recorded_at,
        "last_seen_seconds_ago": seconds_ago,
        "source": latest.get("source"),
        "latest_reading": _to_json_safe(latest),
    }