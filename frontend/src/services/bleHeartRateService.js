import {BleManager} from 'react-native-ble-plx';
import {PermissionsAndroid, Platform} from 'react-native';
import {reportHeartbeat} from './heartbeatService';

const HR_SERVICE_SHORT     = '180d';
const HR_MEASUREMENT_SHORT = '2a37';
const POLAR_NAME_KEYWORDS  = ['polar h10', 'polar'];
const SCAN_TIMEOUT_MS      = 30000;
const REPORT_INTERVAL_MS   = 3000;
const RECONNECT_DELAY_MS   = 2000;
const TRANSACTION_ID       = 'polar_hr_monitor';

let _manager = null;

function getManager() {
  if (!_manager) {
    _manager = new BleManager();
  }
  return _manager;
}

export async function requestBlePermissions() {
  if (Platform.OS !== 'android') {
    return true;
  }
  if (Platform.Version >= 31) {
    const results = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ]);
    return Object.values(results).every(
      r => r === PermissionsAndroid.RESULTS.GRANTED,
    );
  }
  const result = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
  );
  return result === PermissionsAndroid.RESULTS.GRANTED;
}

function decodeHeartRate(base64Value) {
  // Manual base64 → bytes so we don't depend on atob behaviour
  const table = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const str    = base64Value.replace(/=+$/, '');
  const bytes  = [];
  let buf = 0;
  let bitsLeft = 0;
  for (let i = 0; i < str.length; i++) {
    const v = table.indexOf(str[i]);
    if (v === -1) { continue; }
    buf = (buf << 6) | v;
    bitsLeft += 6;
    if (bitsLeft >= 8) {
      bitsLeft -= 8;
      bytes.push((buf >> bitsLeft) & 0xff);
    }
  }
  if (bytes.length < 2) { return 0; }
  const flags    = bytes[0];
  const isUint16 = (flags & 0x01) === 1;
  if (isUint16) {
    if (bytes.length < 3) { return 0; }
    return bytes[1] + (bytes[2] << 8);
  }
  return bytes[1];
}

function isHeartRateDevice(device) {
  const name = ((device.name || '') + ' ' + (device.localName || '')).toLowerCase();
  return POLAR_NAME_KEYWORDS.some(k => name.includes(k)) ||
    (device.serviceUUIDs || []).some(u => u.toLowerCase().includes(HR_SERVICE_SHORT));
}

function waitForBluetoothOn(manager) {
  return new Promise((resolve, reject) => {
    const sub = manager.onStateChange(state => {
      if (state === 'PoweredOn') { sub.remove(); resolve(); }
      else if (state === 'Unsupported' || state === 'Unauthorized') {
        sub.remove();
        reject(new Error(`Bluetooth is ${state}. Check phone settings.`));
      }
    }, true);
  });
}

async function findHrInfo(device) {
  const services = await device.services();
  for (const svc of services) {
    if (!svc.uuid.toLowerCase().includes(HR_SERVICE_SHORT)) { continue; }
    const chars = await svc.characteristics();
    const c = chars.find(
      ch => ch.uuid.toLowerCase().includes(HR_MEASUREMENT_SHORT) &&
            (ch.isNotifiable || ch.isIndicatable),
    );
    if (c) { return {serviceUUID: svc.uuid, charUUID: c.uuid}; }
  }
  return null;
}

/**
 * Scan for a Polar H10, connect, and stream live BPM readings.
 *
 * onBpm({bpm, ts}) — ts = Date.now() every notification so React always
 * re-renders even when the numeric BPM is unchanged.
 *
 * Returns a stop() function.
 */
export function startHeartRateMonitor({
  patientId,
  threshold = 90,
  onBpm,
  onStatus,
  onError,
}) {
  const manager    = getManager();
  let stopped      = false;
  let currentSub   = null;
  let scanTimeout  = null;
  let lastReport   = 0;
  let foundDeviceId = null; // remember device so we can reconnect without re-scan

  function cancelCurrentSub() {
    if (currentSub) {
      try { currentSub.remove(); } catch (_) {}
      currentSub = null;
    }
  }

  function stop() {
    stopped = true;
    if (scanTimeout) { clearTimeout(scanTimeout); scanTimeout = null; }
    manager.stopDeviceScan();
    cancelCurrentSub();
    if (foundDeviceId) {
      manager.cancelDeviceConnection(foundDeviceId).catch(() => {});
      foundDeviceId = null;
    }
  }

  // ── Start a monitor session on an already-connected device ─────────────
  // If the native layer fires a disconnect error (code 201), we reconnect
  // and start a fresh monitor session instead of just re-subscribing.
  async function monitorSession(deviceId, hrInfo) {
    if (stopped) { return; }

    cancelCurrentSub();

    currentSub = manager.monitorCharacteristicForDevice(
      deviceId,
      hrInfo.serviceUUID,
      hrInfo.charUUID,
      async (charError, characteristic) => {
        if (stopped) { return; }

        if (charError) {
          cancelCurrentSub();

          // errorCode 201 = DeviceDisconnected — try to fully reconnect
          const isDisconnect = charError.errorCode === 201;
          if (isDisconnect) {
            onStatus('disconnected');
            await reconnect(deviceId);
          } else {
            // Other error — brief pause then re-monitor on same connection
            await delay(800);
            if (!stopped) { monitorSession(deviceId, hrInfo); }
          }
          return;
        }

        if (characteristic?.value) {
          const bpm = decodeHeartRate(characteristic.value);
          if (bpm > 0 && bpm < 250) {
            onBpm({bpm, ts: Date.now()});

            const now = Date.now();
            if (now - lastReport >= REPORT_INTERVAL_MS) {
              lastReport = now;
              reportHeartbeat({
                patientId,
                heartRate: bpm,
                threshold,
                source: 'phone_ble',
              }).catch(() => {});
            }
          }
        }
      },
      TRANSACTION_ID,
    );
  }

  // ── Reconnect to a known device ID after disconnection ─────────────────
  async function reconnect(deviceId) {
    if (stopped) { return; }
    await delay(RECONNECT_DELAY_MS);
    if (stopped) { return; }
    onStatus('connecting');
    try {
      const connected = await manager.connectToDevice(deviceId, {timeout: 15000});
      if (stopped) { manager.cancelDeviceConnection(deviceId).catch(() => {}); return; }
      await connected.requestMTU(512).catch(() => {}); // ignored if unsupported
      await connected.discoverAllServicesAndCharacteristics();
      if (stopped) { manager.cancelDeviceConnection(deviceId).catch(() => {}); return; }
      const hrInfo = await findHrInfo(connected);
      if (!hrInfo) {
        onStatus('error');
        onError('Heart rate service not found after reconnect');
        return;
      }
      onStatus('connected');
      await monitorSession(deviceId, hrInfo);
    } catch (err) {
      if (!stopped) {
        // If device is gone entirely, fall back to full re-scan
        onStatus('scanning');
        startScan();
      }
    }
  }

  // ── Initial scan ────────────────────────────────────────────────────────
  function startScan() {
    if (stopped) { return; }

    manager.startDeviceScan(
      null,
      {allowDuplicates: false},
      async (scanError, device) => {
        if (stopped) { return; }
        if (scanError) {
          onStatus('error');
          onError(scanError.message || 'BLE scan failed. Is Bluetooth on?');
          return;
        }
        if (!device || !isHeartRateDevice(device)) { return; }

        if (scanTimeout) { clearTimeout(scanTimeout); scanTimeout = null; }
        manager.stopDeviceScan();
        onStatus('connecting');

        try {
          const connected = await manager.connectToDevice(device.id, {timeout: 15000});
          if (stopped) { manager.cancelDeviceConnection(device.id).catch(() => {}); return; }

          // Request larger MTU — helps with Android BLE stability
          await connected.requestMTU(512).catch(() => {});

          await connected.discoverAllServicesAndCharacteristics();
          if (stopped) { manager.cancelDeviceConnection(device.id).catch(() => {}); return; }

          const hrInfo = await findHrInfo(connected);
          if (!hrInfo) {
            onStatus('error');
            onError('This device does not expose a Heart Rate service.');
            return;
          }

          foundDeviceId = connected.id;
          onStatus('connected');
          await monitorSession(connected.id, hrInfo);

        } catch (connectErr) {
          if (!stopped) {
            onStatus('error');
            onError(connectErr.message || 'Could not connect to sensor');
          }
        }
      },
    );

    scanTimeout = setTimeout(() => {
      if (stopped) { return; }
      manager.stopDeviceScan();
      onStatus('error');
      onError(
        'Sensor not found after 30 s. Ensure the Polar H10 is on your chest and Polar Beat is closed.',
      );
    }, SCAN_TIMEOUT_MS);
  }

  // ── Kick off ────────────────────────────────────────────────────────────
  async function run() {
    try {
      onStatus('scanning');
      await waitForBluetoothOn(manager);
    } catch (btErr) {
      if (!stopped) { onStatus('error'); onError(btErr.message); }
      return;
    }
    if (!stopped) { startScan(); }
  }

  run();
  return stop;
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}
