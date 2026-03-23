from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import json
import os

ADMIN_PASSWORD = "zamin123"  # change this

app = FastAPI()

DB_FILE = "licenses.json"


# =========================
# DATABASE FUNCTIONS
# =========================

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


class LicenseRequest(BaseModel):
    license_key: str
    device_id: str


# =========================
# VALIDATION API
# =========================

@app.post("/api/validate")
def validate(data: LicenseRequest):

    db = load_db()
    lic = db.get(data.license_key)

    if not lic:
        return {"valid": False}

    # expiry check
    if datetime.strptime(lic["expiry"], "%Y-%m-%d") < datetime.now():
        return {"valid": False, "reason": "expired"}

    # device lock
    if lic.get("device_id") is None:
        lic["device_id"] = data.device_id
        db[data.license_key] = lic
        save_db(db)

    elif lic.get("device_id") != data.device_id:
        return {"valid": False, "reason": "device_mismatch"}

    return {"valid": True}


def check_admin(password):
    return password == ADMIN_PASSWORD


@app.post("/admin/create")
def create_license(password: str, key: str, expiry: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    db = load_db()

    db[key] = {
        "expiry": expiry,
        "device_id": None
    }

    save_db(db)

    return {"status": "license created"}


@app.get("/admin/list")
def list_licenses(password: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    return load_db()


@app.post("/admin/delete")
def delete_license(password: str, key: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    db = load_db()

    if key in db:
        del db[key]
        save_db(db)

    return {"status": "deleted"}


@app.post("/admin/reset-device")
def reset_device(password: str, key: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    db = load_db()

    if key in db:
        db[key]["device_id"] = None
        save_db(db)

    return {"status": "device reset"}


