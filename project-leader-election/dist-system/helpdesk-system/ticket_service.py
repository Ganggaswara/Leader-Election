import os
import time
import uuid
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify
from flask_cors import CORS
import db_helper

app = Flask(__name__)
CORS(app)  # Enable CORS untuk semua routes

# --- CONFIGURATION ---
PORT = 8000
BACKEND_NODES = [
    x.strip() for x in os.getenv(
        "BACKEND_NODES",
        "http://notification-1:9000,http://notification-2:9000,http://notification-3:9000"
    ).split(",") if x.strip()
]

# Tracker global & Lock untuk load balancing Round-Robin yang Thread-Safe
_rr_index = 0
_rr_lock = threading.Lock()

# Cache node notification yang tidak merespons (hindari hang ~4s per request di Docker)
_offline_nodes = {}
_offline_lock = threading.Lock()
OFFLINE_CACHE_SECONDS = 45

# --- INITIALIZATION ---
# Memastikan tabel database siap saat service pertama kali menyala
db_helper.init_db()


# --- HELPER FUNCTIONS ---
def rpc_call(base_url: str, method: str, params: dict, timeout=2.0) -> dict:
    """Fungsi standar untuk melakukan call RPC berbasis HTTP JSON-RPC ke backend."""
    payload = {"method": method, "params": params}
    response = requests.post(f"{base_url}/rpc", json=payload, timeout=timeout)

    # JIKA statusnya 409 (Bukan Leader), biarkan lolos agar ditangkap oleh logika Redirection
    if response.status_code == 409:
        return response.json()

    # Untuk status error murni (seperti 500 atau 404), lempar exception
    response.raise_for_status()
    return response.json()


def pick_backend_node() -> str:
    """Memilih node backend secara bergantian (Round-Robin) secara aman."""
    global _rr_index
    if not BACKEND_NODES:
        raise RuntimeError("No backend nodes configured.")

    with _rr_lock:
        node = BACKEND_NODES[_rr_index]
        _rr_index = (_rr_index + 1) % len(BACKEND_NODES)
        return node


# --- API ENDPOINTS ---

@app.post("/tickets")
def create_ticket():
    """Endpoint untuk membuat tiket aduan baru (OPEN)."""
    body = request.get_json(force=True, silent=True) or {}
    customer_name = body.get("customer_name")
    issue_title = body.get("issue_title")
    description = body.get("description", "")

    if not customer_name or not issue_title:
        return jsonify({"error": "customer_name and issue_title are required"}), 400

    ticket_id = str(uuid.uuid4())[:8]

    try:
        db_helper.insert_ticket(ticket_id, customer_name, issue_title, description)
        ticket_data = db_helper.get_ticket_by_id(ticket_id)
        return jsonify(ticket_data), 201
    except Exception as e:
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.get("/tickets/<ticket_id>")
def get_ticket(ticket_id):
    """Endpoint untuk mengambil detail data tiket berdasarkan ID."""
    ticket = db_helper.get_ticket_by_id(ticket_id)
    if not ticket:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404
    return jsonify(ticket)


@app.post("/tickets/<ticket_id>/resolve")
def resolve_ticket(ticket_id):
    """
    Endpoint untuk menyelesaikan tiket.
    [BEST PRACTICE] Alur harus melewati RPC ke kluster Leader, baru update DB!
    """
    ticket = db_helper.get_ticket_by_id(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404

    if ticket["status"] == "RESOLVED":
        return jsonify({"message": "Ticket is already resolved", "ticket": ticket}), 200

    body = request.get_json(force=True, silent=True) or {}
    resolution = body.get("resolution", "Resolved by technical support")

    try:
        # 1. Pilih node backend acak (Round-Robin) untuk melempar tugas
        target_node = pick_backend_node()
        print(f"[API] Mengirim request resolve ke {target_node}...", flush=True)
        
        # 2. Tembak via RPC
        res = rpc_call(target_node, "resolve", {"ticket_id": ticket_id, "resolution": resolution})

        # 3. INTERCEPT REDIRECTION (Jika node yang ditembak bukan Leader)
        if "error" in res and res["error"].get("code") == "NOT_LEADER":
            leader_url = res["error"].get("leader_url")
            if not leader_url:
                return jsonify({"error": "Cluster sedang kacau, tidak ada leader aktif"}), 503
            
            print(f"[API] Node Follower menolak. Mengalihkan (Redirect) ke Leader: {leader_url}...", flush=True)
            # Tembak ulang langsung ke Leader yang sah
            res = rpc_call(leader_url, "resolve", {"ticket_id": ticket_id, "resolution": resolution})

        # 4. Evaluasi hasil akhir dari Leader
        if "error" in res:
            return jsonify({"error": "Sistem backend gagal memproses", "detail": res["error"]}), 500

        # 5. JIKA BACKEND SUKSES (RabbitMQ udah jalan), barulah update database SQLite lokal
        db_helper.update_ticket_status(ticket_id, "RESOLVED", resolution)
        updated_ticket = db_helper.get_ticket_by_id(ticket_id)
        
        print(f"[API] Tiket {ticket_id} resmi di-resolve dan di-update ke DB.", flush=True)
        return jsonify({
            "message": "Ticket resolved successfully via Distributed Backend",
            "ticket": updated_ticket
        }), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Gagal terhubung ke kluster Notification Service", "detail": str(e)}), 503
    except Exception as e:
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500


def _offline_entry(base_url: str) -> dict:
    return {
        "node_url": base_url,
        "node_name": base_url.rstrip("/").split("/")[-1].replace(":9000", ""),
        "online": False,
    }


def _mark_offline(base_url: str):
    with _offline_lock:
        _offline_nodes[base_url] = time.time() + OFFLINE_CACHE_SECONDS


def _clear_offline(base_url: str):
    with _offline_lock:
        _offline_nodes.pop(base_url, None)


def _is_cached_offline(base_url: str) -> bool:
    with _offline_lock:
        expires = _offline_nodes.get(base_url)
        if not expires:
            return False
        if time.time() >= expires:
            _offline_nodes.pop(base_url, None)
            return False
        return True


def _fetch_notification_status(base_url: str) -> dict:
    """Ambil status satu notification node (dipanggil paralel)."""
    if _is_cached_offline(base_url):
        return _offline_entry(base_url)

    entry = _offline_entry(base_url)
    try:
        res = rpc_call(base_url, "get_status", {}, timeout=0.35)
        if "result" in res:
            _clear_offline(base_url)
            entry = {**entry, **res["result"], "online": True}
    except requests.exceptions.RequestException:
        _mark_offline(base_url)
    return entry


@app.get("/cluster/status")
def cluster_status():
    """Agregasi status leader election & RabbitMQ worker dari semua notification node."""
    nodes = []
    leader = None
    election_in_progress = False

    workers = min(len(BACKEND_NODES), 6) or 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_notification_status, url) for url in BACKEND_NODES]
        for future in as_completed(futures):
            entry = future.result()
            nodes.append(entry)
            if entry.get("is_leader"):
                leader = {
                    "node_id": entry.get("node_id"),
                    "node_name": entry.get("node_name"),
                    "node_url": entry.get("node_url"),
                }
            if entry.get("election_in_progress"):
                election_in_progress = True

    nodes.sort(key=lambda n: n.get("node_id") or 999)
    active_workers = [
        n["node_name"] for n in nodes
        if n.get("online") and n.get("worker_active")
    ]

    return jsonify({
        "leader": leader,
        "election_in_progress": election_in_progress,
        "nodes": nodes,
        "active_workers": active_workers,
        "updated_at": time.time(),
    }), 200


@app.get("/tickets")
def list_tickets():
    """Endpoint untuk mengambil semua tiket."""
    try:
        tickets = db_helper.get_all_tickets()
        return jsonify({"total": len(tickets), "tickets": tickets}), 200
    except Exception as e:
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.put("/tickets/<ticket_id>")
def update_ticket(ticket_id):
    """Endpoint untuk mengupdate data tiket."""
    ticket = db_helper.get_ticket_by_id(ticket_id)
    if not ticket:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    body = request.get_json(force=True, silent=True) or {}
    customer_name = body.get("customer_name")
    issue_title = body.get("issue_title")
    description = body.get("description")

    if not any([customer_name, issue_title, description]):
        return jsonify({"error": "At least one field must be provided for update"}), 400

    try:
        db_helper.update_ticket(ticket_id, customer_name, issue_title, description)
        updated_ticket = db_helper.get_ticket_by_id(ticket_id)
        return jsonify({"message": "Ticket updated successfully", "ticket": updated_ticket}), 200
    except Exception as e:
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.delete("/tickets/<ticket_id>")
def delete_ticket(ticket_id):
    """Endpoint untuk menghapus tiket."""
    ticket = db_helper.get_ticket_by_id(ticket_id)
    if not ticket:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    try:
        success = db_helper.delete_ticket(ticket_id)
        if success:
            return jsonify({"message": f"Ticket {ticket_id} deleted successfully", "deleted_ticket": ticket}), 200
        else:
            return jsonify({"error": "Failed to delete ticket"}), 500
    except Exception as e:
        return jsonify({"error": "Database error", "detail": str(e)}), 500


if __name__ == "__main__":
    print(f"Starting Ticket Service API Gateway on port {PORT}...", flush=True)
    app.run(host="0.0.0.0", port=PORT, threaded=True)