import json
import pandas as pd
from pathlib import Path

# --- Load data globally for performance ---
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


def handler(request):
    """Vercel serverless function entry point with full CORS support"""
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        return ("", 204, cors_headers)

    if request.method != "POST":
        return (json.dumps({"error": "Method Not Allowed"}), 405, cors_headers)

    if df.empty:
        return (json.dumps({"error": "Data could not be loaded on the server."}), 500, cors_headers)

    try:
        body = request.json  # Vercel automatically parses JSON if Content-Type is application/json
        regions = body.get("regions", [])
        threshold = body.get("threshold_ms", 180)

        results = {region: get_metrics(df, region, threshold) for region in regions}

        return (json.dumps(results), 200, cors_headers)
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500, cors_headers)
