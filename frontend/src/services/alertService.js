import {BASE_URL} from '../config';

const REQUEST_TIMEOUT_MS = 15000;

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
      throw new Error('Alerts request timed out.');
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function parseJsonResponse(response) {
  const data = await response.json();
  if (!response.ok || data?.error) {
    throw new Error(data?.detail || data?.error || 'Alerts request failed');
  }
  return data;
}

export async function getUnreadAlerts(patientId) {
  if (!patientId) {
    throw new Error('Patient ID is required');
  }

  const response = await fetchWithTimeout(
    `${BASE_URL}/alerts/${encodeURIComponent(patientId)}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  return parseJsonResponse(response);
}

export async function markAlertAsRead(alertId) {
  if (!alertId) {
    throw new Error('Alert ID is required');
  }

  const response = await fetchWithTimeout(
    `${BASE_URL}/alerts/${encodeURIComponent(alertId)}/read`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  return parseJsonResponse(response);
}

export async function clearAllAlerts(patientId) {
  if (!patientId) {
    throw new Error('Patient ID is required');
  }

  const response = await fetchWithTimeout(
    `${BASE_URL}/alerts/${encodeURIComponent(patientId)}/clear-all`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  return parseJsonResponse(response);
}
