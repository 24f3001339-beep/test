import json
import pandas as pd
from pathlib import Path
import os

# --- Load data globally ---
BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR.parent / "data" / "q-vercel-latency.json"

GLOBAL_ERROR = None
df = pd.DataFrame()

# Try primary path
try:
    df = pd.read_json(DATA_PATH)
    df.columns = df.columns.str.lower()
    df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
except FileNotFoundError:
    # Try fallback path in case Vercel bundled differently
    fallback_path = BASE_DIR / "data" / "q-vercel-latency.json"
    try:
        df = pd.read_json(fallback_path)
        df.columns = df.columns.str.lower()
        df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
    except Exception as e:
        df = pd.DataFrame()
        GLOBAL_ERROR = f"Data file not found or could not be parsed: {str(e)}"
except Exception as e:
    df = pd.DataFrame()
    GLOBAL_ERROR = f"Data parsing error: {str(e)}"


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


def handler(request):
    """Vercel serverless function with guaranteed CORS and JSON response"""
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json"
    }

    # OPTIONS preflight
    if request.method == "OPTIONS":
        return "", 204, cors_headers

    if request.method != "POST":
        return json.dumps({"error": "Method Not Allowed"}), 405, cors_headers

    if df.empty:
        error_msg = GLOBAL_ERROR or "Data not loaded on server."
        return json.dumps({"error": f"Initialization Error: {error_msg}"}), 500, cors_headers

    try:
        # Parse request body
        body_data = getattr(request, 'json', None)
        if not body_data:
            body_raw = getattr(request, 'body', None)
            if body_raw:
                if isinstance(body_raw, bytes):
                    body_data = json.loads(body_raw.decode('utf-8'))
                else:
                    body_data = json.loads(body_raw)
            else:
                return json.dumps({"error": "Empty request body"}), 400, cors_headers

        regions = body_data.get("regions", [])
        threshold = body_data.get("threshold_ms", 180)

        results = {region: get_metrics(df, region, threshold) for region in regions}

        return json.dumps(results), 200, cors_headers

    except Exception as e:
        return json.dumps({"error": f"Runtime Error: {str(e)}"}), 500, cors_headers
