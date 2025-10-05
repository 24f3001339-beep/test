import json
import statistics
from typing import List, Dict, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- 1. Data Structures ---

# Define the structure for the input payload
class InputPayload(BaseModel):
    regions: List[str] = Field(..., description="List of regions to process")
    threshold_ms: int = Field(..., description="Latency threshold in milliseconds")

# Define the structure for the output metrics
class RegionMetrics(BaseModel):
    region: str
    avg_latency: float
    p95_latency: float
    avg_uptime: float
    breaches: int

# --- 2. Application Setup ---

app = FastAPI()

# Enable CORS for POST requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],  # Allows POST and the required OPTIONS preflight
    allow_headers=["*"],
)

# --- 3. Data Loading (Mocked) ---

# IMPORTANT: In a real scenario, you must load 'q-vercel-latency.json' here.
# Since the file is not provided, this uses simulated data matching the expected format.
# A simple way to load the file in a real Vercel app is to read it once globally.

try:
    # --- Replace this block with your actual file loading logic ---
    # Example: with open("q-vercel-latency.json", 'r') as f: ALL_RECORDS = json.load(f)
    
    MOCK_TELEMETRY_DATA = [
        {"region": "emea", "latency_ms": 150},
        {"region": "emea", "latency_ms": 160},
        {"region": "emea", "latency_ms": 200}, # Breach (180 < 200)
        {"region": "amer", "latency_ms": 100},
        {"region": "amer", "latency_ms": 110},
        {"region": "amer", "latency_ms": 190}, # Breach (180 < 190)
        {"region": "apac", "latency_ms": 50},
        {"region": "apac", "latency_ms": 60},
    ]
    ALL_RECORDS = MOCK_TELEMETRY_DATA
except Exception:
    ALL_RECORDS = []

# --- 4. Utility Function for P95 Calculation ---

def calculate_p95(latencies: List[int]) -> float:
    """Calculates the 95th percentile (P95) of a list of latencies."""
    if not latencies:
        return 0.0
    
    sorted_latencies = sorted(latencies)
    N = len(sorted_latencies)
    
    # Calculate the index for the 95th percentile (0-based)
    # The requirement is often to use the closest value in the set.
    # index = ceil(N * 0.95) - 1
    # For a list of 100, index 94 is 95th value (0 to 99)
    p95_index = max(0, int(N * 0.95) - 1)
    
    # Ensure index is within bounds
    final_index = min(N - 1, p95_index)
    
    return float(sorted_latencies[final_index])

# --- 5. Endpoint Definition ---

@app.post("/api/latency", response_model=List[RegionMetrics])
async def get_latency_metrics(payload: InputPayload):
    """
    Calculates per-region latency and uptime metrics based on the input threshold.
    """
    
    # Group latencies and counts for requested regions
    region_data: Dict[str, Dict[str, List[int] | int]] = {
        region: {"latencies": [], "total_records": 0, "breaches": 0}
        for region in payload.regions
    }

    # Process all records
    for record in ALL_RECORDS:
        region = record.get("region")
        latency = record.get("latency_ms")
        
        if region in region_data and latency is not None:
            region_data[region]["latencies"].append(latency)
            region_data[region]["total_records"] += 1
            if latency > payload.threshold_ms:
                region_data[region]["breaches"] += 1

    # Calculate final metrics for each region
    results: List[RegionMetrics] = []
    for region_name, data in region_data.items():
        latencies = data["latencies"]
        total_records = data["total_records"]
        breaches = data["breaches"]
        
        if total_records == 0:
            results.append(RegionMetrics(
                region=region_name, avg_latency=0.0, p95_latency=0.0, avg_uptime=100.0, breaches=0
            ))
            continue
            
        # 1. avg_latency (mean)
        avg_latency = statistics.mean(latencies) if latencies else 0.0

        # 2. p95_latency (95th percentile)
        p95_latency = calculate_p95(latencies)

        # 3. avg_uptime (mean)
        # Uptime is defined by the complement of breaches (records under threshold)
        under_threshold = total_records - breaches
        avg_uptime = (under_threshold / total_records) * 100

        # 4. breaches (count of records above threshold)
        
        results.append(RegionMetrics(
            region=region_name,
            avg_latency=round(avg_latency, 2),
            p95_latency=round(p95_latency, 2),
            avg_uptime=round(avg_uptime, 2),
            breaches=breaches
        ))

    return results

# To run on Vercel, this file should be located at:
# your-project/api/latency.py
# and the endpoint URL will be: https://your-app-name.vercel.app/api/latency