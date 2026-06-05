import os
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- KONFIGURASI TARGET API GATEWAY ---
TICKET_SERVICES = [
    x.strip() for x in os.getenv(
        "TICKET_SERVICES",
        "http://ticket-1:8000,http://ticket-2:8000,http://ticket-3:8000,http://ticket-4:8000"
    ).split(",") if x.strip()
]

# Tracker index global & Lock untuk thread-safety Round-Robin
_rr_lb_index = 0
_lb_lock = threading.Lock()

def log(msg: str):
    print(f"[⚖ LOAD BALANCER] {msg}", flush=True)


def request_timeout(path: str) -> float:
    """cluster/status butuh waktu lebih lama (banyak RPC ke notification nodes)."""
    if path.startswith("cluster/"):
        return float(os.getenv("LB_CLUSTER_TIMEOUT", "8"))
    return float(os.getenv("LB_TIMEOUT", "5"))


def pick_ticket_service() -> str:
    """Memilih salah satu node secara bergantian (Thread-Safe Round-Robin)."""
    global _rr_lb_index
    if not TICKET_SERVICES:
        raise RuntimeError("Tidak ada target ticket_service yang dikonfigurasi.")
    
    with _lb_lock:  # Kunci thread agar index tidak tabrakan saat high-traffic
        target = TICKET_SERVICES[_rr_lb_index]
        _rr_lb_index = (_rr_lb_index + 1) % len(TICKET_SERVICES)
        return target

# --- ENDPOINT FORWARDER (REVERSE PROXY) ---
# Menambahkan OPTIONS untuk lulus CORS preflight, dan PATCH untuk kelengkapan
ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']

@app.route('/', defaults={'path': ''}, methods=ALLOWED_METHODS)
@app.route('/<path:path>', methods=ALLOWED_METHODS)
def catch_all_and_forward(path):
    attempts = 0
    max_attempts = len(TICKET_SERVICES)
    
    req_data = request.get_data()
    req_headers = {key: value for key, value in request.headers if key.lower() != 'host'}
    req_params = request.args

    timeout = request_timeout(path)
    tried = []

    while attempts < max_attempts:
        target_host = pick_ticket_service()
        full_url = f"{target_host}/{path}"
        attempts += 1
        tried.append(target_host)

        try:
            response = requests.request(
                method=request.method,
                url=full_url,
                headers=req_headers,
                data=req_data,
                params=req_params,
                timeout=timeout,
            )

            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            safe_headers = [
                (name, value) for (name, value) in response.headers.items()
                if name.lower() not in excluded_headers
            ]

            return (response.content, response.status_code, safe_headers)

        except Exception:
            continue

    log(
        f"⚠ Gagal [{request.method}] /{path} — "
        f"semua ticket service tidak merespons (timeout {timeout}s): {', '.join(tried)}"
    )
    return jsonify({
        "error": "Bad Gateway",
        "message": "Seluruh kluster Ticket Service API Gateway tidak dapat dijangkau."
    }), 502

if __name__ == "__main__":
    LB_PORT = 5000
    log(f"Load Balancer (Round-Robin) sukses berjalan di port :{LB_PORT}")
    app.run(host="0.0.0.0", port=LB_PORT, threaded=True)