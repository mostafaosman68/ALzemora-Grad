# MOBILEFaceNet - Database Documentation

## Database Type & Connection Details

### Database Engine
- **Type**: MongoDB (NoSQL)
- **Connection Method**: MongoDB Atlas (Cloud)
- **Driver**: PyMongo 4.16.0 (Async)

### Connection Configuration

**Location**: `Backend/.env`

```
MONGODB_URL=mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0
MONGODB_DB_NAME=Alzemora
```

**Connection Details**:
- **Cluster**: cluster0.admj5gd.mongodb.net
- **Username**: Alzemora
- **Password**: alzemora2026
- **Database Name**: Alzemora
- **Service**: MongoDB Atlas

### Backend Configuration
- **Framework**: FastAPI 0.135.2
- **Python Version**: 3.8+
- **Connection Type**: AsyncMongoClient (Asynchronous)

---

## Collections Schema

### 1. **users** Collection
**Purpose**: Stores patient account information

**Document Structure**:
```json
{
  "_id": ObjectId,
  "email": "patient@example.com",
  "password": "hashed_password",
  "full_name": "John Doe",
  "role": "User",
  "profile_image": "url_or_path",
  "age": 65,
  "status": "active",
  "address": "123 Main St",
  "emergency_contacts": "JSON_string",
  "dnr_status": false,
  "last_medical_report": "url_or_path",
  "last_location": "JSON_string",
  "patient_links": [
    {
      "patient_id": "user_object_id",
      "patient_name": "Patient Name"
    }
  ],
  "patient_id": "legacy_patient_id",
  "patient_name": "legacy_patient_name",
  "created_at": ISODate
}
```

**Indexes**:
- `email` (unique)
- `_id` (primary)

---

### 2. **guardians** Collection
**Purpose**: Stores guardian/helper account information (can have multiple guardians per patient, max 2)

**Document Structure**:
```json
{
  "_id": ObjectId,
  "email": "guardian@example.com",
  "password": "hashed_password",
  "full_name": "Jane Doe",
  "role": "Guardian",
  "patient_links": [
    {
      "patient_id": "user_object_id",
      "patient_name": "Patient Name"
    }
  ],
  "patient_id": "legacy_patient_id",
  "patient_name": "legacy_patient_name",
  "created_at": ISODate
}
```

**Constraints**:
- Maximum 2 guardians per patient
- Email must be unique

---

### 3. **caregivers** Collection
**Purpose**: Stores caregiver account information (1 caregiver per patient maximum)

**Document Structure**:
```json
{
  "_id": ObjectId,
  "email": "caregiver@example.com",
  "password": "hashed_password",
  "full_name": "Care Provider",
  "role": "CareGiver",
  "agency": "Agency Name",
  "patient_links": [
    {
      "patient_id": "user_object_id",
      "patient_name": "Patient Name"
    }
  ],
  "patient_id": "legacy_patient_id",
  "patient_name": "legacy_patient_name",
  "created_at": ISODate
}
```

**Constraints**:
- Maximum 1 caregiver per patient
- Email must be unique

---

### 4. **people** Collection
**Purpose**: Stores known persons for facial recognition (friends/family of patient)

**Document Structure**:
```json
{
  "_id": ObjectId,
  "user_id": "patient_user_id",
  "name": "Ahmed Abdelkader",
  "relation": "Friend",
  "photo_url": "path_to_image",
  "voice": "path_to_voice",
  "permissions": "JSON_string",
  "face_embedding": "JSON_array_string",
  "voice_embedding": "JSON_array_string",
  "created_at": ISODate
}
```

**Purpose**: Face and voice embeddings are stored as JSON strings for ML recognition

---

### 5. **medications** Collection
**Purpose**: Stores patient medication information and schedule

**Document Structure**:
```json
{
  "_id": ObjectId,
  "user_id": "patient_user_id",
  "name": "Medication Name",
  "description": "Medication description",
  "photo_url": "image_url",
  "schedule": "JSON_string {times, frequency, dosage}",
  "is_active": true,
  "created_at": ISODate
}
```

---

### 6. **heartbeat_readings** Collection
**Purpose**: Stores all heart rate readings from sensors

**Document Structure**:
```json
{
  "_id": ObjectId,
  "patient_id": "patient_user_id",
  "heart_rate": 85,
  "threshold": 120,
  "status": "live",
  "alert_triggered": false,
  "recipients": [
    {
      "helper_id": "guardian_or_caregiver_id",
      "helper_name": "Jane Doe",
      "role": "Guardian"
    }
  ],
  "source": "sensor|manual_check",
  "recorded_at": ISODate,
  "updated_at": ISODate
}
```

**Purpose**: Time-series data for heart rate monitoring

---

### 7. **heartbeat_latest** Collection
**Purpose**: Stores only the latest heart rate reading per patient (for efficient polling)

**Document Structure**:
```json
{
  "_id": ObjectId,
  "patient_id": "patient_user_id",
  "heart_rate": 85,
  "threshold": 120,
  "status": "alert_triggered|live",
  "alert_triggered": false,
  "recipients": [...],
  "source": "sensor|manual_check",
  "recorded_at": ISODate,
  "updated_at": ISODate
}
```

**Update Strategy**: `upsert=True` - Updates existing or creates new

---

### 8. **heartbeat_alerts** Collection
**Purpose**: Stores triggered heart rate alerts for notification

**Document Structure**:
```json
{
  "_id": ObjectId,
  "patient_id": "patient_user_id",
  "heart_rate": 125,
  "threshold": 120,
  "triggered_at": ISODate,
  "recipients": [
    {
      "helper_id": "guardian_or_caregiver_id",
      "helper_name": "Jane Doe",
      "role": "Guardian"
    }
  ],
  "status": "triggered"
}
```

---

## Dependencies & Framework Info

**Key Python Packages**:
```
FastAPI==0.135.2          # Web framework
pymongo==4.16.0          # MongoDB driver
pydantic==2.12.5         # Data validation
SQLAlchemy==2.0.48       # (Legacy - not actively used)
python-dotenv            # Environment variables
```

**API Routes** (`Backend/app/routes/`):
- `users.py` - User management (create, login, update, delete)
- `people.py` - Manage known persons for recognition
- `recognition.py` - Face/voice recognition endpoints
- `heartbeat.py` - Heart rate monitoring
- `ml_process.py` - ML processing pipelines

---

## Data Flow & Key Operations

### User Registration Flow
1. **Create User** → `users.insert_one(user_doc)`
2. **Create Guardian/Caregiver** → `guardians.insert_one(helper_doc)` OR `caregivers.insert_one(helper_doc)`
3. Bidirectional linking via `patient_links`

### Person Recognition Setup
1. Add person to `people` collection
2. Store face embedding → `people.face_embedding`
3. Store voice embedding → `people.voice_embedding`

### Heart Rate Monitoring
1. Receive reading → `record_heartbeat_sample()`
2. Evaluate threshold → `evaluate_heartbeat()`
3. Insert to `heartbeat_readings` (historical)
4. Update `heartbeat_latest` with upsert (recent)
5. If alert → Insert to `heartbeat_alerts` & notify recipients

---

## Important Notes for Integration

### Authentication
- Passwords stored in database (ensure proper hashing in your implementation)
- No JWT tokens currently stored in MongoDB

### Patient Links (New Schema)
- Supports one-to-many helpers per patient
- Backward compatible with legacy `patient_id` field
- Use `patient_links` array for new implementations

### Async Operations
- All MongoDB operations are **asynchronous**
- Use `await db.collection.operation()`
- Required Python 3.7+ with async/await support

### Default Thresholds
- **Heart Rate Alert Threshold**: 120 bpm
- **Sensor Stale Timeout**: 10 seconds

### Face/Voice Embeddings
- Stored as JSON strings in MongoDB
- Format: `JSON.stringify(numpy_array)` → stored as string
- Parse back: `JSON.parse(string) → numpy_array`

---

## Environment Setup

Create `.env` file in `Backend/` with:
```
MONGODB_URL=mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0
MONGODB_DB_NAME=Alzemora
```

---

## Database Connection Code Reference

**File**: `Backend/app/database.py`

```python
from pymongo import AsyncMongoClient

async def connect_to_mongo():
    client = AsyncMongoClient(MONGODB_URL)
    db = client[MONGODB_DB_NAME]
    return db

async def close_mongo_connection():
    await client.close()
```

---

## Summary for New Project Integration

When connecting this database to another project, you need:

1. **MongoDB Atlas Credentials**:
   - Connection String: `mongodb+srv://Alzemora:alzemora2026@cluster0.admj5gd.mongodb.net/?appName=Cluster0`
   - Database: `Alzemora`
   - Username: `Alzemora`
   - Password: `alzemora2026`

2. **Collections to Access**:
   - `users`, `guardians`, `caregivers`, `people`, `medications`
   - `heartbeat_readings`, `heartbeat_latest`, `heartbeat_alerts`

3. **Key Relationships**:
   - Patients (in `users`) ↔ Guardians/Caregivers (via `patient_links`)
   - Patients ↔ Known Persons (via `user_id` in `people`)
   - Patients ↔ Heart Rate Data (via `patient_id` in heartbeat collections)

4. **Important Constraints**:
   - Max 2 Guardians per patient
   - Max 1 Caregiver per patient
   - Email fields are unique per collection

5. **Driver Compatibility**:
   - Python: `pymongo`, `motor` (async)
   - Node.js: `mongodb` driver
   - Other languages: Check MongoDB official drivers
