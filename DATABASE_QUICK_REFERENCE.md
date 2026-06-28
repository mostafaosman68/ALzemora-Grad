# Database Quick Reference - For AI/Developer Integration

## Credentials (⚠️ SENSITIVE)
```
Connection String: mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0
Database Name: Alzemora
Username: Alzemora
Password: alzemora2026
```

## Collections Overview

| Collection | Purpose | Key Field | Connections |
|---|---|---|---|
| **users** | Patient profiles | `_id`, `email` (unique) | Parent for people, medications, health data |
| **guardians** | Guardian accounts (max 2/patient) | `_id`, `email` (unique) | Linked via `patient_links` |
| **caregivers** | Caregiver accounts (max 1/patient) | `_id`, `email` (unique) | Linked via `patient_links` |
| **people** | Known faces/voices | `_id`, `user_id` | Child of users, stores embeddings |
| **medications** | Patient medications | `_id`, `user_id` | Child of users |
| **heartbeat_readings** | All HR readings (time-series) | `_id`, `patient_id`, `recorded_at` | Historical data |
| **heartbeat_latest** | Most recent HR reading | `patient_id` (unique per patient) | Real-time data |
| **heartbeat_alerts** | Triggered HR alerts | `_id`, `patient_id` | Notifications |

## Critical Fields Reference

### users
- `_id` - MongoDB ObjectId (primary key)
- `email` - Unique identifier, used for login
- `password` - Stored password (hash recommended)
- `full_name` - Patient name
- `role` - Always "User" for patients
- `patient_links` - Array of guardian/caregiver links
- `age`, `status`, `address` - Patient metadata
- `emergency_contacts` - JSON string
- `last_location` - JSON string {lat, lng, timestamp}
- `dnr_status` - Do Not Resuscitate flag
- `created_at` - Account creation timestamp

### guardians / caregivers
- `_id` - MongoDB ObjectId
- `email` - Unique per collection
- `password` - Stored password
- `full_name` - Helper name
- `role` - "Guardian" or "CareGiver"
- `patient_links` - `[{patient_id: string, patient_name: string}]`
- `agency` - (caregivers only) Agency name
- `created_at` - Account creation timestamp

### people
- `_id` - MongoDB ObjectId
- `user_id` - Foreign key to users._id
- `name` - Person's name
- `relation` - Relationship to patient (e.g., "Friend", "Family")
- `photo_url` - Path/URL to photo
- `voice` - Path to voice recording
- `face_embedding` - JSON string of face vector array
- `voice_embedding` - JSON string of voice vector array
- `permissions` - JSON string of access permissions

### heartbeat_* collections
**heartbeat_readings** (all readings):
- `patient_id` - Target patient
- `heart_rate` - BPM (integer)
- `threshold` - Alert threshold (default 120)
- `status` - "live" or "alert_triggered"
- `alert_triggered` - Boolean
- `recipients` - Array of notifiable helpers
- `source` - "sensor" or "manual_check"
- `recorded_at` - When reading was taken
- `updated_at` - When record was updated

**heartbeat_latest** (most recent):
- Same as above but upserted per patient
- Use for real-time status display

**heartbeat_alerts** (triggered events):
- `patient_id` - Target patient
- `heart_rate` - Triggering BPM
- `threshold` - What threshold was exceeded
- `triggered_at` - Alert timestamp
- `recipients` - Who to notify
- `status` - "triggered"

## Connection Examples

### Python (FastAPI Backend - Current)
```python
from pymongo import AsyncMongoClient

client = AsyncMongoClient("mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0")
db = client["Alzemora"]

# Query example
user = await db.users.find_one({"email": "patient@example.com"})
```

### Node.js
```javascript
const { MongoClient } = require("mongodb");
const uri = "mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0";
const client = new MongoClient(uri);
const db = client.db("Alzemora");

// Query example
const user = await db.collection("users").findOne({email: "patient@example.com"});
```

### Python (Sync - Alternative)
```python
from pymongo import MongoClient

client = MongoClient("mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0")
db = client["Alzemora"]

# Query example
user = db.users.find_one({"email": "patient@example.com"})
```

## Common Queries

### Find patient by email
```javascript
db.users.findOne({ email: "patient@example.com" })
```

### Find all guardians linked to patient
```javascript
db.guardians.find({ "patient_links.patient_id": ObjectId("patient_id_here") })
```

### Get latest heartbeat for patient
```javascript
db.heartbeat_latest.findOne({ patient_id: "patient_id_here" })
```

### Get all known faces for patient
```javascript
db.people.find({ user_id: "patient_id_here" })
```

### Get all heartbeat alerts for patient (last 24 hours)
```javascript
db.heartbeat_alerts.find({
  patient_id: "patient_id_here",
  triggered_at: { $gte: new Date(Date.now() - 24*60*60*1000) }
})
```

## Relationship Map

```
users (Patient)
  ├── Guardians ←→ guardians collection (via patient_links)
  ├── Caregivers ←→ caregivers collection (via patient_links)
  ├── People (Known faces) → people collection (user_id field)
  ├── Medications → medications collection (user_id field)
  ├── Heart Readings → heartbeat_readings collection (patient_id field)
  ├── Latest Heart Rate → heartbeat_latest collection (patient_id field)
  └── Heart Alerts → heartbeat_alerts collection (patient_id field)
```

## Important Behaviors

1. **Patient Links**: All guardians and caregivers have a `patient_links` array that can contain multiple patients. Active patient selection is stored separately.

2. **Heart Rate Alerts**: 
   - Triggered when HR ≥ threshold (default 120 bpm)
   - Automatically notifies all linked guardians/caregivers
   - Alert record stored in heartbeat_alerts collection

3. **Embeddings Format**: 
   - Face and voice embeddings stored as JSON strings
   - Must parse/stringify when reading/writing: `JSON.parse(embedding_string)`

4. **Backward Compatibility**:
   - Old single-patient links use `patient_id` field (legacy)
   - New system uses `patient_links` array
   - Code handles both formats

5. **Async Requirements**: All Python queries must use `await` keyword (AsyncMongoClient)

## File Locations in Project
- Database config: `Backend/app/database.py`
- API routes: `Backend/app/routes/` (users, people, heartbeat, recognition, ml_process)
- Environment: `Backend/.env` (contains credentials)
- Models (legacy): `Backend/app/models.py` (SQLAlchemy - NOT USED, ignore)

## Testing Connection
```bash
# From Backend directory with .env configured
python -c "from app.database import connect_to_mongo, get_db; import asyncio; asyncio.run(connect_to_mongo())"
```
