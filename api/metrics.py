import json
import pandas as pd
from pathlib import Path
import os
import sys # Added for path debugging

# --- Load data globally for performance ---
# NOTE: Vercel environment path handling can be tricky.
# We modify the path lookup to be more robust, searching relative to the executing file.

# Dynamically set the base directory, which is usually the 'api' directory on Vercel
BASE_DIR = Path(os.path.dirname(__file__))

# Standard path: api/../data/q-vercel-latency.json
DATA_PATH = BASE_DIR.parent / "data" / "q-vercel-latency.json"

GLOBAL_ERROR = None

try:
    df = pd.read_json(DATA_PATH)
    df.columns = df.columns.str.lower()
    df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
except FileNotFoundError:
    
    # 💥 CRITICAL FIX: Try Vercel's relative path fallback 💥
    # On some deployments, Vercel places data directly in the root of the function bundle.
    FALLBACK_PATH = Path(os.path.join(os.getcwd(), 'data', 'q-vercel-latency.json'))
    
    try:
        df = pd.read_json(FALLBACK_PATH)
        df.columns = df.columns.str.lower()
        df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
    except FileNotFoundError:
        df = pd.DataFrame()
        # 💥 FIX: Removed .resolve() which was causing errors 💥
        GLOBAL_ERROR = f"Data file not found after two path checks."
    except Exception as e:
        df = pd.DataFrame()
        GLOBAL_ERROR = f"Data parsing error on fallback path: {str(e)}"

except Exception as e:
    # Catching general errors during data reading (e.g., pandas parsing error)
    df = pd.DataFrame()
    GLOBAL_ERROR = f"Data parsing error on standard path: {str(e)}"


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
        "Content-Type": "application/json" 
    }

    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        # The body is empty for a 204 response
        return "", 204, cors_headers

    if request.method != "POST":
        body = json.dumps({"error": "Method Not Allowed"})
        return body, 405, cors_headers

    # CHECK FOR GLOBAL DATA LOAD FAILURE
    if df.empty:
        # Return the specific global error message captured during startup.
        error_msg = GLOBAL_ERROR if GLOBAL_ERROR else "Data could not be loaded on the server (unknown reason)."
        body = json.dumps({"error": "Initialization Error: " + error_msg})
        return body, 500, cors_headers

    try:
        # --- Robust Body Parsing ---
        if hasattr(request, 'json') and request.json is not None:
            body_data = request.json
        elif hasattr(request, 'body') and request.body:
            # Decode the request body bytes/string if it exists
            if isinstance(request.body, bytes):
                 body_data = json.loads(request.body.decode('utf-8'))
            else:
                 body_data = json.loads(request.body)
        else:
            raise ValueError("Request body is empty or invalid.")
        # --- END Robust Body Parsing ---
            
        regions = body_data.get("regions", [])
        threshold = body_data.get("threshold_ms", 180)

        results = {region: get_metrics(df, region, threshold) for region in regions}
        
        # FINAL RESPONSE: Return (body, status_code, headers)
        return json.dumps(results), 200, cors_headers
        
    except Exception as e:
        # This catch block is for errors during runtime (e.g., bad input parsing)
        body = json.dumps({"error": "Runtime Error during processing: " + str(e)})
        return body, 500, cors_headers
