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
      throw new Error('Request timed out. Check the backend and Wi-Fi connection.');
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
    throw new Error(data?.detail || data?.error || 'Request failed');
  }
  return data;
}

export async function fetchMedicineCatalog() {
  const response = await fetchWithTimeout(`${BASE_URL}/medscan/catalog`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  return parseJsonResponse(response);
}

export async function fetchMedicineHistory(patientId, limit = 20) {
  const response = await fetchWithTimeout(
    `${BASE_URL}/medscan/history/${encodeURIComponent(patientId)}?limit=${encodeURIComponent(limit)}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  return parseJsonResponse(response);
}

export async function scanMedicineImage({patientId, actorUserId, actorRole, image}) {
  const formData = new FormData();
  formData.append('patient_id', patientId);
  if (actorUserId) {
    formData.append('actor_user_id', actorUserId);
  }
  if (actorRole) {
    formData.append('actor_role', actorRole);
  }
  formData.append('image_file', {
    uri: image.uri,
    name: image.fileName || image.name || 'scan.jpg',
    type: image.type || 'image/jpeg',
  });

  const response = await fetchWithTimeout(`${BASE_URL}/medscan/scan`, {
    method: 'POST',
    body: formData,
    headers: {
      Accept: 'application/json',
    },
  });

  return parseJsonResponse(response);
}