import {BASE_URL} from '../config';

const REQUEST_TIMEOUT_MS = 10000;

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error('Heartbeat request timed out. Check backend and Wi-Fi connection.');
    }

    if (String(error?.message || '').toLowerCase().includes('network request failed')) {
      throw new Error('Network request failed. Verify BASE_URL, backend server, and same Wi-Fi network.');
    }

    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function parseJsonResponse(response) {
  const data = await response.json();
  if (!response.ok || data?.error) {
    throw new Error(data?.detail || data?.error || 'Heartbeat request failed');
  }
  return data;
}

export async function fetchLiveHeartbeat(patientId) {
  const response = await fetchWithTimeout(
    `${BASE_URL}/heartbeat/live/${encodeURIComponent(patientId)}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  return parseJsonResponse(response);
}

export async function reportHeartbeat({patientId, heartRate, threshold, source = 'sensor'}) {
  const response = await fetchWithTimeout(`${BASE_URL}/heartbeat/report`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      patient_id: patientId,
      heart_rate: heartRate,
      threshold,
      source,
    }),
  });

  return parseJsonResponse(response);
}
