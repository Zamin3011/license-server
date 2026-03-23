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
            body {
                font-family: 'Segoe UI', sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                margin: 0;
                padding: 20px;
            }

            h1 {
                margin-bottom: 20px;
            }

            .card {
                background: #1e293b;
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 20px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            }

            input {
                padding: 10px;
                border-radius: 8px;
                border: none;
                margin-right: 10px;
                background: #334155;
                color: white;
            }

            button {
                padding: 10px 15px;
                border-radius: 8px;
                border: none;
                background: #3b82f6;
                color: white;
                cursor: pointer;
                transition: 0.2s;
            }

            button:hover {
                background: #2563eb;
            }

            .danger {
                background: #ef4444;
            }

            .danger:hover {
                background: #dc2626;
            }

            .secondary {
                background: #64748b;
            }

            .secondary:hover {
                background: #475569;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }

            th, td {
                padding: 12px;
                text-align: left;
            }

            th {
                background: #334155;
            }

            tr {
                border-bottom: 1px solid #334155;
            }

            .actions button {
                margin-right: 5px;
            }
        </style>
    </head>

    <body>

        <h1>🔐 License Admin Dashboard</h1>

        <div class="card">
            <h3>Create License</h3>
            <input id="password" placeholder="Admin Password">
            <input id="key" placeholder="License Key">
            <input id="expiry" placeholder="YYYY-MM-DD">
            <button onclick="createLicense()">Create</button>
        </div>

        <div class="card">
            <h3>All Licenses</h3>
            <button class="secondary" onclick="loadLicenses()">Refresh</button>

            <table id="table">
                <tr>
                    <th>Key</th>
                    <th>Expiry</th>
                    <th>Device</th>
                    <th>Actions</th>
                </tr>
            </table>
        </div>

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
                        <td class="actions">
                            <button class="danger" onclick="deleteLicense('${key}')">Delete</button>
                            <button class="secondary" onclick="resetDevice('${key}')">Reset</button>
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