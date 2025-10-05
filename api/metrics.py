# api/metrics.py
import json
import pandas as pd
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# --- Configuration ---
# Vercel's deployment environment is read-only, so we load the data once globally.
DATA_PATH = Path(__file__).parent.parent / "data" / "q-vercel-latency.csv"
try:
    # Load the sample telemetry bundle (assuming it's a CSV)
    df = pd.read_csv(DATA_PATH)
    # Ensure columns are properly named/cased if different from the sample data
    # Standardize column names for ease of use
    df.columns = df.columns.str.lower()
    df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
except FileNotFoundError:
    # Fallback for environments where the data might be loaded differently
    df = pd.DataFrame() 


def get_metrics(df, region, threshold):
    """Calculates all required metrics for a single region."""
    
    # 1. Filter data for the current region
    region_data = df[df['region'] == region]
    
    if region_data.empty:
        return {
            "avg_latency": None,
            "p95_latency": None,
            "avg_uptime": None,
            "breaches": 0,
        }

    # 2. Calculate Required Metrics
    avg_latency = region_data['latency'].mean()
    p95_latency = region_data['latency'].quantile(0.95, interpolation='lower') # Use 'lower' for a conservative 95th percentile
    avg_uptime = region_data['uptime'].mean()
    breaches = (region_data['latency'] > threshold).sum()

    # 3. Format and Return
    return {
        "avg_latency": round(avg_latency, 2),
        "p95_latency": int(p95_latency),
        "avg_uptime": round(avg_uptime, 2),
        "breaches": int(breaches),
    }

def handler(request):
    """Vercel serverless function entry point."""
    
    # 1. Enable CORS for POST requests
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return (204, headers, None)
    
    # Check for correct method and data frame
    if request.method != 'POST' or df.empty:
        return (405, headers, "Method Not Allowed or Data Not Loaded")

    try:
        # 2. Parse JSON body
        body = json.loads(request.body)
        regions_list = body.get("regions", [])
        threshold_ms = body.get("threshold_ms", 180)

        results = {}
        for region in regions_list:
            # 3. Calculate and store metrics per region
            results[region] = get_metrics(df, region, threshold_ms)
        
        # 4. Return results
        return (200, headers, json.dumps(results))

    except json.JSONDecodeError:
        return (400, headers, "Invalid JSON body")
    except Exception as e:
        # General error handling
        return (500, headers, json.dumps({"error": str(e)}))

# Vercel entry point requires a specific class definition for compatibility
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read the content length and body
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length).decode('utf-8')
        
        # Create a mock request object for the custom handler function
        mock_request = type('Request', (object,), {
            'method': 'POST',
            'body': body
        })

        # Call the core logic handler
        status, headers, response_body = handler(mock_request)
        
        # Write response
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        
        if response_body:
            self.wfile.write(response_body.encode('utf-8'))
            
    # Handle OPTIONS preflight requests for CORS
    def do_OPTIONS(self):
        status, headers, _ = handler(type('Request', (object,), {'method': 'OPTIONS', 'body': None}))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

# Note: The actual Vercel runtime uses a simpler handler function, 
# but the BaseHTTPRequestHandler structure is a common pattern for local testing.
# The core logic is isolated in the 'handler(request)' function.