import json
from pathlib import Path
import os

# Global placeholders
df = None
GLOBAL_ERROR = None

def load_data():
    """Lazy-load the JSON file when handler is invoked."""
    global df, GLOBAL_ERROR
    if df is not None:
        return  # already loaded

    try:
        import pandas as pd
    except ImportError:
        GLOBAL_ERROR = "Pandas not installed. Add 'pandas' to requirements.txt"
        df = None
        return

    BASE_DIR = Path(__file__).parent
    primary_path = BASE_DIR.parent / "data" / "q-vercel-latency.json"
    fallback_path = BASE_DIR / "data" / "q-vercel-latency.json"

    for path in [primary_path, fallback_path]:
        try:
            df_local = pd.read_json(path)
            df_local.columns = df_local.columns.str.lower()
            df_local.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
            df = df_local
            return
        except FileNotFoundError:
            continue
        except Exception as e:
            GLOBAL_ERROR = f"Error parsing JSON file at {path}: {str(e)}"
            df = None
            return

    GLOBAL_ERROR = "Data file not found in both primary and fallback locations."
    df = None


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
    """Vercel serverless function entry point with full CORS and safe JSON handling"""
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

    # Lazy-load data
    load_data()

    if df is None:
        error_msg = GLOBAL_ERROR or "Data could not be loaded."
        return json.dumps({"error": f"Initialization Error: {error_msg}"}), 500, cors_headers

    # Parse request body
    try:
        if hasattr(request, 'json') and request.json is not None:
            body_data = request.json
        elif hasattr(request, 'body') and request.body:
            raw = request.body
            if isinstance(raw, bytes):
                body_data = json.loads(raw.decode('utf-8'))
            else:
                body_data = json.loads(raw)
        else:
            return json.dumps({"error": "Empty request body"}), 400, cors_headers

        regions = body_data.get("regions", [])
        threshold = body_data.get("threshold_ms", 180)

        results = {region: get_metrics(df, region, threshold) for region in regions}

        return json.dumps(results), 200, cors_headers

    except Exception as e:
        return json.dumps({"error": f"Runtime Error: {str(e)}"}), 500, cors_headers
