# api/metrics.py
import json
import pandas as pd
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# --- Configuration ---
# Vercel's deployment environment is read-only, so we load the data once globally.
# NOTE: Ensure your file is named 'q-vercel-latency.json' and is in a 'data' folder
# adjacent to the 'api' folder (i.e., 'data/q-vercel-latency.json').
DATA_PATH = Path(__file__).parent.parent / "data" / "q-vercel-latency.json"

try:
    # 💥 MODIFIED: Using pd.read_json to correctly load the JSON file.
    df = pd.read_json(DATA_PATH)
    
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
    
    # Check for correct method and data frame
    if request.method != 'POST':
        return (405, headers, "Method Not Allowed")
        
    # Check if the data loaded correctly (prevents 500 error if data is missing)
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

# Vercel requires the handler function to be present. 
# We use a wrapper class for robust compatibility, especially when testing locally.
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read the content length and body
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length).decode('utf-8')
        
        # Create a mock request object for the custom core_handler function
        mock_request = type('Request', (object,), {
            'method': 'POST',
            'body': body
        })

        # Call the core logic handler
        status, headers, response_body = core_handler(mock_request)
        
        # Write response
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        
        if response_body:
            self.wfile.write(response_body.encode('utf-8'))
            
    # Handle OPTIONS preflight requests for CORS
    def do_OPTIONS(self):
        # Create a mock request object for the custom core_handler function
        mock_request = type('Request', (object,), {'method': 'OPTIONS', 'body': None})
        
        status, headers, _ = core_handler(mock_request)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()