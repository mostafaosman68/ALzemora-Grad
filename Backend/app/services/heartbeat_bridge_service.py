import asyncio
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

logger = logging.getLogger(__name__)

_bridge_task: asyncio.Task | None = None
_bridge_config: dict[str, object] = {}
_active_patient_id: str | None = None

HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

# How long to wait before retrying after a failure
_RETRY_DELAY_SECONDS = 15


def _normalize_uuid(value: str | None) -> str:
    return (value or "").strip().lower()


def resolve_notify_characteristic(client: BleakClient) -> str | None:
    """Find the best notify characteristic for heart-rate streaming on this device."""
    wanted_service = _normalize_uuid(HEART_RATE_SERVICE_UUID)
    wanted_char = _normalize_uuid(HEART_RATE_MEASUREMENT_UUID)

    fallback_notify_uuid: str | None = None

    for service in client.services:
        service_uuid = _normalize_uuid(getattr(service, "uuid", ""))
        for char in service.characteristics:
            char_uuid = _normalize_uuid(getattr(char, "uuid", ""))
            props = {p.lower() for p in getattr(char, "properties", [])}
            if "notify" not in props and "indicate" not in props:
                continue

            if char_uuid == wanted_char:
                return char.uuid

            if not fallback_notify_uuid and service_uuid == wanted_service:
                fallback_notify_uuid = char.uuid

    return fallback_notify_uuid


def parse_heart_rate_measurement(payload: bytearray) -> int | None:
    if not payload:
        return None

    flags = payload[0]
    is_uint16 = bool(flags & 0x01)

    if is_uint16:
        if len(payload) < 3:
            return None
        return int.from_bytes(payload[1:3], byteorder="little", signed=False)

    if len(payload) < 2:
        return None
    return int(payload[1])


def post_heartbeat(backend_url: str, patient_id: str, heart_rate: int, threshold: int, source: str) -> tuple[bool, dict]:
    url = backend_url.rstrip("/") + "/heartbeat/report"
    body = json.dumps(
        {
            "patient_id": patient_id,
            "heart_rate": heart_rate,
            "threshold": threshold,
            "source": source,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            text = response.read().decode("utf-8")
            data = json.loads(text)
            return True, data
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="ignore")
        return False, {"error": f"HTTP {exc.code}: {msg}"}
    except Exception as exc:
        return False, {"error": str(exc)}


async def resolve_device_address(device_name: str, timeout: float) -> str | None:
    """Scan for a BLE device.

    Strategy:
    1. If device_name is given, match by name substring (case-insensitive).
    2. Fallback: pick the strongest-RSSI device that advertises the standard
       Heart Rate Service UUID (0x180D) — works for generic HR sensors.
    """
    logger.info(f"[POLAR] Scanning {timeout:.0f}s for '{device_name or 'any heart-rate device'}'...")

    found_by_name: tuple[str, str, int] | None = None   # (address, name, rssi)
    found_by_hr: tuple[str, str, int] | None = None     # (address, name, rssi) — best HR service

    hr_service_short = "180d"

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        nonlocal found_by_name, found_by_hr

        name = (device.name or "").strip()
        rssi = adv.rssi or -999

        if device_name and device_name.lower() in name.lower():
            if found_by_name is None or rssi > found_by_name[2]:
                found_by_name = (device.address, name, rssi)
                logger.info(f"[POLAR] Name-match: {name!r} @ {device.address} rssi={rssi}")

        uuids = [u.lower() for u in (adv.service_uuids or [])]
        if any(hr_service_short in u for u in uuids):
            if found_by_hr is None or rssi > found_by_hr[2]:
                found_by_hr = (device.address, name or device.address, rssi)
                logger.info(f"[POLAR] HR-service device: {name or device.address!r} @ {device.address} rssi={rssi}")

    try:
        async with BleakScanner(callback) as _scanner:
            await asyncio.sleep(timeout)
    except Exception as exc:
        logger.error(f"[POLAR] BLE scan failed: {type(exc).__name__}: {exc}")
        return None

    if found_by_name:
        logger.info(f"[POLAR] Using name-matched device: {found_by_name[1]!r} @ {found_by_name[0]}")
        return found_by_name[0]

    if found_by_hr:
        logger.info(f"[POLAR] Using HR-service fallback device: {found_by_hr[1]!r} @ {found_by_hr[0]}")
        return found_by_hr[0]

    return None


async def _connect_and_stream(
    address: str,
    patient_id: str,
    backend_url: str,
    threshold: int,
    source: str,
) -> None:
    """Connect to a single BLE device and stream heart rate until disconnected."""
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_disconnect(_: BleakClient) -> None:
        logger.info("[POLAR] Device disconnected.")
        loop.call_soon_threadsafe(stop_event.set)

    # Note: do NOT pass winrt= here — that is a Windows-only option and causes
    # errors on Linux (Raspberry Pi / BlueZ backend).
    async with BleakClient(address, disconnected_callback=handle_disconnect) as client:
        if not client.is_connected:
            raise RuntimeError("BleakClient connected=False after context entry")

        notify_uuid = resolve_notify_characteristic(client)
        if not notify_uuid:
            logger.error("[POLAR] No heart-rate notify characteristic found on this device.")
            logger.info("[POLAR] Available services/characteristics:")
            for service in client.services:
                logger.info(f"  [SERVICE] {service.uuid}")
                for char in service.characteristics:
                    props = ",".join(char.properties)
                    logger.info(f"    [CHAR] {char.uuid} props={props}")
            raise RuntimeError("No notify characteristic found")

        if _normalize_uuid(notify_uuid) != _normalize_uuid(HEART_RATE_MEASUREMENT_UUID):
            logger.info(f"[POLAR] Using fallback notify characteristic: {notify_uuid}")

        logger.info(f"[POLAR] Connected to {address} — streaming heart rate...")

        async def _handle_heart_rate_reading(bpm: int) -> None:
            now = datetime.now().strftime("%H:%M:%S")
            ok, response_data = await asyncio.to_thread(
                post_heartbeat,
                backend_url,
                patient_id,
                bpm,
                threshold,
                source,
            )

            if ok:
                if response_data.get("alert_triggered"):
                    logger.warning(
                        f"[{now}] ALERT! BPM={bpm} exceeded threshold={response_data.get('threshold')}"
                    )
                else:
                    logger.debug(f"[{now}] BPM={bpm} -> ok")
            else:
                logger.warning(f"[{now}] BPM={bpm} -> backend error: {response_data.get('error', 'unknown')}")

        def on_hr_notification(_: int, data: bytearray) -> None:
            bpm = parse_heart_rate_measurement(data)
            if bpm is None or bpm <= 0:
                return
            asyncio.create_task(_handle_heart_rate_reading(bpm))

        await client.start_notify(notify_uuid, on_hr_notification)
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            logger.info("[POLAR] Bridge task cancelled.")
            raise
        finally:
            try:
                await client.stop_notify(notify_uuid)
            except Exception:
                pass


async def run_heartbeat_bridge(
    patient_id: str,
    backend_url: str = "http://127.0.0.1:8000",
    device_name: str = "Polar H10",
    device_address: str = "",
    threshold: int = 120,
    source: str = "polar_h10",
    scan_timeout: float = 10.0,
) -> None:
    """Run the heart rate sensor -> backend bridge with automatic retries.

    Retries indefinitely until the bridge task is cancelled or _active_patient_id
    is cleared.  Each failure waits _RETRY_DELAY_SECONDS before trying again.
    """
    if not patient_id:
        logger.warning("[POLAR] patient_id not configured; heartbeat bridge disabled")
        return

    attempt = 0
    while _active_patient_id == patient_id:
        attempt += 1
        logger.info(f"[POLAR] Bridge attempt #{attempt} for patient {patient_id}")

        try:
            address = device_address.strip()
            if not address:
                address = await resolve_device_address(device_name, scan_timeout)

            if not address:
                logger.warning(
                    f"[POLAR] Sensor not found (attempt #{attempt}). "
                    f"Make sure '{device_name}' is on and not connected to another device. "
                    f"Retrying in {_RETRY_DELAY_SECONDS}s..."
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
                continue

            await _connect_and_stream(
                address=address,
                patient_id=patient_id,
                backend_url=backend_url,
                threshold=threshold,
                source=source,
            )

            # If we get here, the device disconnected cleanly — try to reconnect immediately.
            logger.info("[POLAR] Device disconnected — reconnecting...")

        except asyncio.CancelledError:
            logger.info("[POLAR] Bridge cancelled.")
            return
        except Exception as exc:
            logger.error(
                f"[POLAR] Bridge error (attempt #{attempt}): {type(exc).__name__}: {exc}. "
                f"Retrying in {_RETRY_DELAY_SECONDS}s..."
            )
            await asyncio.sleep(_RETRY_DELAY_SECONDS)

    logger.info("[POLAR] Bridge stopped (patient changed or cleared).")


async def set_active_heartbeat_patient(
    patient_id: str | None,
    backend_url: str = "http://127.0.0.1:8000",
    device_name: str = "Polar H10",
    device_address: str = "",
    threshold: int = 120,
    source: str = "polar_h10",
    scan_timeout: float = 10.0,
) -> dict:
    """Start, restart, or stop the heart rate bridge for the supplied patient."""
    global _bridge_task, _bridge_config, _active_patient_id

    requested_patient_id = (patient_id or "").strip()
    current_config = {
        "backend_url": backend_url,
        "device_name": device_name,
        "device_address": device_address,
        "threshold": threshold,
        "source": source,
        "scan_timeout": scan_timeout,
    }

    if _bridge_task is not None and not _bridge_task.done() and requested_patient_id == _active_patient_id:
        return {
            "status": "unchanged",
            "patient_id": _active_patient_id,
            "message": "Heartbeat bridge already active for this patient",
        }

    if _bridge_task is not None and not _bridge_task.done():
        _bridge_task.cancel()
        try:
            await _bridge_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.info(f"[POLAR] Previous bridge stopped with: {exc}")

    _bridge_task = None
    _bridge_config = current_config
    _active_patient_id = requested_patient_id or None

    if not requested_patient_id:
        return {
            "status": "stopped",
            "patient_id": None,
            "message": "Heartbeat bridge stopped",
        }

    _bridge_task = asyncio.create_task(
        run_heartbeat_bridge(
            patient_id=requested_patient_id,
            backend_url=backend_url,
            device_name=device_name,
            device_address=device_address,
            threshold=threshold,
            source=source,
            scan_timeout=scan_timeout,
        )
    )

    return {
        "status": "started",
        "patient_id": requested_patient_id,
        "message": "Heartbeat bridge started (will retry automatically if sensor not found)",
    }


def get_active_heartbeat_patient() -> str | None:
    return _active_patient_id
