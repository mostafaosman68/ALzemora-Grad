import logging
import os

from fastapi import FastAPI

from app.database import connect_to_mongo, close_mongo_connection
from app.routes import users, people, recognition, heartbeat, ml_process, medications, alerts
from app.services.heartbeat_bridge_service import run_heartbeat_bridge
from app.services.firebase_service import initialize_firebase

logger = logging.getLogger(__name__)

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()

    # Initialize Firebase for push notifications
    firebase_creds = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
    if firebase_creds and os.path.exists(firebase_creds):
        initialize_firebase(firebase_creds)
    else:
        # Try to use GOOGLE_APPLICATION_CREDENTIALS env var
        initialize_firebase()

    logger.info("[STARTUP] Heartbeat bridge waiting for the logged-in patient to activate it...")


@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()


app.include_router(users.router)
app.include_router(users.legacy_router)
app.include_router(people.router)
app.include_router(recognition.router)
app.include_router(heartbeat.router)
app.include_router(ml_process.router)
app.include_router(medications.router)
app.include_router(alerts.router)


@app.get("/")
def root():
    return {"message": "Backend is running with MongoDB"}