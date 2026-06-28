import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

from bleak import BleakClient, BleakScanner

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


def post_heartbeat(backend_url: str, patient_id: str, heart_rate: int, threshold: int, source: str) -> tuple[bool, str]:
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
            return True, text
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {exc.code}: {msg}"
    except Exception as exc:
        return False, str(exc)


async def resolve_device_address(device_name: str, timeout: float) -> str | None:
    print(f"[POLAR] Scanning for BLE devices ({timeout:.0f}s)...")
    devices = await BleakScanner.discover(timeout=timeout)

    for device in devices:
        name = (device.name or "").strip()
        if device_name.lower() in name.lower():
            print(f"[POLAR] Found device: {name} ({device.address})")
            return device.address

    return None


async def run_bridge(args: argparse.Namespace) -> None:
    address = args.device_address
    if not address:
        address = await resolve_device_address(args.device_name, args.scan_timeout)
        if not address:
            print(f"[POLAR] Could not find a BLE device matching '{args.device_name}'.")
            print("[POLAR] Tip: pass --device-address with the exact MAC address.")
            sys.exit(1)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_disconnect(_: BleakClient) -> None:
        print("[POLAR] Device disconnected.")
        loop.call_soon_threadsafe(stop_event.set)

    async with BleakClient(
        address,
        disconnected_callback=handle_disconnect,
        winrt={"use_cached_services": False},
    ) as client:
        if not client.is_connected:
            print("[POLAR] Failed to connect to Polar H10.")
            sys.exit(1)

        notify_uuid = resolve_notify_characteristic(client)
        if not notify_uuid:
            print("[POLAR] No notify characteristic found on this device.")
            print("[POLAR] Available services/characteristics:")
            for service in client.services:
                print(f"  [SERVICE] {service.uuid}")
                for char in service.characteristics:
                    props = ",".join(char.properties)
                    print(f"    [CHAR] {char.uuid} props={props}")
            sys.exit(1)

        if _normalize_uuid(notify_uuid) != _normalize_uuid(HEART_RATE_MEASUREMENT_UUID):
            print(f"[POLAR] Using fallback notify characteristic: {notify_uuid}")

        print(f"[POLAR] Connected to {address}")
        print("[POLAR] Streaming heart rate... Press Ctrl+C to stop.")

        async def on_hr_notification(_: int, data: bytearray) -> None:
            bpm = parse_heart_rate_measurement(data)
            if bpm is None:
                return

            now = datetime.now().strftime("%H:%M:%S")
            ok, result = await asyncio.to_thread(
                post_heartbeat,
                args.backend_url,
                args.patient_id,
                bpm,
                args.threshold,
                args.source,
            )

            if ok:
                print(f"[{now}] BPM={bpm} -> backend ok")
            else:
                print(f"[{now}] BPM={bpm} -> backend error: {result}")

        try:
            await client.start_notify(notify_uuid, on_hr_notification)
        except Exception as exc:
            print(f"[POLAR] Failed to start notifications on {notify_uuid}: {exc}")
            print("[POLAR] Ensure Polar Beat/Flow or any other app is not connected to the strap.")
            print("[POLAR] If needed, remove and re-pair the sensor from Windows Bluetooth settings.")
            raise

        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            print("\n[POLAR] Stopping bridge...")
        finally:
            await client.stop_notify(notify_uuid)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Polar H10 -> Backend heartbeat bridge",
    )
    parser.add_argument("--patient-id", required=True, help="Mongo user _id of the patient")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--threshold", type=int, default=120, help="Alert threshold BPM")
    parser.add_argument("--source", default="polar_h10", help="Source label stored in backend")
    parser.add_argument("--device-name", default="Polar H10", help="BLE name to match while scanning")
    parser.add_argument("--device-address", default="", help="BLE MAC address to connect directly")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="BLE scan timeout in seconds")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    cli_args = parser.parse_args()

    try:
        asyncio.run(run_bridge(cli_args))
    except KeyboardInterrupt:
        print("\n[POLAR] Bridge stopped.")
