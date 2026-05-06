import os
from dotenv import load_dotenv
from pymongo import AsyncMongoClient

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "elder_assist")

print(f"[DATABASE] MONGODB_URL: {MONGODB_URL}")
print(f"[DATABASE] MONGODB_DB_NAME: {MONGODB_DB_NAME}")

client = None
db = None


async def connect_to_mongo():
    global client, db
    try:
        client = AsyncMongoClient(MONGODB_URL)
        db = client[MONGODB_DB_NAME]
        print(f"[DATABASE] Connected to MongoDB: {MONGODB_DB_NAME}")
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to connect: {str(e)}")


async def close_mongo_connection():
    global client
    if client is not None:
        await client.close()
        print("[DATABASE] MongoDB connection closed")


def get_db():
    if db is None:
        print("[DATABASE WARNING] Database not initialized!")
    return db