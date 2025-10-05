import json
import pandas as pd
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# --- Configuration ---
DATA_PATH = Path(__file__).parent.parent / "data" / "q-vercel-latency.json"

try:
    df = pd.read_json(DATA_PATH)
    df.columns = df.columns.str.lower()
    df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
except FileNotFoundError:
    df = pd.DataFrame()


def get_metrics(df, region, threshold):
    region_data = df[df['region'] == region]
    if region_data.empty:
        return {"avg_latency": None, "p95_latency": None, "avg_uptime": None, "breaches": 0}

    avg_latency = region_data['latency'].mean()
    p95_latency = region_data['latency'].quantile(0.95, interpolation='lower')
    avg_uptime = region_data['uptime'].mean()
    breaches = (region_data['latency'] > threshold).sum()

    return {
        "avg_latency": round(avg_latency, 2),
        "p95_latency": int(p95_latency),
        "avg_uptime": round(avg_uptime, 2),
        "breaches": int(breaches),
    }


def core_handler(request):
    """Core logic with CORS always applied"""
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    # Handle preflight
    if request.method == 'OPTIONS':
        return 204, cors_headers, None

    if request.method != 'POST':
        return 405, cors_headers, json.dumps({"error": "Method Not Allowed"})

    if df.empty:
        return 500, cors_headers, json.dumps({"error": "Data could not be loaded on the server."})

    try:
        body = json.loads(request.body)
        regions_list = body.get("regions", [])
        threshold_ms = body.get("threshold_ms", 180)

        results = {region: get_metrics(df, region, threshold_ms) for region in regions_list}
        return 200, cors_headers, json.dumps(results)

    except json.JSONDecodeError:
        return 400, cors_headers, json.dumps({"error": "Invalid JSON body"})
    except Exception as e:
        return 500, cors_headers, json.dumps({"error": str(e)})


class handler(BaseHTTPRequestHandler):
    """Wrapper to handle HTTP requests"""

    def _send_response(self, status, headers, response_body):
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if response_body:
            self.wfile.write(response_body.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else ''
        mock_request = type('Request', (object,), {'method': 'POST', 'body': body})
        status, headers, response_body = core_handler(mock_request)
        self._send_response(status, headers, response_body)

    def do_OPTIONS(self):
        mock_request = type('Request', (object,), {'method': 'OPTIONS', 'body': None})
        status, headers, _ = core_handler(mock_request)
        self._send_response(status, headers, None)
