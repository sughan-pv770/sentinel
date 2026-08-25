# SentinelX — Troubleshooting Guide

Common issues and their solutions, organized by category.

---

## Setup & Installation Issues

### `ModuleNotFoundError: No module named 'fastapi'` (or any dependency)

**Cause:** Dependencies not installed, or virtual environment not activated.

**Fix:**
```bash
# Make sure you're in the correct directory
cd gateway   # or cd demo-service

# Activate your virtual environment
# Windows CMD:
.venv\Scripts\activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Mac/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### `python: command not found` or wrong Python version

**Cause:** Python not in PATH, or multiple Python versions installed.

**Fix:**
```bash
# Try these alternatives:
python3 --version
py --version        # Windows Python Launcher

# Use the one that shows 3.10 or 3.11:
py -3.11 -m venv .venv
```

### `pip install` fails with permission errors

**Cause:** Trying to install globally without admin rights.

**Fix:** Always use a virtual environment:
```bash
python -m venv .venv
# Activate it (see above), then:
pip install -r requirements.txt
```

---

## Runtime Issues

### `Connection refused` on port 9000

**Cause:** Demo-service is not running.

**Fix:** Start it in a separate terminal:
```bash
cd demo-service
uvicorn app.main:app --host 0.0.0.0 --port 9000
```

### `502 Bad Gateway` or proxy errors

**Cause:** Gateway cannot reach the origin service.

**Fix:**
1. Verify demo-service is running: `curl http://localhost:9000/health`
2. Check the environment variable is set:
   ```bash
   # Windows CMD:
   set SENTINELX_ORIGIN_BASE_URL=http://localhost:9000
   # Windows PowerShell:
   $env:SENTINELX_ORIGIN_BASE_URL="http://localhost:9000"
   # Mac/Linux:
   export SENTINELX_ORIGIN_BASE_URL=http://localhost:9000
   ```
3. Restart the gateway after setting the variable

### Port already in use (`Address already in use`)

**Cause:** Another process is using port 8080 or 9000.

**Fix:**
```bash
# Find the process (Mac/Linux):
lsof -i :8080
kill <PID>

# Windows CMD:
netstat -ano | findstr :8080
taskkill /PID <PID> /F

# Or use a different port:
uvicorn app.main:app --host 0.0.0.0 --port 8081
```

### Gateway logs show `IsolationForest` warnings at startup

**Cause:** Normal — scikit-learn may print convergence info during training.

**Fix:** These are informational, not errors. The model trains successfully in ~150ms on 4,000 samples. If training fails, the gateway will crash with a clear error.

---

## Dashboard Issues

### Dashboard shows old theme / styling

**Cause:** Browser cached the previous CSS file.

**Fix:** Hard refresh:
- **Chrome/Edge/Firefox:** `Ctrl + Shift + R` (Windows/Linux) or `Cmd + Shift + R` (Mac)
- **Safari:** `Cmd + Option + R`
- Or clear browser cache and reload

### Dashboard says "No alerts yet" after clicking scenario buttons

**Cause:** The alerts are filtered by the selected identity. The simulator uses the selected identity, but the alert feed may not match.

**Fix:**
1. Check the identity dropdown — ensure it matches the identity in the simulator
2. Click the scenario button and wait 2-3 seconds for the polling cycle to fetch new data
3. Try switching to a different identity and back

### Gauge shows "—" or doesn't move

**Cause:** No requests have been made for the selected identity yet, or API polling is failing.

**Fix:**
1. Click any scenario button to generate traffic
2. Open browser dev tools (F12) → Console tab — check for JavaScript errors
3. Open Network tab — ensure requests to `/sentinelx/risk/u_alex` return 200

---

## Test Suite Issues

### Tests fail: `AssertionError: Origin service not reachable`

**Cause:** Demo-service not running on port 9000.

**Fix:** Start it: `cd demo-service && uvicorn app.main:app --port 9000`

### Tests fail: `AssertionError: Gateway not reachable`

**Cause:** Gateway not running on port 8080.

**Fix:** Start it with the env var set (see Quick Start above).

### Tests fail: scoring assertions (wrong tier)

**Cause:** Unlikely with the randomized identity system, but possible if the gateway has accumulated extreme state.

**Fix:**
- Tests use per-run random identity IDs (`u_traveller_a3k9x2`) — they should be idempotent
- If still failing, restart the gateway to clear in-memory state
- Run the test directly: `python test_pipeline.py`

### `UnicodeEncodeError` on Windows

**Cause:** Windows cp1252 encoding doesn't support some Unicode characters.

**Fix:** Run the test directly from Command Prompt or PowerShell:
```bash
python test_pipeline.py
```
The test suite uses ASCII-safe output (`->` instead of `→`).

---

## Docker Issues

### `docker-compose up` fails: "Cannot connect to Docker daemon"

**Cause:** Docker Desktop is not running.

**Fix:** Start Docker Desktop, wait for it to fully initialize, then retry.

### `docker-compose up` — gateway starts before Redis is ready

**Cause:** Health check timing — shouldn't happen with the current `docker-compose.yml` which includes `condition: service_healthy`.

**Fix:** If it does happen:
```bash
docker-compose down
docker-compose up --build
```

### Redis connection errors in Docker

**Cause:** Gateway is trying to connect before Redis accepts connections.

**Fix:** The `docker-compose.yml` includes a Redis health check with `redis-cli ping`. If the issue persists, manually verify Redis:
```bash
docker exec -it sentinelx-redis-1 redis-cli ping
# Should return: PONG
```

---

## Performance Issues

### Requests are slow (> 100ms overhead)

**Cause:** Unlikely in normal operation (budget is < 15ms). Possible causes:
- First request after startup (ML model may still be loading)
- Debug logging enabled with high I/O
- Running inside a VM with limited resources

**Fix:**
- Check `x-sentinelx-latency-ms` response header to see actual SentinelX overhead
- Ensure you're running with `--log-level info` (not `debug`)
- Give the gateway a warmup request before measuring

---

## Getting Help

1. **Check this document first** for your specific error
2. **Review the logs** — the gateway outputs structured JSON logs that include scoring details
3. **Open browser dev tools** (F12) to check for API errors in the Network/Console tabs
4. **Read the architecture docs** — [`ARCHITECTURE.md`](ARCHITECTURE.md) explains every component

---

*NexHack 2.0 — SentinelX Team*
