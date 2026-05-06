from fastapi import FastAPI
from app.database import connect_to_mongo, close_mongo_connection
from app.routes import users, people, recognition, heartbeat, ml_process, medications

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()


@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()


app.include_router(users.router)
app.include_router(people.router)
app.include_router(recognition.router)
app.include_router(heartbeat.router)
app.include_router(ml_process.router)
app.include_router(medications.router)


@app.get("/")
def root():
    return {"message": "Backend is running with MongoDB"}