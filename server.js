import express from "express";

const app = express();
const PORT = process.env.PORT || 3000;
const DEFAULT_RADIUS_METERS = 100;
//TO DO: Add authentication and authorization for production use.
// In-memory storage for demo/simple usage. Replace with a database for production.
const devices = new Map();

app.use(express.json());
app.use(express.static("public"));

app.get("/", (req, res) => {
  res.json({
    message: "Geofence backend is running.",
    endpoints: {
      setGeofence: "POST /devices/:deviceId/geofence",
      updateLocation: "POST /devices/:deviceId/location",
      getStatus: "GET /devices/:deviceId/status",
    },
  });
});

app.post("/devices/:deviceId/geofence", (req, res) => {
  const { deviceId } = req.params;
  const { latitude, longitude, radiusMeters = DEFAULT_RADIUS_METERS } = req.body;

  const validationError = validateCoordinates(latitude, longitude);
  if (validationError) {
    return res.status(400).json({ error: validationError });
  }

  if (!Number.isFinite(radiusMeters) || radiusMeters <= 0) {
    return res.status(400).json({ error: "radiusMeters must be a positive number." });
  }

  const existing = devices.get(deviceId) || {};
  const geofence = {
    latitude,
    longitude,
    radiusMeters,
    createdAt: new Date().toISOString(),
  };

  devices.set(deviceId, { ...existing, geofence });

  return res.status(201).json({
    deviceId,
    geofence,
  });
});

app.post("/devices/:deviceId/location", (req, res) => {
  const { deviceId } = req.params;
  const { latitude, longitude } = req.body;

  const validationError = validateCoordinates(latitude, longitude);
  if (validationError) {
    return res.status(400).json({ error: validationError });
  }

  const device = devices.get(deviceId);
  if (!device?.geofence) {
    return res.status(404).json({
      error: "No geofence is set for this device.",
    });
  }

  const distanceMeters = getDistanceMeters(device.geofence, { latitude, longitude });
  const outside = distanceMeters > device.geofence.radiusMeters;

  const location = {
    latitude,
    longitude,
    receivedAt: new Date().toISOString(),
  };

  devices.set(deviceId, {
    ...device,
    lastLocation: location,
    lastStatus: outside ? "outside" : "inside",
    lastDistanceMeters: distanceMeters,
  });

  return res.json({
    deviceId,
    status: outside ? "outside" : "inside",
    alert: outside,
    distanceMeters: Math.round(distanceMeters),
    radiusMeters: device.geofence.radiusMeters,
    location,
  });
});

app.get("/devices/:deviceId/status", (req, res) => {
  const { deviceId } = req.params;
  const device = devices.get(deviceId);

  if (!device) {
    return res.status(404).json({ error: "Device not found." });
  }

  return res.json({
    deviceId,
    geofence: device.geofence || null,
    lastLocation: device.lastLocation || null,
    status: device.lastStatus || "unknown",
    distanceMeters:
      typeof device.lastDistanceMeters === "number"
        ? Math.round(device.lastDistanceMeters)
        : null,
  });
});

app.listen(PORT, () => {
  console.log(`Geofence backend running on http://localhost:${PORT}`);
});

function validateCoordinates(latitude, longitude) {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return "latitude and longitude must be numbers.";
  }

  if (latitude < -90 || latitude > 90) {
    return "latitude must be between -90 and 90.";
  }

  if (longitude < -180 || longitude > 180) {
    return "longitude must be between -180 and 180.";
  }

  return null;
}

function getDistanceMeters(from, to) {
  const earthRadiusMeters = 6371000;
  const fromLatitude = toRadians(from.latitude);
  const toLatitude = toRadians(to.latitude);
  const deltaLatitude = toRadians(to.latitude - from.latitude);
  const deltaLongitude = toRadians(to.longitude - from.longitude);

  const haversine =
    Math.sin(deltaLatitude / 2) ** 2 +
    Math.cos(fromLatitude) *
      Math.cos(toLatitude) *
      Math.sin(deltaLongitude / 2) ** 2;

  return (
    earthRadiusMeters *
    2 *
    Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))
  );
}

function toRadians(degrees) {
  return degrees * (Math.PI / 180);
}
