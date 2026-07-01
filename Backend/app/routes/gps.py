import asyncio
import json
import urllib.request
from urllib.error import URLError

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_db

router = APIRouter(prefix="/gps", tags=["gps"])

_GPS_DOC_ID = "pi_location"


def _fetch_ip_location() -> dict:
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        lat_str, lon_str = data.get("loc", "0,0").split(",")
        return {
            "lat": float(lat_str),
            "lon": float(lon_str),
            "city": data.get("city", "Unknown"),
            "region": data.get("region", ""),
            "country": data.get("country", ""),
            "ip": data.get("ip", ""),
            "source": "ip",
        }
    except (URLError, ValueError) as exc:
        raise RuntimeError(f"IP geolocation failed: {exc}") from exc


@router.get("/location")
async def get_pi_location():
    """Returns the manually-pinned location if set, otherwise falls back to IP geolocation."""
    db = get_db()
    if db is not None:
        saved = await db.pi_location.find_one({"_id": _GPS_DOC_ID})
        if saved:
            return {
                "lat": saved["lat"],
                "lon": saved["lon"],
                "city": saved.get("city", ""),
                "region": saved.get("region", ""),
                "country": saved.get("country", ""),
                "ip": "",
                "source": "manual",
            }

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _fetch_ip_location)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class LocationPin(BaseModel):
    lat: float
    lon: float
    city: str = ""
    region: str = ""
    country: str = ""


@router.post("/set")
async def set_pi_location(body: LocationPin):
    """Save a manually-corrected location for the Pi (overwrites any previous pin)."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    doc = {
        "_id": _GPS_DOC_ID,
        "lat": body.lat,
        "lon": body.lon,
        "city": body.city,
        "region": body.region,
        "country": body.country,
    }
    await db.pi_location.replace_one({"_id": _GPS_DOC_ID}, doc, upsert=True)
    return {"message": "Location saved", **doc}


@router.delete("/set")
async def clear_pi_location():
    """Remove the manual pin and revert to IP geolocation."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await db.pi_location.delete_one({"_id": _GPS_DOC_ID})
    return {"message": "Manual location cleared — will use IP geolocation"}
