# Uvicorn production config
# Run with: uvicorn app.main:app --config gateway/uvicorn.conf.py
# Or simply: uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8080

import multiprocessing

# Bind
host = "0.0.0.0"
port = 8080

# Workers: 2x CPU cores + 1 is the classic recommendation for async I/O apps
workers = (multiprocessing.cpu_count() * 2) + 1

# Logging
log_level = "info"
access_log = True

# Graceful shutdown
timeout_graceful_shutdown = 10
