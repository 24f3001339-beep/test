import json
from pathlib import Path

def handler(request):
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json"
    }

    if request.method == "OPTIONS":
        return "", 204, cors_headers

    if request.method != "POST":
        return json.dumps({"error": "Method Not Allowed"}), 405, cors_headers

    try:
        import pandas as pd  # lazy import

        # Load JSON dynamically
        base_dir = Path(__file__).parent
        data_file = base_dir.parent / "data" / "q-vercel-latency.json"
        if not data_file.exists():
            # fallback dummy data
            df = pd.DataFrame({
                "region": ["us-east-1", "eu-west-1"],
                "latency": [100, 120],
                "uptime": [99.9, 99.5]
            })
        else:
            df = pd.read_json(data_file)
            df.columns = df.columns.str.lower()
            df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)

        # Parse request body
        body_data = getattr(request, 'json', None) or getattr(request, 'body', None)
        if isinstance(body_data, bytes):
            body_data = json.loads(body_data.decode('utf-8'))
        elif isinstance(body_data, str):
            body_data = json.loads(body_data)

        regions = body_data.get("regions", [])
        threshold = body_data.get("threshold_ms", 180)

        results = {}
        for region in regions:
            region_data = df[df['region'] == region]
            if region_data.empty:
                results[region] = {"avg_latency": None, "p95_latency": None, "avg_uptime": None, "breaches": 0}
            else:
                avg_latency = region_data['latency'].mean()
                p95_latency = region_data['latency'].quantile(0.95, interpolation='lower')
                avg_uptime = region_data['uptime'].mean()
                breaches = (region_data['latency'] > threshold).sum()
                results[region] = {
                    "avg_latency": round(avg_latency, 2),
                    "p95_latency": int(p95_latency),
                    "avg_uptime": round(avg_uptime, 2),
                    "breaches": int(breaches)
                }

        return json.dumps(results), 200, cors_headers

    except Exception as e:
        # Never let the function crash
        return json.dumps({"error": f"Runtime error: {str(e)}"}), 500, cors_headers
