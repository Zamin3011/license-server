from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import json
import os
from fastapi.responses import HTMLResponse

app = FastAPI()

ADMIN_PASSWORD = "zamin123"  # change this
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

# =========================
# MODELS
# =========================

class LicenseRequest(BaseModel):
    license_key: str
    device_id: str

class AdminRequest(BaseModel):
    password: str
    key: str = None
    expiry: str = None

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

# =========================
# ADMIN AUTH
# =========================

def check_admin(password):
    return password == ADMIN_PASSWORD

# =========================
# ADMIN APIs (FIXED)
# =========================

@app.post("/admin/create")
def create_license(req: AdminRequest):

    if not check_admin(req.password):
        return {"error": "unauthorized"}

    db = load_db()

    db[req.key] = {
        "expiry": req.expiry,
        "device_id": None
    }

    save_db(db)

    return {"status": "created"}

@app.get("/admin/list")
def list_licenses(password: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    return load_db()

@app.post("/admin/delete")
def delete_license(req: AdminRequest):

    if not check_admin(req.password):
        return {"error": "unauthorized"}

    db = load_db()

    if req.key in db:
        del db[req.key]
        save_db(db)

    return {"status": "deleted"}

@app.post("/admin/reset-device")
def reset_device(req: AdminRequest):

    if not check_admin(req.password):
        return {"error": "unauthorized"}

    db = load_db()

    if req.key in db:
        db[req.key]["device_id"] = None
        save_db(db)

    return {"status": "reset"}

# =========================
# ADMIN UI PANEL
# =========================

@app.get("/admin", response_class=HTMLResponse)
def admin_panel():

    return """
    <html>
    <head>
        <title>License Admin Panel</title>
        <style>
            body { font-family: Arial; background:#111; color:white; padding:20px; }
            input, button { padding:8px; margin:5px; }
            table { border-collapse: collapse; width:100%; margin-top:20px; }
            th, td { border:1px solid #444; padding:8px; text-align:left; }
            th { background:#222; }
            button { cursor:pointer; }
        </style>
    </head>
    <body>

        <h2>🔐 License Admin Panel</h2>

        <h3>Create License</h3>
        <input id="password" placeholder="Admin Password">
        <input id="key" placeholder="License Key">
        <input id="expiry" placeholder="YYYY-MM-DD">
        <button onclick="createLicense()">Create</button>

        <h3>All Licenses</h3>
        <button onclick="loadLicenses()">Refresh</button>

        <table id="table">
            <tr>
                <th>Key</th>
                <th>Expiry</th>
                <th>Device</th>
                <th>Actions</th>
            </tr>
        </table>

        <script>

        async function createLicense() {
            const password = document.getElementById("password").value;
            const key = document.getElementById("key").value;
            const expiry = document.getElementById("expiry").value;

            await fetch("/admin/create", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({password, key, expiry})
            });

            loadLicenses();
        }

        async function loadLicenses() {
            const password = document.getElementById("password").value;

            const res = await fetch("/admin/list?password=" + password);
            const data = await res.json();

            const table = document.getElementById("table");
            table.innerHTML = `
                <tr>
                    <th>Key</th>
                    <th>Expiry</th>
                    <th>Device</th>
                    <th>Actions</th>
                </tr>
            `;

            for (let key in data) {
                const lic = data[key];

                table.innerHTML += `
                    <tr>
                        <td>${key}</td>
                        <td>${lic.expiry}</td>
                        <td>${lic.device_id || "-"}</td>
                        <td>
                            <button onclick="deleteLicense('${key}')">Delete</button>
                            <button onclick="resetDevice('${key}')">Reset</button>
                        </td>
                    </tr>
                `;
            }
        }

        async function deleteLicense(key) {
            const password = document.getElementById("password").value;

            await fetch("/admin/delete", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({password, key})
            });

            loadLicenses();
        }

        async function resetDevice(key) {
            const password = document.getElementById("password").value;

            await fetch("/admin/reset-device", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({password, key})
            });

            loadLicenses();
        }

        </script>

    </body>
    </html>
    """