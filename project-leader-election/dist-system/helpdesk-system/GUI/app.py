from flask import Flask, render_template, jsonify, request
import os
import sys
import requests

app = Flask(__name__)

# Explicitly set template and static folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.template_folder = os.path.join(BASE_DIR, 'templates')
app.static_folder = os.path.join(BASE_DIR, 'static')
app.static_url_path = '/static'

print(f"DEBUG: Template folder: {app.template_folder}")
print(f"DEBUG: Static folder: {app.static_folder}")
print(f"DEBUG: Template exists: {os.path.exists(app.template_folder)}")
print(f"DEBUG: Static exists: {os.path.exists(app.static_folder)}")

# Backend API (load balancer Docker = :5000; ticket langsung = :8000)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")
GUI_PORT = int(os.getenv("GUI_PORT", "5050"))


@app.route('/')
def index():
    """Serve halaman utama GUI."""
    try:
        print("DEBUG: Loading index.html...")
        return render_template('index.html')
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return f"Error loading template: {str(e)}", 500


@app.route('/api/config')
def get_config():
    """Endpoint untuk config frontend."""
    return jsonify({
        "api_base_url": API_BASE_URL
    })


def _proxy_to_backend(path: str):
    """Teruskan request ke ticket service / load balancer."""
    target = f"{API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8')}"

    headers = {
        key: value
        for key, value in request.headers
        if key.lower() not in ('host', 'content-length', 'connection')
    }

    response = requests.request(
        method=request.method,
        url=target,
        headers=headers,
        data=request.get_data(),
        timeout=30,
    )

    excluded = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
    resp_headers = [
        (name, value)
        for name, value in response.headers.items()
        if name.lower() not in excluded
    ]
    return response.content, response.status_code, resp_headers


@app.route('/api/backend', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/api/backend/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy_backend(path):
    """Proxy semua API ticket agar browser tidak perlu akses port backend langsung."""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        return _proxy_to_backend(path)
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Gagal terhubung ke backend",
            "detail": str(e),
            "api_base_url": API_BASE_URL,
        }), 503


@app.route('/api/cluster/status')
def proxy_cluster_status():
    """Alias untuk status kluster (kompatibilitas)."""
    try:
        return _proxy_to_backend('cluster/status')
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Gagal mengambil status kluster", "detail": str(e)}), 503


if __name__ == '__main__':
    print(f"Starting Helpdesk GUI on port {GUI_PORT}...")
    print(f"Connecting to API at: {API_BASE_URL}")
    print(f"Buka browser: http://localhost:{GUI_PORT}")
    print(f"Python: {sys.executable}")
    app.run(host='0.0.0.0', port=GUI_PORT, debug=False)
