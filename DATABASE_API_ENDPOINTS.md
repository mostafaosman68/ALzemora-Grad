# Database API Endpoints Reference

## User Management Endpoints

### POST `/create-user`
**Description**: Register new patient, guardian, or caregiver
**Database Operations**:
- `db.users.find_one({email})` - Check if email exists (patients)
- `db.guardians.find_one({email})` - Check if email exists (guardians)
- `db.caregivers.find_one({email})` - Check if email exists (caregivers)
- `db.users.insert_one(user_doc)` - Insert patient record
- `db.guardians.insert_one(helper_doc)` OR `db.caregivers.insert_one(helper_doc)` - Insert helper
- Count validation: `db.guardians.count_documents(query)` - Max 2 per patient
- Count validation: `db.caregivers.count_documents(query)` - Max 1 per patient

**Data Written**:
- User: email, password, full_name, age, role, created_at, patient_links
- Guardian/Caregiver: email, password, full_name, role, patient_id, patient_links

---

### POST `/login`
**Description**: Authenticate user (patient, guardian, or caregiver)
**Database Operations**:
- `db.users.find_one({email})` - Check patients
- `db.guardians.find_one({email})` - Check guardians
- `db.caregivers.find_one({email})` - Check caregivers
- Password verification against stored hash

---

### GET `/get-user/{user_id}`
**Description**: Retrieve user profile
**Database Operations**:
- `db.users.find_one({"_id": ObjectId(user_id)})` - For patients
- `db.guardians.find_one({"_id": ObjectId(user_id)})` - For guardians
- `db.caregivers.find_one({"_id": ObjectId(user_id)})` - For caregivers
- `db.people.count_documents({"user_id": user_id})` - Friends count
- `db.medications.count_documents({"user_id": user_id})` - Medications count

---

### POST `/update-user`
**Description**: Update user profile (restricted to role)
**Database Operations**:
- `db.users.find_one({"_id": ObjectId(user_id)})` - Verify user
- `db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {...}})` - Update fields
- Updatable fields: profile_image, age, status, address, emergency_contacts, last_medical_report

---

### DELETE `/delete-user/{user_id}`
**Description**: Delete user account
**Database Operations**:
- `db.users.delete_one({"_id": ObjectId(user_id)})` - Delete patient
- `db.guardians.delete_one({"_id": ObjectId(user_id)})` - Delete guardian
- `db.caregivers.delete_one({"_id": ObjectId(user_id)})` - Delete caregiver

---

### GET `/list-users`
**Description**: List all users
**Database Operations**:
- `db.users.find()` - Get all patients
- Returns paginated results with profile_image, name, email, created_at

---

## Person/Friend Management Endpoints

### POST `/register-person`
**Description**: Add new known person (face + voice) for patient
**Database Operations**:
- `db.users.find_one({"_id": ObjectId(user_id)})` - Verify patient
- `db.people.find_one({"user_id": user_id, "name": name})` - Check duplicates
- Face embedding computation via InsightFace model
- Voice embedding computation via pretrained model
- `db.people.insert_one(person_doc)` - Store person record
- File save: `data/NewPersonImages/{sanitized_name}/`
- File save: `data/voices/{sanitized_name}/`

**Data Written**:
```json
{
  "user_id": "patient_id",
  "name": "Person Name",
  "relation": "Friend",
  "photo_url": "path_to_image",
  "voice": "path_to_voice",
  "face_embedding": "JSON_string_array",
  "voice_embedding": "JSON_string_array",
  "permissions": "JSON_string"
}
```

---

### GET `/get-person/{person_id}`
**Description**: Get details of known person
**Database Operations**:
- `db.people.find_one({"_id": ObjectId(person_id)})` - Retrieve person

---

### PUT `/update-person/{person_id}`
**Description**: Update person information
**Database Operations**:
- `db.people.update_one({"_id": ObjectId(person_id)}, {"$set": {...}})` - Update fields

---

### DELETE `/delete-person/{person_id}`
**Description**: Remove known person
**Database Operations**:
- `db.people.delete_one({"_id": ObjectId(person_id)})` - Delete person record

---

### GET `/get-people/{user_id}`
**Description**: Get all known people for a patient
**Database Operations**:
- `db.people.find({"user_id": user_id})` - Retrieve all associated persons

---

## Face & Voice Recognition Endpoints

### POST `/recognize-person`
**Description**: Identify person from face/voice
**Database Operations**:
- `db.people.find()` - Get ALL known people (queries all patients)
- Reads: `face_embedding`, `voice_embedding`
- Cosine similarity comparison (threshold: face=0.40, voice=0.45)
- Returns: Best match with similarity score

**Return Format**:
```json
{
  "recognized": true,
  "person_name": "Ahmed Abdelkader",
  "patient_id": "patient_object_id",
  "similarity": 0.92,
  "method": "face|voice"
}
```

---

## Heart Rate Monitoring Endpoints

### POST `/heartbeat/check`
**Description**: Submit manual heart rate check
**Database Operations**:
- `db.users.find_one({"_id": ObjectId(patient_id)})` - Verify patient exists
- Calls `record_heartbeat_sample()` which:
  - `db.heartbeat_readings.insert_one()` - Store reading
  - `db.heartbeat_latest.update_one(..., upsert=True)` - Update latest
  - If alert triggered: `db.heartbeat_alerts.insert_one()` - Store alert
  - Finds recipients via: `db.guardians.find()`, `db.caregivers.find()` - Notify helpers

**Data Written**:
- Reading: patient_id, heart_rate, threshold, status, source, recorded_at
- Latest: Same fields, upserted per patient
- Alert: patient_id, heart_rate, threshold, triggered_at, recipients, status

---

### GET `/heartbeat/live/{patient_id}`
**Description**: Get latest heart rate status
**Database Operations**:
- `db.heartbeat_latest.find_one({"patient_id": patient_id})` - Get current state
- Check staleness: `last_reading_time > current_time - 10_seconds`

**Return Format**:
```json
{
  "patient_id": "patient_id",
  "heart_rate": 85,
  "threshold": 120,
  "status": "live",
  "alert_triggered": false,
  "sensor_connected": true
}
```

---

### GET `/heartbeat/history/{patient_id}`
**Description**: Get heart rate history
**Database Operations**:
- `db.heartbeat_readings.find({"patient_id": patient_id}).sort("recorded_at", -1).limit(100)` - Last 100 readings

---

### GET `/heartbeat/alerts/{patient_id}`
**Description**: Get triggered alerts
**Database Operations**:
- `db.heartbeat_alerts.find({"patient_id": patient_id})` - All alerts for patient
- Returns: triggered_at, heart_rate, threshold, recipients

---

## Data Flow Examples

### Example 1: Patient Registration
```
POST /create-user
├── Check db.users for duplicate email
├── Insert into db.users {_id, email, password, full_name, created_at}
└── Return {user_id, message}
```

### Example 2: Register Known Person + Later Recognition
```
POST /register-person
├── Verify db.users exists
├── Compute face embedding (InsightFace model)
├── Compute voice embedding (pretrained model)
├── Insert into db.people {user_id, face_embedding, voice_embedding}
└── Save files to data/NewPersonImages and data/voices

POST /recognize-person
├── Load uploaded image/audio
├── Compute embedding
├── db.people.find() - Get ALL known embeddings
├── Compare via cosine_similarity (threshold: 0.40 for face)
└── Return best match with patient_id
```

### Example 3: Heart Rate Alert Flow
```
POST /heartbeat/check {patient_id, heart_rate: 125, threshold: 120}
├── record_heartbeat_sample()
│  ├── db.heartbeat_readings.insert_one() - Store reading
│  ├── db.heartbeat_latest.update_one(..., upsert=True) - Update latest
│  ├── Alert triggered (125 >= 120)
│  │  ├── db.heartbeat_alerts.insert_one() - Store alert
│  │  ├── find_notifiable_helpers() queries:
│  │  │  ├── db.guardians.find() - Get linked guardians
│  │  │  ├── db.caregivers.find() - Get linked caregivers
│  │  │  └── Build recipients list
│  │  └── Send notifications to recipients
│  └── Return {alert_triggered: true, recipients: [...]}
```

---

## Important Data Constraints

| Operation | Constraint | Query |
|---|---|---|
| Email uniqueness (users) | Email must be unique | `find_one({email})` before insert |
| Email uniqueness (guardians) | Email must be unique per collection | `find_one({email})` before insert |
| Email uniqueness (caregivers) | Email must be unique per collection | `find_one({email})` before insert |
| Guardians per patient | Max 2 | `count_documents(query) < 2` |
| Caregivers per patient | Max 1 | `count_documents(query) < 1` |
| Person duplicate | Avoid name duplicates per patient | `find_one({user_id, name})` |

---

## Performance Considerations

1. **Heart Rate Recognition**: Queries all `people` records across all patients - could be slow with large datasets
2. **Bulk Operations**: Use batch inserts for better performance
3. **Pagination**: List endpoints should implement skip/limit
4. **Indexing**: Add indexes for frequently queried fields:
   - `users.email` (unique)
   - `guardians.email` (unique)
   - `caregivers.email` (unique)
   - `people.user_id`
   - `medications.user_id`
   - `heartbeat_readings.patient_id` + `recorded_at`

---

## Integration Checklist for Another Project

- [ ] Install dependencies: `pymongo`, `motor` (for async)
- [ ] Set environment variables: MONGODB_URL, MONGODB_DB_NAME
- [ ] Implement connection: AsyncMongoClient setup
- [ ] Create collection models/interfaces
- [ ] Implement authentication (currently plain password - consider hashing)
- [ ] Add query validation and error handling
- [ ] Test connectivity to collections
- [ ] Implement indexes for performance
- [ ] Handle ObjectId conversions (string ↔ ObjectId)
- [ ] Test with sample data from production database
