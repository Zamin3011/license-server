from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

licenses = {
    "ZAMIN-TEST-123": {
        "expiry": "2026-12-31",
        "device_id": None
    }
}

class LicenseRequest(BaseModel):
    license_key: str
    device_id: str

@app.post("/api/validate")
def validate(data: LicenseRequest):

    lic = licenses.get(data.license_key)

    if not lic:
        return {"valid": False}

    # expiry check
    if datetime.strptime(lic["expiry"], "%Y-%m-%d") < datetime.now():
        return {"valid": False, "reason": "expired"}

    # device lock
    if lic["device_id"] is None:
        lic["device_id"] = data.device_id
    elif lic["device_id"] != data.device_id:
        return {"valid": False, "reason": "device_mismatch"}

    return {"valid": True}