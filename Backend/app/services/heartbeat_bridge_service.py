import asyncio
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import datetime

from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)

_bridge_task: asyncio.Task | None = None
_bridge_config: dict[str, object] = {}
_active_patient_id: str | None = None

HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


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
    logger.info(f"[POLAR] Scanning for BLE devices ({timeout:.0f}s)...")
    try:
        devices = await BleakScanner.discover(timeout=timeout)

        for device in devices:
            name = (device.name or "").strip()
            if device_name.lower() in name.lower():
                logger.info(f"[POLAR] Found device: {name} ({device.address})")
                return device.address
    except Exception as exc:
        logger.error(f"[POLAR] BLE scan failed: {exc}")

    return None


async def run_heartbeat_bridge(
    patient_id: str,
    backend_url: str = "http://127.0.0.1:8000",
    device_name: str = "Polar H10",
    device_address: str = "",
    threshold: int = 120,
    source: str = "polar_h10",
    scan_timeout: float = 10.0,
) -> None:
    """Run the Polar H10 -> Backend heartbeat bridge as a background task."""
    if not patient_id:
        logger.warning("[POLAR] patient_id not configured; heartbeat bridge disabled")
        return

    address = device_address
    if not address:
        address = await resolve_device_address(device_name, scan_timeout)
        if not address:
            logger.warning(f"[POLAR] Could not find a BLE device matching '{device_name}'.")
            logger.warning("[POLAR] Tip: set POLAR_DEVICE_ADDRESS environment variable with the exact MAC address.")
            return

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_disconnect(_: BleakClient) -> None:
        logger.info("[POLAR] Device disconnected.")
        loop.call_soon_threadsafe(stop_event.set)

    try:
        async with BleakClient(
            address,
            disconnected_callback=handle_disconnect,
            winrt={"use_cached_services": False},
        ) as client:
            if not client.is_connected:
                logger.error("[POLAR] Failed to connect to Polar H10.")
                return

            notify_uuid = resolve_notify_characteristic(client)
            if not notify_uuid:
                logger.error("[POLAR] No notify characteristic found on this device.")
                logger.info("[POLAR] Available services/characteristics:")
                for service in client.services:
                    logger.info(f"  [SERVICE] {service.uuid}")
                    for char in service.characteristics:
                        props = ",".join(char.properties)
                        logger.info(f"    [CHAR] {char.uuid} props={props}")
                return

            if _normalize_uuid(notify_uuid) != _normalize_uuid(HEART_RATE_MEASUREMENT_UUID):
                logger.info(f"[POLAR] Using fallback notify characteristic: {notify_uuid}")

            logger.info(f"[POLAR] Connected to {address}")
            logger.info("[POLAR] Streaming heart rate...")

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
                    # Check if an alert was triggered (BPM > threshold)
                    if response_data.get("alert_triggered"):
                        logger.warning(
                            f"[{now}] ⚠️ ALERT! BPM={bpm} exceeded threshold={response_data.get('threshold')} -> "
                            f"notification sent to patient"
                        )
                    else:
                        logger.debug(f"[{now}] BPM={bpm} -> backend ok")
                else:
                    logger.warning(f"[{now}] BPM={bpm} -> backend error: {response_data.get('error', 'unknown')}")

            def on_hr_notification(_: int, data: bytearray) -> None:
                bpm = parse_heart_rate_measurement(data)
                if bpm is None or bpm <= 0:
                    logger.debug(f"[POLAR] Ignoring invalid heart rate payload: {list(data)}")
                    return

                asyncio.create_task(_handle_heart_rate_reading(bpm))

            try:
                await client.start_notify(notify_uuid, on_hr_notification)
            except Exception as exc:
                logger.error(f"[POLAR] Failed to start notifications on {notify_uuid}: {exc}")
                logger.error("[POLAR] Ensure Polar Beat/Flow or any other app is not connected to the strap.")
                logger.error("[POLAR] If needed, remove and re-pair the sensor from Windows Bluetooth settings.")
                return

            try:
                await stop_event.wait()
            except asyncio.CancelledError:
                logger.info("[POLAR] Bridge task cancelled.")
            finally:
                try:
                    await client.stop_notify(notify_uuid)
                except Exception:
                    pass

    except Exception as exc:
        logger.error(f"[POLAR] Bridge error: {exc}")


async def set_active_heartbeat_patient(
    patient_id: str | None,
    backend_url: str = "http://127.0.0.1:8000",
    device_name: str = "Polar H10",
    device_address: str = "",
    threshold: int = 120,
    source: str = "polar_h10",
    scan_timeout: float = 10.0,
) -> dict:
    """Start, restart, or stop the Polar bridge for the supplied patient."""
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
        "message": "Heartbeat bridge started",
    }


def get_active_heartbeat_patient() -> str | None:
    return _active_patient_id
