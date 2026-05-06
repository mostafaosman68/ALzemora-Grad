from fastapi import APIRouter, Form, Body
from typing import Optional
from bson import ObjectId
from app.database import get_db

router = APIRouter()

MAX_GUARDIANS_PER_PATIENT = 2
MAX_CAREGIVERS_PER_PATIENT = 1


def normalize_patient_links(helper_account: dict):
    links = helper_account.get("patient_links")
    normalized = []
    if isinstance(links, list) and len(links) > 0:
        for link in links:
            pid = link.get("patient_id")
            pname = link.get("patient_name")
            if pid:
                normalized.append({"patient_id": str(pid), "patient_name": pname})

    # Backward compatibility for old single-patient documents.
    # Also keeps the active patient in the list if older data drifted.
    legacy_pid = helper_account.get("patient_id")
    if legacy_pid:
        legacy_link = {
            "patient_id": str(legacy_pid),
            "patient_name": helper_account.get("patient_name"),
        }
        if not any(link.get("patient_id") == legacy_link["patient_id"] for link in normalized):
            normalized.append(legacy_link)

    return normalized


async def get_patient_helper_counts(db, patient_id_value: str):
    query = {
        "$or": [
            {"patient_id": patient_id_value},
            {"patient_links.patient_id": patient_id_value},
        ]
    }
    guardians_count = await db.guardians.count_documents(query)
    caregivers_count = await db.caregivers.count_documents(query)
    return guardians_count, caregivers_count


# ─── Signup ───────────────────────────────────────────────
@router.post("/create-user")
async def create_user(
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    patient_name: str = Form(None),
    age: int = Form(None),
    status: str = Form(None),
    address: str = Form(None),
    editor_user_id: Optional[str] = Form(None),
    editor_role: Optional[str] = Form(None),
):
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed. Backend server error."}
        
        role = role.strip()
        email = email.strip().lower()
        
        print(f"[SIGNUP] Creating {role} account: {email}")

        # ── Guardian / CareGiver ───────────────────────────────
        if role in ("Guardian", "CareGiver"):
            if not patient_name or not patient_name.strip():
                return {"error": "Patient name is required for Guardian and CareGiver accounts"}

            patient = await db.users.find_one(
                {"full_name": {"$regex": f"^{patient_name.strip()}$", "$options": "i"}}
            )
            if not patient:
                return {"error": f"No patient named '{patient_name}' found. Please check the name and try again."}

            patient_id_value = str(patient["_id"])
            guardians_count, caregivers_count = await get_patient_helper_counts(db, patient_id_value)

            if role == "Guardian" and guardians_count >= MAX_GUARDIANS_PER_PATIENT:
                return {"error": "This patient already has the maximum number of guardians (2)"}
            if role == "CareGiver" and caregivers_count >= MAX_CAREGIVERS_PER_PATIENT:
                return {"error": "This patient already has a caregiver assigned"}

            collection = db.guardians if role == "Guardian" else db.caregivers
            existing = await collection.find_one({"email": email})
            if existing:
                return {"error": "An account with this email already exists"}

            doc = {
                "email": email,
                "password": password,
                "full_name": full_name.strip(),
                "role": role,
                "patient_name": patient["full_name"],
                "patient_id": patient_id_value,
                "patient_links": [
                    {
                        "patient_id": patient_id_value,
                        "patient_name": patient["full_name"],
                    }
                ],
                "age": age,
                "address": address,
            }

            result = await collection.insert_one(doc)
            print(f"[SIGNUP] {role} account created: {result.inserted_id}")

            return {
                "message": f"{role} account created successfully",
                "user_id": str(result.inserted_id),
                "email": email,
                "full_name": full_name.strip(),
                "role": role,
                "patient_name": patient["full_name"],
                "patient_id": patient_id_value,
                "patient_links": doc["patient_links"],
                "age": age,
            }

        # ── Patient (User) ─────────────────────────────────────
        existing = await db.users.find_one({"email": email})
        if existing:
            return {"error": "A user with this email already exists"}

        user_doc = {
            "email": email,
            "password": password,
            "full_name": full_name.strip(),
            "role": "User",
            "age": age,
            "status": status,
            "address": address,
            "emergency_contacts": None,
            "dnr_status": False,
        }

        result = await db.users.insert_one(user_doc)
        print(f"[SIGNUP] User account created: {result.inserted_id}")

        linked_patient_links = None
        if editor_user_id and editor_role and editor_role.strip() in ("Guardian", "CareGiver"):
            helper_role = editor_role.strip()
            helper_collection = db.guardians if helper_role == "Guardian" else db.caregivers
            helper_account = await helper_collection.find_one({"_id": ObjectId(editor_user_id)})

            if helper_account:
                merged_links = normalize_patient_links(helper_account)
                new_link = {
                    "patient_id": str(result.inserted_id),
                    "patient_name": full_name.strip(),
                }
                if not any(link.get("patient_id") == new_link["patient_id"] for link in merged_links):
                    merged_links.append(new_link)

                await helper_collection.update_one(
                    {"_id": ObjectId(editor_user_id)},
                    {
                        "$set": {
                            "patient_links": merged_links,
                            "patient_id": str(result.inserted_id),
                            "patient_name": full_name.strip(),
                        },
                    },
                )

                helper_after_update = await helper_collection.find_one({"_id": ObjectId(editor_user_id)})
                linked_patient_links = normalize_patient_links(helper_after_update or helper_account)

        return {
            "message": "User created successfully",
            "user_id": str(result.inserted_id),
            "email": email,
            "full_name": full_name.strip(),
            "role": "User",
            "age": age,
            "patient_name": full_name.strip(),
            "patient_id": str(result.inserted_id),
            "patient_links": linked_patient_links,
        }
    
    except Exception as e:
        print(f"[SIGNUP ERROR] {str(e)}")
        return {"error": f"Signup error: {str(e)}"}


# ─── Login ─────────────────────────────────────────────────
@router.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    patient_name: Optional[str] = Form(None),
):
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed. Backend server error."}
        
        email = email.strip().lower()
        role = role.strip()

        # Map role to collection
        collection_map = {
            "User":      db.users,
            "Guardian":  db.guardians,
            "CareGiver": db.caregivers,
        }

        collection = collection_map.get(role)
        if collection is None:
            return {"error": "Invalid account type selected"}

        # Search for user
        user = await collection.find_one({"email": email})

        if not user:
            print(f"[LOGIN] {role} account not found: {email}")
            return {"error": f"No {role} account found with this email"}

        # Check password
        if user["password"] != password:
            print(f"[LOGIN] Incorrect password for: {email}")
            return {"error": "Incorrect password"}

        # For helpers, verify the patient name matches
        selected_patient_id = user.get("patient_id")
        selected_patient_name = user.get("patient_name")
        patient_links = []

        if role in ("Guardian", "CareGiver"):
            patient_links = normalize_patient_links(user)
            if not patient_links:
                return {"error": "No patient linked to this account"}

            if patient_name and patient_name.strip():
                requested_name = patient_name.strip().lower()
                matched_link = next(
                    (link for link in patient_links if (link.get("patient_name") or "").lower() == requested_name),
                    None,
                )
                if not matched_link:
                    return {"error": "Patient name does not match your linked patients"}
                selected_patient_id = matched_link.get("patient_id")
                selected_patient_name = matched_link.get("patient_name")
            else:
                # If no patient is provided, default to first linked patient
                selected_patient_id = patient_links[0].get("patient_id")
                selected_patient_name = patient_links[0].get("patient_name")

        print(f"[LOGIN] {role} login successful: {email}")
        return {
            "message": "Login successful",
            "user_id": str(user["_id"]),
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user.get("role", role),
            "patient_name": selected_patient_name,
            "patient_id": selected_patient_id,
            "patient_links": patient_links,
            "age": user.get("age"),
            "status": user.get("status"),
            "address": user.get("address"),
        }
    
    except Exception as e:
        print(f"[LOGIN ERROR] {str(e)}")
        return {"error": f"Login error: {str(e)}"}


# ─── Get linked patients for helper account ──────────────
@router.get("/helper-patients")
async def get_helper_patients(user_id: str, role: str):
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed. Backend server error."}

        role = role.strip()
        if role not in ("Guardian", "CareGiver"):
            return {"error": "Invalid role. Must be Guardian or CareGiver"}

        collection = db.guardians if role == "Guardian" else db.caregivers
        helper = await collection.find_one({"_id": ObjectId(user_id)})
        if not helper:
            return {"error": "Helper account not found"}

        patient_links = normalize_patient_links(helper)
        if not patient_links:
            return {
                "user_id": str(helper["_id"]),
                "role": role,
                "patient_links": [],
                "patient_id": None,
                "patient_name": None,
                "count": 0,
            }

        active_patient_id = helper.get("patient_id")
        active_patient_name = helper.get("patient_name")

        # Keep active patient consistent with available links
        if not active_patient_id or not any(link.get("patient_id") == active_patient_id for link in patient_links):
            active_patient_id = patient_links[0].get("patient_id")
            active_patient_name = patient_links[0].get("patient_name")

        return {
            "user_id": str(helper["_id"]),
            "role": role,
            "patient_links": patient_links,
            "patient_id": active_patient_id,
            "patient_name": active_patient_name,
            "count": len(patient_links),
        }

    except Exception as e:
        print(f"[HELPER PATIENTS ERROR] {str(e)}")
        return {"error": f"Error fetching helper patients: {str(e)}"}


# ─── Get user by name ─────────────────────────────────────
@router.get("/get-user-by-name")
async def get_user_by_name(name: str):
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed"}
        
        user = await db.users.find_one(
            {"full_name": {"$regex": f"^{name.strip()}$", "$options": "i"}}
        )
        
        if not user:
            print(f"[GET USER] No user found with name: {name}")
            return {"error": f"No user found with name '{name}'"}
        
        print(f"[GET USER] Found user: {user.get('full_name')}")
        return {
            "user_id": str(user["_id"]),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "age": user.get("age"),
            "status": user.get("status"),
            "address": user.get("address"),
            "emergency_contact": user.get("emergency_contacts"),
            "dnr_status": user.get("dnr_status"),
            "role": user.get("role", "User"),
        }
    except Exception as e:
        print(f"[GET USER ERROR] {str(e)}")
        return {"error": f"Error fetching user: {str(e)}"}


# ─── Update user profile ───────────────────────────────────
@router.post("/update-user")
async def update_user(
    data: dict = Body(...),
):
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed. Backend server error."}

        user_id = data.get("user_id")
        role = data.get("role")
        editor_role = data.get("editor_role", role)
        patient_user_id = data.get("patient_user_id")
        if not user_id or not role:
            return {"error": "user_id and role are required"}

        if editor_role not in ("Guardian", "CareGiver"):
            return {"error": "Only guardians and caregivers can edit patient profiles"}

        if not patient_user_id:
            return {"error": "patient_user_id is required for profile updates"}

        collection = db.users

        update_fields = {}
        if data.get("full_name") is not None:
            update_fields["full_name"] = data["full_name"].strip()
        if data.get("age") is not None:
            update_fields["age"] = data["age"]
        if data.get("status") is not None:
            update_fields["status"] = data["status"].strip()
        if data.get("address") is not None:
            update_fields["address"] = data["address"].strip()
        if data.get("emergency_contact") is not None:
            update_fields["emergency_contacts"] = data["emergency_contact"].strip()
        if data.get("dnr_status") is not None:
            update_fields["dnr_status"] = data["dnr_status"]

        if not update_fields:
            return {"error": "No profile fields provided to update"}

        result = await collection.update_one({"_id": ObjectId(patient_user_id)}, {"$set": update_fields})
        if result.matched_count == 0:
            return {"error": f"User {patient_user_id} not found"}

        updated_user = await collection.find_one({"_id": ObjectId(patient_user_id)})
        if not updated_user:
            return {"error": "Failed to fetch updated user data"}

        return {
            "message": "Profile updated successfully",
            "user": {
                "user_id": str(updated_user["_id"]),
                "email": updated_user.get("email"),
                "full_name": updated_user.get("full_name"),
                "age": updated_user.get("age"),
                "status": updated_user.get("status"),
                "address": updated_user.get("address"),
                "emergency_contact": updated_user.get("emergency_contacts"),
                "dnr_status": updated_user.get("dnr_status"),
                "role": updated_user.get("role", role),
            },
        }

    except Exception as e:
        print(f"[UPDATE USER ERROR] {str(e)}")
        return {"error": f"Error updating user: {str(e)}"}


# ─── Get all users ─────────────────────────────────────────
@router.get("/users")
async def get_users():
    db = get_db()

    users = []
    async for user in db.users.find():
        user["_id"] = str(user["_id"])
        users.append(user)

    return {"count": len(users), "users": users}


# ─── Get user statistics (friends, meds, status) ─────────────
@router.get("/user-stats/{user_id}")
async def get_user_stats(user_id: str):
    """
    Get dashboard statistics for a user:
    - Number of friends/people
    - Number of medications
    - User status (Active/Inactive)
    """
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed"}

        # Get user
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return {"error": f"User {user_id} not found"}

        # Count friends/people for this user
        friends_count = await db.people.count_documents({"user_id": user_id})

        # Count medications for this user
        meds_count = await db.medications.count_documents({"user_id": user_id})

        # Get user status (Active/Inactive based on status field)
        status = user.get("status", "Active")
        if not status:
            status = "Active"

        print(f"[STATS] User {user.get('full_name', user_id)}: Friends={friends_count}, Meds={meds_count}, Status={status}")

        return {
            "friends_count": friends_count,
            "meds_count": meds_count,
            "status": status
        }

    except Exception as e:
        print(f"[STATS ERROR] {str(e)}")
        return {"error": f"Error fetching user statistics: {str(e)}"}


# ─── Link existing patient to guardian/caregiver ───────────
@router.post("/link-existing-patient")
async def link_existing_patient(
    editor_user_id: str = Form(...),
    editor_role: str = Form(...),
    patient_email: str = Form(...),
    patient_password: str = Form(...),
):
    try:
        db = get_db()
        if db is None:
            return {"error": "Database connection failed. Backend server error."}
        
        role = editor_role.strip()
        if role not in ("Guardian", "CareGiver"):
            return {"error": "Invalid role. Must be Guardian or CareGiver"}
        
        patient_email = patient_email.strip().lower()
        
        print(f"[LINK PATIENT] Linking logged-in {role} {editor_user_id} to patient {patient_email}")

        helper_collection = db.guardians if role == "Guardian" else db.caregivers
        helper_account = await helper_collection.find_one({"_id": ObjectId(editor_user_id)})
        if not helper_account:
            return {"error": "Logged in account was not found. Please sign in again."}

        current_links = normalize_patient_links(helper_account)

        # Find the patient
        patient = await db.users.find_one({"email": patient_email})
        if not patient:
            return {"error": f"No patient found with email '{patient_email}'"}

        if patient.get("password") != patient_password:
            return {"error": "Incorrect patient credentials"}

        if any(link.get("patient_id") == str(patient["_id"]) for link in current_links):
            return {"error": "This patient is already linked to your account"}

        patient_id_value = str(patient["_id"])
        guardians_count, caregivers_count = await get_patient_helper_counts(db, patient_id_value)

        if role == "Guardian" and guardians_count >= MAX_GUARDIANS_PER_PATIENT:
            return {"error": "This patient already has the maximum number of guardians (2)"}
        if role == "CareGiver" and caregivers_count >= MAX_CAREGIVERS_PER_PATIENT:
            return {"error": "This patient already has a caregiver assigned"}

        current_links.append(
            {
                "patient_id": str(patient["_id"]),
                "patient_name": patient["full_name"],
            }
        )

        await helper_collection.update_one(
            {"_id": ObjectId(editor_user_id)},
            {
                "$set": {
                    "patient_links": current_links,
                    "patient_name": patient["full_name"],
                    "patient_id": str(patient["_id"]),
                }
            },
        )

        print(f"[LINK PATIENT] {role} account {editor_user_id} linked to patient {patient['_id']}")

        updated_helper = await helper_collection.find_one({"_id": ObjectId(editor_user_id)})
        updated_links = normalize_patient_links(updated_helper or helper_account)

        return {
            "message": f"{role} account linked to patient successfully",
            "user_id": str(helper_account["_id"]),
            "email": helper_account.get("email"),
            "full_name": helper_account.get("full_name"),
            "role": role,
            "patient_name": patient["full_name"],
            "patient_id": str(patient["_id"]),
            "patient_links": updated_links,
        }
    
    except Exception as e:
        print(f"[LINK PATIENT ERROR] {str(e)}")
        return {"error": f"Error linking patient: {str(e)}"}