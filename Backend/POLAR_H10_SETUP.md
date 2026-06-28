# Polar H10 Laptop Bridge Setup

This sends live BPM from a Polar H10 chest strap to the backend endpoint:

- `POST /heartbeat/report`

## 1) Install dependencies

From `Backend` folder:

```powershell
pip install bleak
```

`urllib` is part of Python stdlib, so no extra HTTP package is required.

## 2) Run backend

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 3) Run Polar H10 bridge

```powershell
python polar_h10_bridge.py --patient-id <PATIENT_ID>
```

Example:

```powershell
python polar_h10_bridge.py --patient-id 6803fabc1234567890abcd12 --backend-url http://127.0.0.1:8000
```

If auto-scan fails, run with MAC address:

```powershell
python polar_h10_bridge.py --patient-id <PATIENT_ID> --device-address AA:BB:CC:DD:EE:FF
```

## 4) Open app HB screen

- In mobile app: `Dashboard -> HB`
- The screen polls every 3 seconds and should show sensor connected + live BPM.

## Notes

- On Windows, make sure Bluetooth is ON and Polar H10 is worn (electrodes active).
- Pairing is optional for BLE, but it can help connection stability.
- Only one app should hold the Polar H10 stream at a time.
