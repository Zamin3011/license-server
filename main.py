from fastapi import FastAPI, Request
from pydantic import BaseModel
from datetime import datetime
from fastapi.responses import HTMLResponse
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

API_SECRET = os.environ.get("API_SECRET")

if not API_SECRET:
    raise Exception("API_SECRET not set")

app = FastAPI()

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
# MODELS
# =========================

class LicenseRequest(BaseModel):
    license_key: str
    device_id: str
    device_name: str = "Unknown"


class AdminRequest(BaseModel):
    key: str
    expiry: str
    distributor_id: str = None
    max_devices: int = 1


# =========================
# VALIDATION API
# =========================

@app.post("/api/validate")
def validate(data: LicenseRequest, request: Request):

    # 🔐 API SECURITY
    if request.headers.get("x-api-key") != API_SECRET:
        return {"valid": False, "error": "unauthorized"}

    # ❗ basic tamper protection
    if len(data.license_key) < 10:
        return {"valid": False, "message": "Invalid key format"}

    lic_ref = db.collection("license_keys").document(data.license_key)
    lic_doc = lic_ref.get()

    if not lic_doc.exists:
        return {"valid": False, "message": "Invalid key"}

    lic = lic_doc.to_dict()

    # 🔥 DISTRIBUTOR CHECK
    dist_id = lic.get("distributor_id")

    dist = None

    if dist_id:
        dist_doc = db.collection("distributors").document(dist_id).get()

        if not dist_doc.exists:
            return {"valid": False, "message": "Distributor not found"}

        dist = dist_doc.to_dict()

        if not dist.get("active", True):
            return {"valid": False, "message": "Distributor disabled"}

        if dist.get("expires_at"):
            try:
                dist_expiry = datetime.strptime(dist["expires_at"], "%Y-%m-%d")
                if dist_expiry < datetime.utcnow():
                    return {"valid": False, "message": "Distributor expired"}
            except:
                pass

    if not lic.get("active", True):
        return {"valid": False, "message": "License disabled"}

    # expiry check
    try:
        expiry_str = lic.get("expires_at")

        if not expiry_str:
            return {"valid": False, "message": "No expiry set"}

        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
        if expiry_date < datetime.utcnow():
            return {"valid": False, "message": "Expired"}
    except:
        return {"valid": False, "message": "Invalid expiry format"}

    # check if device already exists
    devices = db.collection("licensed_devices") \
        .where("license_key", "==", data.license_key) \
        .where("device_id", "==", data.device_id) \
        .stream()

    device_list = list(devices)

    if device_list:
        doc = device_list[0]
        device_data = doc.to_dict()

        # ❗ BLOCK inactive devices
        if not device_data.get("active", True):
            return {"valid": False, "message": "Device disabled"}

        # ❗ ensure distributor consistency
        if device_data.get("distributor_id") != lic.get("distributor_id"):
            return {"valid": False, "message": "Invalid distributor mapping"}

        doc.reference.update({
            "last_seen": datetime.utcnow()
        })

        return {
            "valid": True,
            "expiry": lic["expires_at"]
        }

    # 🔥 REAL DEVICE COUNT (NO CHEATING)
    devices = db.collection("licensed_devices") \
        .where("license_key", "==", data.license_key) \
        .stream()

    count = sum(1 for _ in devices)

    max_devices = lic.get("max_devices", 1)

    if count >= max_devices:
        return {"valid": False, "message": "Device limit reached"}

    # DISTRIBUTOR DEVICE LIMIT CHECK
    if dist:
        devices_snap = db.collection("licensed_devices") \
            .where("distributor_id", "==", dist_id) \
            .stream()

        total_devices = sum(1 for _ in devices_snap)

        if total_devices >= dist.get("max_devices", 999999):
            return {"valid": False, "message": "Distributor device limit reached"}

    # register new device
    db.collection("licensed_devices").add({
        "device_id": data.device_id,
        "license_key": data.license_key,
        "distributor_id": lic.get("distributor_id"),
        "device_label": data.device_name,
        "last_seen": datetime.utcnow(),
        "active": True,
        "pro_override": False
    })

    return {
        "valid": True,
        "expiry": lic["expires_at"]
    }


@app.post("/api/heartbeat")
def heartbeat(data: LicenseRequest, request: Request):

    # 🔐 API SECURITY
    if request.headers.get("x-api-key") != API_SECRET:
        return {"error": "unauthorized"}

    devices = db.collection("licensed_devices") \
        .where("device_id", "==", data.device_id) \
        .where("license_key", "==", data.license_key) \
        .stream()

    updated = False

    for d in devices:
        d.reference.update({
            "last_seen": datetime.utcnow()
        })
        updated = True

    if not updated:
        return {"status": "device_not_found"}

    return {"status": "ok"}


# =========================
# ADMIN APIs (UPDATED)
# =========================

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")

if not API_SECRET:
    raise Exception("API_SECRET not set")

def check_admin(request: Request):
    return request.headers.get("x-admin-key") == ADMIN_API_KEY


# ✅ CREATE LICENSE
@app.post("/admin/create")
def create_license(req: AdminRequest, request: Request):

    if not check_admin(request):
        return {"error": "unauthorized"}

    db.collection("license_keys").document(req.key).set({
        "key": req.key,
        "distributor_id": req.distributor_id or None,
        "max_devices": req.max_devices or 1,
        "expires_at": req.expiry,
        "active": True,
        "created_at": datetime.utcnow()
    })

    return {"status": "created"}


# ✅ LIST LICENSES
@app.get("/admin/list")
def list_licenses(request: Request):

    if not check_admin(request):
        return {"error": "unauthorized"}

    docs = db.collection("license_keys").stream()

    result = []
    for doc in docs:
        data = doc.to_dict()
        result.append(data)

    return result


# ✅ DELETE LICENSE
@app.post("/admin/delete")
def delete_license(req: AdminRequest, request: Request):

    if not check_admin(request):
        return {"error": "unauthorized"}

    # delete license key
    db.collection("license_keys").document(req.key).delete()

    # delete all devices linked to it
    devices = db.collection("licensed_devices") \
        .where("license_key", "==", req.key) \
        .stream()

    for d in devices:
        d.reference.delete()

    return {"status": "deleted"}


# ✅ RESET DEVICES (remove all devices for a license)
@app.post("/admin/reset-devices")
def reset_devices(req: AdminRequest, request: Request):

    if not check_admin(request):
        return {"error": "unauthorized"}

    devices = db.collection("licensed_devices") \
        .where("license_key", "==", req.key) \
        .stream()

    count = 0
    for d in devices:
        d.reference.delete()
        count += 1

    return {"status": "reset", "removed_devices": count}


# ✅ STATS
@app.get("/admin/stats")
def get_stats(request: Request):

    if not check_admin(request):
        return {"error": "unauthorized"}

    docs = db.collection("license_keys").stream()

    total = 0
    active = 0
    expired = 0

    now = datetime.utcnow()

    for doc in docs:
        total += 1
        data = doc.to_dict()

        try:
            expiry = datetime.strptime(data["expires_at"], "%Y-%m-%d")
            if expiry >= now and data.get("active", True):
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
# ADMIN UI PANEL (FIXED)
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
            <input id="key" placeholder="License Key">
            <input id="expiry" placeholder="YYYY-MM-DD">
            <button onclick="createLicense()">Create</button>
        </div>

        <div class="card">
            <h3>All Licenses</h3>
            <button class="secondary" onclick="loadLicenses()">Refresh</button>

            <table id="table"></table>
        </div>

        <script>

        const ADMIN_KEY = prompt("Enter admin key");

        async function loadStats() {
            const res = await fetch("/admin/stats", {
                headers: { "x-admin-key": ADMIN_KEY }
            });

            const data = await res.json();

            document.getElementById("total").innerText = data.total || 0;
            document.getElementById("active").innerText = data.active || 0;
            document.getElementById("expired").innerText = data.expired || 0;
        }

        async function createLicense() {
            const key = document.getElementById("key").value;
            const expiry = document.getElementById("expiry").value;

            await fetch("/admin/create", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-admin-key": ADMIN_KEY
                },
                body: JSON.stringify({
                    key: key,
                    expiry: expiry,
                    max_devices: 3,
                    distributor_id: "default"
                })
            });

            loadLicenses();
            loadStats();
        }

        async function loadLicenses() {
            const res = await fetch("/admin/list", {
                headers: { "x-admin-key": ADMIN_KEY }
            });

            const data = await res.json();

            const table = document.getElementById("table");

            table.innerHTML = `
                <tr>
                    <th>Key</th>
                    <th>Expiry</th>
                    <th>Used</th>
                    <th>Max</th>
                    <th>Actions</th>
                </tr>
            `;

            data.forEach(lic => {
                table.innerHTML += `
                    <tr>
                        <td>${lic.key}</td>
                        <td>${lic.expires_at}</td>
                        <td>${lic.used_devices || 0}</td>
                        <td>${lic.max_devices || 1}</td>
                        <td>
                            <button class="danger" onclick="deleteLicense('${lic.key}')">Delete</button>
                            <button class="secondary" onclick="resetDevices('${lic.key}')">Reset</button>
                        </td>
                    </tr>
                `;
            });
        }

        async function deleteLicense(key) {
            await fetch("/admin/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-admin-key": ADMIN_KEY
                },
                body: JSON.stringify({ key })
            });

            loadLicenses();
            loadStats();
        }

        async function resetDevices(key) {
            await fetch("/admin/reset-devices", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-admin-key": ADMIN_KEY
                },
                body: JSON.stringify({ key })
            });

            loadLicenses();
        }

        window.onload = () => {
            loadStats();
            loadLicenses();
        };

        </script>

    </body>
    </html>
    """
