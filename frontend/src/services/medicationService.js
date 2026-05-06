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
      throw new Error('Medication request timed out. Check backend and Wi-Fi connection.');
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
    throw new Error(data?.detail || data?.error || 'Medication request failed');
  }
  return data;
}

export async function addMedication({
  patientId,
  name,
  description,
  schedule,
  imageUris = [],
  actorUserId,
  actorRole,
}) {
  const formData = new FormData();
  formData.append('patient_id', patientId);
  formData.append('name', name);

  if (description) {
    formData.append('description', description);
  }

  if (schedule) {
    formData.append('schedule', JSON.stringify(schedule));
  }

  if (actorUserId) {
    formData.append('actor_user_id', actorUserId);
  }

  if (actorRole) {
    formData.append('actor_role', actorRole);
  }

  imageUris.forEach((uri, index) => {
    if (!uri) {
      return;
    }

    const fileName = uri.split('/').pop() || `medication_${index + 1}.jpg`;
    const fileType = fileName.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';
    formData.append('image_files', {
      uri,
      name: fileName,
      type: fileType,
    });
  });

  const response = await fetchWithTimeout(`${BASE_URL}/medications/add`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
    body: formData,
  });

  return parseJsonResponse(response);
}

export async function fetchPatientMedications(patientId) {
  const response = await fetchWithTimeout(
    `${BASE_URL}/medications/${encodeURIComponent(patientId)}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  return parseJsonResponse(response);
}

export async function recordGivenMedication({
  patientId,
  medicationId,
  medicationName,
  imageUri,
  actorUserId,
  actorRole,
}) {
  const formData = new FormData();
  formData.append('patient_id', patientId);
  if (medicationId) formData.append('medication_id', medicationId);
  if (medicationName) formData.append('medication_name', medicationName);
  if (actorUserId) formData.append('actor_user_id', actorUserId);
  if (actorRole) formData.append('actor_role', actorRole);

  const fileName = imageUri.split('/').pop() || 'given.jpg';
  const fileType = fileName.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';
  formData.append('image_file', {
    uri: imageUri,
    name: fileName,
    type: fileType,
  });

  const response = await fetchWithTimeout(`${BASE_URL}/medications/give`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
    body: formData,
  });

  return parseJsonResponse(response);
}

export async function detectMedicationFromImage(imageUri) {
  const formData = new FormData();

  const fileName = imageUri.split('/').pop() || 'detection.jpg';
  const fileType = fileName.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';
  formData.append('image_file', {
    uri: imageUri,
    name: fileName,
    type: fileType,
  });

  const response = await fetchWithTimeout(`${BASE_URL}/medications/detect`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
    body: formData,
  });

  return parseJsonResponse(response);
}