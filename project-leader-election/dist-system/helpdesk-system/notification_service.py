import os
import time
import threading
import logging
import requests
import json
import pika
from flask import Flask, request, jsonify

app = Flask(__name__)

# Matikan log bawaan Flask
log_werkzeug = logging.getLogger('werkzeug')
log_werkzeug.setLevel(logging.ERROR)

# ==========================================
# 1. KONFIGURASI NODE & RING ARCHITECTURE
# ==========================================
NODE_NAME = os.getenv("NODE_NAME", "notification-1")
NODE_ID = int(os.getenv("NODE_ID", "1"))
ALL_NODES_RAW = os.getenv("ALL_NODES", "notification-1:1,notification-2:2,notification-3:3,notification-4:4,notification-5:5,notification-6:6")

# Parsing daftar seluruh node dari environment variable
NODES = {}
for item in [x.strip() for x in ALL_NODES_RAW.split(",") if x.strip()]:
    host, sid = item.split(":")
    NODES[int(sid)] = host

SELF_URL = f"http://{NODE_NAME}:9000"
sorted_ids = sorted(NODES.keys())  # Global, bisa di-update saat election

# ==========================================
# 2. STATE DISTRIBUSI & LOCKING
# ==========================================
state_lock = threading.Lock()
leader_id = None
leader_url = None
is_leader = False
election_in_progress = False
last_heartbeat = time.time()
rabbitmq_connected = False
last_worker_activity = None

RESOLVED_TICKETS = {}
WORKER_ACTIVE_SECONDS = 15
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def log(msg: str):
    print(f"[{NODE_NAME} ID:{NODE_ID}] {msg}", flush=True)

def rpc_call(url: str, method: str, params: dict, timeout=1.5):
    try:
        r = requests.post(f"{url}/rpc", json={"method": method, "params": params}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"error": {"code": "RPC_FAILED", "detail": str(e)}}

def publish_to_queue(ticket_data: dict):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue='ticket_notifications', durable=True)
        message = json.dumps(ticket_data)
        channel.basic_publish(
            exchange='',
            routing_key='ticket_notifications',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
        log(f"✉ [RabbitMQ] Sukses publish notifikasi tiket {ticket_data['ticket_id']}.")
    except Exception as e:
        log(f"⚠ [RabbitMQ ERROR] Gagal mempublish pesan: {str(e)}")

# ==========================================
# 4. DETEKSI NODE AKTIF
# ==========================================
def get_active_nodes():
    """Cek node mana yang masih hidup untuk update ring sebelum election."""
    active = []
    for nid, host in NODES.items():
        if nid == NODE_ID:
            active.append(nid)
            continue
        res = rpc_call(f"http://{host}:9000", "ping", {}, timeout=0.3)
        if "error" not in res:
            active.append(nid)
    return sorted(active)

# ==========================================
# 5. ALGORITMA HIRSCHBERG-SINCLAIR
# ==========================================
def forward_hs_token(current_id, direction, payload):
    """Smart Forwarding: lompat ke tetangga berikutnya kalau node mati."""
    with state_lock:
        local_sorted = list(sorted_ids)

    if current_id not in local_sorted:
        return {"result": "ELECTED"}

    idx = local_sorted.index(current_id)

    for skip in range(1, len(local_sorted)):
        if direction == "LEFT":
            target_idx = (idx - skip) % len(local_sorted)
        else:
            target_idx = (idx + skip) % len(local_sorted)

        target_id = local_sorted[target_idx]

        if target_id == payload["candidate_id"]:
            return {"result": "ELECTED"}

        target_url = f"http://{NODES[target_id]}:9000"
        res = rpc_call(target_url, "hs_election", payload, timeout=0.3)

        if "error" not in res:
            return res
        else:
            log(f"⚠️ Bypass: Node {target_id} DOWN! Melompat ke tetangga sebelahnya...")

    return {"result": "ELECTED"}

def become_leader():
    global leader_id, leader_url, is_leader, election_in_progress, last_heartbeat
    with state_lock:
        leader_id = NODE_ID
        leader_url = SELF_URL
        is_leader = True
        election_in_progress = False
        last_heartbeat = time.time()

    log("=" * 60)
    log(f"👑 ✨ ELECTION WON! Saya adalah LEADER Baru! (ID: {NODE_ID}) ✨ 👑")
    log("=" * 60)

    # Broadcast coordinator + langsung kirim heartbeat pertama
    for nid, host in NODES.items():
        if nid == NODE_ID:
            continue
        rpc_call(f"http://{host}:9000", "coordinator", {
            "leader_id": NODE_ID,
            "leader_url": SELF_URL
        }, timeout=1.0)

    for nid, host in NODES.items():
        if nid == NODE_ID:
            continue
        rpc_call(f"http://{host}:9000", "heartbeat", {
            "leader_id": NODE_ID,
            "leader_url": SELF_URL
        }, timeout=0.5)

def run_hs_election_loop():
    global election_in_progress
    k = 0
    max_phases = 10

    while k < max_phases:
        with state_lock:
            if not election_in_progress:
                log("🛑 Election dibatalkan, leader sudah ada.")
                return

        steps = 2 ** k
        log(f"⚡ [Phase k={k}] Range: {steps} | Melempar token Kiri & Kanan...")

        payload_left  = {"candidate_id": NODE_ID, "direction": "LEFT",  "steps_left": steps, "sender_id": NODE_ID}
        payload_right = {"candidate_id": NODE_ID, "direction": "RIGHT", "steps_left": steps, "sender_id": NODE_ID}

        res_left  = forward_hs_token(NODE_ID, "LEFT",  payload_left)
        res_right = forward_hs_token(NODE_ID, "RIGHT", payload_right)

        # Cek lagi setelah blocking RPC selesai
        with state_lock:
            if not election_in_progress:
                log("🛑 Election dibatalkan setelah forward.")
                return

        status_l = res_left.get("result")
        status_r = res_right.get("result")

        if status_l == "ELECTED" or status_r == "ELECTED":
            log("✅ Token kembali! Saya menang pemilu!")
            become_leader()
            return

        if status_l == "OK" and status_r == "OK":
            log(f"✅ Fase {k} aman. Lanjut ke fase {k+1}...")
            k += 1
            time.sleep(0.1)
        else:
            log("❌ Terjegal node ID lebih besar. Mundur dari pencalonan.")
            with state_lock:
                election_in_progress = False
                # Reset timer agar monitor tidak langsung trigger lagi
                # Leader baru akan kirim heartbeat dalam ~0.2 detik
                last_heartbeat = time.time()
            return

    with state_lock:
        election_in_progress = False
        last_heartbeat = time.time()

def start_election():
    global election_in_progress, leader_id, last_heartbeat, sorted_ids
    with state_lock:
        if election_in_progress:
            return
        election_in_progress = True
        leader_id = None
        last_heartbeat = time.time()

    # Update ring dengan node yang masih hidup
    active = get_active_nodes()
    with state_lock:
        sorted_ids = active

    log(f"📣 MEMULAI PEMILU (HIRSCHBERG-SINCLAIR) | Node aktif: {sorted_ids}")
    threading.Thread(target=run_hs_election_loop, daemon=True).start()

# ==========================================
# 6. ENDPOINT UTAMA (/rpc)
# ==========================================
@app.post("/rpc")
def rpc():
    global last_heartbeat, leader_id, leader_url, is_leader, election_in_progress

    body = request.get_json(force=True, silent=True) or {}
    method = body.get("method")
    params = body.get("params") or {}

    if method == "ping":
        return jsonify({"result": "PONG"})

    if method == "get_status":
        with state_lock:
            lid, lurl = leader_id, leader_url
            local_is_leader = is_leader
            in_election = election_in_progress
            rmq_ok = rabbitmq_connected
            last_work = last_worker_activity

        worker_active = (
            last_work is not None
            and (time.time() - last_work) < WORKER_ACTIVE_SECONDS
        )
        return jsonify({
            "result": {
                "node_id": NODE_ID,
                "node_name": NODE_NAME,
                "node_url": SELF_URL,
                "online": True,
                "is_leader": local_is_leader,
                "role": "leader" if local_is_leader else "follower",
                "leader_id": lid,
                "leader_url": lurl,
                "election_in_progress": in_election,
                "rabbitmq_connected": rmq_ok,
                "worker_active": worker_active,
                "last_worker_activity": last_work,
                "resolved_count": len(RESOLVED_TICKETS),
            }
        })

    if method == "heartbeat":
        lid = params.get("leader_id")
        lurl = params.get("leader_url")
        if lid is None or lurl is None:
            return jsonify({"result": "OK"})  # ignore heartbeat kosong
        with state_lock:
            leader_id = int(lid)
            leader_url = lurl
            is_leader = (leader_id == NODE_ID)
            last_heartbeat = time.time()
            election_in_progress = False
        return jsonify({"result": "OK"})

    if method == "coordinator":
        lid = params.get("leader_id")
        lurl = params.get("leader_url")
        if lid is None or lurl is None:
            return jsonify({"result": "OK"})  # ignore coordinator kosong
        with state_lock:
            leader_id = int(lid)
            leader_url = lurl
            is_leader = (leader_id == NODE_ID)
            last_heartbeat = time.time()
            election_in_progress = False
        log(f"📢 [PENGUMUMAN] Leader baru terpilih: Node {leader_id}")
        return jsonify({"result": "OK"})

    if method == "hs_election":
        candidate_id = params.get("candidate_id")
        direction = params.get("direction")
        steps_left = params.get("steps_left")

        # Validasi semua params ada
        if any(v is None for v in [candidate_id, direction, steps_left]):
            return jsonify({"error": {"code": "INVALID_PARAMS"}}), 400

        candidate_id = int(candidate_id)
        steps_left = int(steps_left)

        if candidate_id == NODE_ID:
            return jsonify({"result": "ELECTED"})
        if NODE_ID > candidate_id:
            return jsonify({"result": "BLOCKED"})
        if steps_left == 1:
            return jsonify({"result": "OK"})

        payload = {
            "candidate_id": candidate_id,
            "direction": direction,
            "steps_left": steps_left - 1,
            "sender_id": NODE_ID
        }
        res = forward_hs_token(NODE_ID, direction, payload)
        return jsonify(res)

    if method == "resolve":
        ticket_id = str(params.get("ticket_id", ""))
        resolution = str(params.get("resolution", ""))

        if not ticket_id:
            return jsonify({"error": {"code": "INVALID_PARAMS"}}), 400
 
        with state_lock:
            local_is_leader = is_leader
            l_id, l_url = leader_id, leader_url

        if not local_is_leader:
            return jsonify({"error": {"code": "NOT_LEADER", "leader_id": l_id, "leader_url": l_url}}), 409

        if ticket_id in RESOLVED_TICKETS:
            return jsonify({"result": RESOLVED_TICKETS[ticket_id]})

        time.sleep(0.1)
        receipt = {
            "ticket_id": ticket_id,
            "resolution": resolution,
            "resolved_by_node": NODE_NAME,
            "resolved_at": time.time()
        }
        RESOLVED_TICKETS[ticket_id] = receipt
        log(f"✔ Berhasil memproses tiket {ticket_id}.")
        publish_to_queue({"ticket_id": ticket_id, "resolution": resolution, "resolved_by": NODE_NAME})
        return jsonify({"result": receipt})

    return jsonify({"error": {"code": "METHOD_NOT_FOUND"}}), 400

# ==========================================
# 7. BACKGROUND THREADS
# ==========================================
def heartbeat_loop():
    """Leader kirim heartbeat ke semua follower secara paralel."""
    while True:
        try:
            time.sleep(0.5)
            with state_lock:
                if not is_leader:
                    continue
                hb_data = {"leader_id": leader_id, "leader_url": leader_url}

            # Kirim paralel agar tidak blocking satu per satu
            threads = []
            for nid, host in NODES.items():
                if nid == NODE_ID:
                    continue
                t = threading.Thread(
                    target=rpc_call,
                    args=(f"http://{host}:9000", "heartbeat", hb_data),
                    kwargs={"timeout": 0.5},
                    daemon=True
                )
                threads.append(t)
                t.start()

            # Tidak perlu join — fire and forget
        except Exception as e:
            log(f"⚠ [Heartbeat Error] {str(e)}")

def monitor_loop():
    while True:
        try:
            time.sleep(1.0)
            with state_lock:
                if is_leader:
                    continue
                lh = last_heartbeat
                is_in_election = election_in_progress

            if (time.time() - lh) > 6.0 and not is_in_election:  # ← 3.0 ke 6.0
                log("🚨 LEADER MATI! Heartbeat terputus. Memulai pemilu...")
                start_election()
        except Exception:
            pass

def rabbitmq_consumer_loop():
    """Semua node consume dari RabbitMQ queue."""
    global rabbitmq_connected, last_worker_activity
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()
            channel.queue_declare(queue='ticket_notifications', durable=True)

            def callback(ch, method, properties, body):
                global last_worker_activity
                data = json.loads(body.decode())
                last_worker_activity = time.time()
                print(f"\n🔔 >>> [RABBITMQ WORKER: {NODE_NAME}] <<<", flush=True)
                print(f"    Tiket ID : {data.get('ticket_id')}", flush=True)
                print(f"    Solusi   : {data.get('resolution')}", flush=True)
                print(f"    Status   : Email terkirim ke pelanggan!\n", flush=True)
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue='ticket_notifications', on_message_callback=callback)
            with state_lock:
                rabbitmq_connected = True
            log("🔌 [RabbitMQ] Berhasil terhubung. Consumer siap kerja!")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            with state_lock:
                rabbitmq_connected = False
            time.sleep(3.0)
        except Exception as e:
            with state_lock:
                rabbitmq_connected = False
            log(f"⚠ [RabbitMQ Consumer Error] {str(e)}")
            time.sleep(3.0)

def bootstrap():
    """
    Delay bootstrap per node agar semua container siap sebelum election dimulai.
    node-1: 4.0s, node-2: 5.0s, ..., node-6: 9.0s
    Jeda cukup besar agar node-6 (ID tertinggi) pasti ikut election pertama.
    """
    delay = 3.0 + (1.0 * NODE_ID)
    log(f"⏳ Bootstrap: menunggu {delay:.1f} detik agar semua node siap...")
    time.sleep(delay)
    log("🚀 Bootstrap selesai. Memulai inisiasi awal kluster...")
    start_election()

# ==========================================
# 8. MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=rabbitmq_consumer_loop, daemon=True).start()
    threading.Thread(target=bootstrap, daemon=True).start()

    log(f"Service menyala (Port 9000). Bersiap bergabung ke Ring...")
    app.run(host="0.0.0.0", port=9000, threaded=True)