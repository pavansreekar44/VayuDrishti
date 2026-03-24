"""
Gunicorn configuration for running FastAPI on Azure Web App.
This is used when deploying with the startup.sh script.
"""

import multiprocessing
import os

# Get the port from environment variable (Azure sets this)
bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"

# Number of worker processes
workers = multiprocessing.cpu_count() * 2 + 1

# Worker class for async support
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout for worker processes
timeout = 120

# Keep-alive connections
keepalive = 5

# Access and error logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr

# Logging level
loglevel = "info"

# Worker process naming
proc_name = "vayu_drishti_backend"

# Server mechanics
daemon = False
pidfile = None
umask = 0
tmp_upload_dir = None

# SSL (if needed, configure in Azure)
# keyfile = None
# certfile = None
# ssl_version = None
# cert_reqs = 0
# ca_certs = None
# suppress_ragged_eof = True

# Server hooks
def on_starting(server):
    """Hook called just before the master process is initialized."""
    print(f"Starting Gunicorn with {workers} workers on {bind}")

def when_ready(server):
    """Hook called just after the server is started."""
    print(f"Server is ready. Spawning workers")
