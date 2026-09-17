# Self-Healing API Mesh — Interactive Frontend Dashboard

This directory contains the interactive demonstration dashboard for the **Self-Healing API Resilience Package** (`self-healing-api`), built by **Naveen Krishna**.

## Features Included

1. **⚡ Fault Injection Playground**:
   - **🟢 Normal Call (200 OK)**: Clean execution through the resilience pipeline.
   - **🔥 503 Outage (Auto-Retry)**: Simulates intermittent backend outage healed with exponential backoff & full jitter.
   - **⏳ 429 Rate Limit (Retry-After)**: Simulates HTTP 429 and automatic delay honoring standard RFC headers.
   - **🌐 Network Timeout (Fallback)**: Simulates total transport disconnect tripping graceful cached/synthetic fallback.
   - **🛑 Force Circuit Trip**: Injects 5 consecutive faults to trip the breaker from `CLOSED` to `OPEN`.
   - **🔄 Reset Breaker**: Manually resets the state machine back to `CLOSED`.

2. **📊 Live Telemetry Counters**:
   - Total Requests Dispatched
   - Success Rate (%)
   - Outages Auto-Healed
   - Retries Executed
   - Fallbacks Served
   - Real-time Sub-millisecond Execution Latency (0.05ms)

3. **🔄 Real-Time Circuit Breaker FSM**:
   - Visual indicator of states: `CLOSED` (Healthy), `OPEN` (Tripped), `HALF-OPEN` (Canary Recovery Probe).
   - Live cooldown countdown timer (e.g. 10s cooldown before probe trial).
   - Failure threshold and half-open canary progress bar.

4. **📜 Live Resilience Pipeline Stream**:
   - Step-by-step logs showing UUID generation, retry attempts, jitter delay times, and failover fallbacks in real-time.

---

## How to Run

### Option 1: Direct File Open (Zero Setup)
Simply double-click `index.html` in your file explorer, or open it in any modern browser (Chrome, Edge, Firefox, Safari).

### Option 2: Run via Python Built-in Web Server
From the repository root:
```bash
python -m http.server 8000 --directory frontend
```
Then navigate in your browser to:
```
http://localhost:8000
```
