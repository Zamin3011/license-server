from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from fastapi.responses import HTMLResponse
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

app = FastAPI()

ADMIN_PASSWORD = "zamin123"  # change this

# =========================
# FIREBASE INIT
# =========================

firebase_key_json = os.environ.get("FIREBASE_KEY")

if not firebase_key_json:
    raise Exception("FIREBASE_KEY not found in environment variables")

cred = credentials.Certificate(json.loads(firebase_key_json))
firebase_admin.initialize_app(cred)

db = firestore.client()

# =========================
# FIREBASE FUNCTIONS
# =========================

def get_license(key):
    doc = db.collection("licenses").document(key).get()
    return doc.to_dict() if doc.exists else None


def save_license(key, data):
    db.collection("licenses").document(key).set(data)


def delete_license_db(key):
    db.collection("licenses").document(key).delete()


def get_all_licenses():
    docs = db.collection("licenses").stream()
    return {doc.id: doc.to_dict() for doc in docs}

# =========================
# MODELS
# =========================

class LicenseRequest(BaseModel):
    license_key: str
    device_id: str
    device_name: str = "Unknown"


class AdminRequest(BaseModel):
    password: str
    key: str = None
    expiry: str = None

# =========================
# VALIDATION API
# =========================

@app.post("/api/validate")
def validate(data: LicenseRequest):

    lic = get_license(data.license_key)

    if not lic:
        return {"valid": False}

    # expiry check
    if datetime.strptime(lic["expiry"], "%Y-%m-%d") < datetime.now():
        return {"valid": False, "reason": "expired"}

    # device lock
    if lic.get("device_id") is None:
        lic["device_id"] = data.device_id
        lic["device_name"] = data.device_name
        save_license(data.license_key, lic)

    elif lic.get("device_id") != data.device_id:
        return {
            "valid": False,
            "reason": "device_mismatch",
            "device_name": lic.get("device_name", "Unknown")
        }

    return {
        "valid": True,
        "expiry": lic["expiry"]
    }

# =========================
# ADMIN AUTH
# =========================

def check_admin(password):
    return password == ADMIN_PASSWORD

# =========================
# ADMIN APIs
# =========================

@app.post("/admin/create")
def create_license(req: AdminRequest):

    if not check_admin(req.password):
        return {"error": "unauthorized"}

    save_license(req.key, {
        "expiry": req.expiry,
        "device_id": None,
        "device_name": None
    })

    return {"status": "created"}


@app.get("/admin/list")
def list_licenses(password: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    return get_all_licenses()


@app.post("/admin/delete")
def delete_license(req: AdminRequest):

    if not check_admin(req.password):
        return {"error": "unauthorized"}

    delete_license_db(req.key)

    return {"status": "deleted"}


@app.post("/admin/reset-device")
def reset_device(req: AdminRequest):

    if not check_admin(req.password):
        return {"error": "unauthorized"}

    lic = get_license(req.key)

    if lic:
        lic["device_id"] = None
        lic["device_name"] = None
        save_license(req.key, lic)

    return {"status": "reset"}


@app.get("/admin/stats")
def get_stats(password: str):

    if not check_admin(password):
        return {"error": "unauthorized"}

    db_data = get_all_licenses()

    total = len(db_data)
    active = 0
    expired = 0

    now = datetime.now()

    for lic in db_data.values():
        try:
            expiry = datetime.strptime(lic["expiry"], "%Y-%m-%d")
            if expiry >= now:
                active += 1
            else:
                expired += 1
        except:
            expired += 1

    return {
        "total": total,
        "active": active,
        "expired": expired
    }


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

            .stats {
                display: flex;
                gap: 15px;
                margin-bottom: 20px;
            }

            .stat-box {
                flex: 1;
                background: #1e293b;
                padding: 20px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            }

            .stat-box h2 {
                margin: 0;
                font-size: 28px;
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
            }

            button:hover {
                background: #2563eb;
            }

            .danger {
                background: #ef4444;
            }

            .secondary {
                background: #64748b;
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
        </style>
    </head>

    <body>

        <h1>🔐 License Dashboard</h1>

        <div class="stats">
            <div class="stat-box">
                <h2 id="total">0</h2>
                <p>Total Licenses</p>
            </div>
            <div class="stat-box">
                <h2 id="active">0</h2>
                <p>Active</p>
            </div>
            <div class="stat-box">
                <h2 id="expired">0</h2>
                <p>Expired</p>
            </div>
        </div>

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
                    <th>Device Name</th>
                    <th>Actions</th>
                </tr>
            </table>
        </div>

        <script>

        async function loadStats() {
            const password = document.getElementById("password").value;

            const res = await fetch("/admin/stats?password=" + password);
            const data = await res.json();

            document.getElementById("total").innerText = data.total || 0;
            document.getElementById("active").innerText = data.active || 0;
            document.getElementById("expired").innerText = data.expired || 0;
        }

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
            loadStats();
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
                        <td>${lic.device_name || "-"}</td>
                        <td>
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
            loadStats();
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
