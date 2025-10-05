# api/metrics.py
import json
import pandas as pd
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# --- Configuration ---
# Vercel's deployment environment is read-only, so we load the data once globally.
DATA_PATH = Path(__file__).parent.parent / "data" / "q-vercel-latency.json"

try:
    # MODIFIED: Using pd.read_json to correctly load the JSON file.
    df = pd.read_json(DATA_PATH)
    
    # Standardize column names for ease of use
    df.columns = df.columns.str.lower()
    df.rename(columns={'latency_ms': 'latency', 'uptime_pct': 'uptime'}, inplace=True)
except FileNotFoundError:
    df = pd.DataFrame()


def get_metrics(df, region, threshold):
    """Calculates all required metrics for a single region."""
    
    region_data = df[df['region'] == region]
    
    if region_data.empty:
        return {
            "avg_latency": None,
            "p95_latency": None,
            "avg_uptime": None,
            "breaches": 0,
        }

    # Calculate Required Metrics
    avg_latency = region_data['latency'].mean()
    p95_latency = region_data['latency'].quantile(0.95, interpolation='lower')
    avg_uptime = region_data['uptime'].mean()
    breaches = (region_data['latency'] > threshold).sum()

    # Format and Return
    return {
        "avg_latency": round(avg_latency, 2),
        "p95_latency": int(p95_latency),
        "avg_uptime": round(avg_uptime, 2),
        "breaches": int(breaches),
    }

# This function contains the core logic for the Vercel Serverless Function
def core_handler(request):
    """Vercel serverless function entry point logic."""
    
    # 1. Enable CORS for POST requests
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return (204, headers, None)
    
    if request.method != 'POST':
        return (405, headers, "Method Not Allowed")
        
    # Check if the data loaded correctly
    if df.empty:
         return (500, headers, json.dumps({"error": "Data could not be loaded on the server."}))


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

# Vercel entry point requires the handler function to be present. 
# We use a wrapper class for robust compatibility.
class handler(BaseHTTPRequestHandler):
    
    # MODIFIED: Helper function to write status and headers consistently for CORS
    def _send_response(self, status, headers, response_body):
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        
        if response_body:
            self.wfile.write(response_body.encode('utf-8'))
            
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length).decode('utf-8')
        
        mock_request = type('Request', (object,), {
            'method': 'POST',
            'body': body
        })

        status, headers, response_body = core_handler(mock_request)
        
        # Write response using the helper
        self._send_response(status, headers, response_body)
            
    def do_OPTIONS(self):
        mock_request = type('Request', (object,), {'method': 'OPTIONS', 'body': None})
        
        status, headers, _ = core_handler(mock_request)
        
        # Write response using the helper (no body for OPTIONS)
        self._send_response(status, headers, None)