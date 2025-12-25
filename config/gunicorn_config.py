"""
Gunicorn Configuration for Dashboard Server
Production WSGI server configuration with SSL support
"""

import os
import multiprocessing
from pathlib import Path

# Project paths
project_dir = Path(__file__).parent.parent
bind_host = os.getenv('DASHBOARD_SERVER_HOST', '0.0.0.0')
bind_port = os.getenv('DASHBOARD_SERVER_PORT', '5000')

# Server socket
bind = f"{bind_host}:{bind_port}"
backlog = 2048

# Worker processes
# Formula: (2 × CPU cores) + 1, capped at 9
workers = min((multiprocessing.cpu_count() * 2) + 1, 9)
worker_class = 'gevent'  # Async I/O for streaming (HLS, downloads)
worker_connections = 1000
max_requests = 1000  # Recycle workers after 1000 requests (prevents memory leaks)
max_requests_jitter = 50  # Add randomness to prevent all workers restarting simultaneously

# Timeouts
timeout = 120  # 120 seconds for large video downloads
graceful_timeout = 30  # 30 seconds for graceful shutdown
keepalive = 5

# Process naming
proc_name = 'camera-dashboard'

# Daemon mode - run in background
daemon = False  # managed_start.sh will handle daemonization

# PID file
pidfile = str(project_dir / 'pids' / 'gunicorn.pid')

# Logging
accesslog = str(project_dir / 'logs' / 'gunicorn_access.log')
errorlog = str(project_dir / 'logs' / 'gunicorn_error.log')
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# SSL Configuration (read from environment)
ssl_enabled = os.getenv('DASHBOARD_SSL_ENABLED', 'false').lower() == 'true'
if ssl_enabled:
    certfile = os.getenv('DASHBOARD_SSL_CERT_FILE')
    keyfile = os.getenv('DASHBOARD_SSL_KEY_FILE')

    if certfile and keyfile and os.path.exists(certfile) and os.path.exists(keyfile):
        # SSL certificates accessible via ssl-certs group membership
        print(f"🔒 SSL enabled: {certfile}")
    else:
        print(f"⚠️  SSL enabled but certificates not found:")
        print(f"   Cert: {certfile}")
        print(f"   Key: {keyfile}")
        certfile = None
        keyfile = None
else:
    certfile = None
    keyfile = None

# Server mechanics
preload_app = False  # Don't preload - allows graceful restarts
reload = False  # Don't auto-reload in production
reuse_port = True  # Enable SO_REUSEPORT for better performance

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized"""
    print("=" * 70)
    print("🚀 Starting Gunicorn Dashboard Server")
    print("=" * 70)
    print(f"Workers: {workers} ({worker_class})")
    print(f"Bind: {bind}")
    if certfile:
        print(f"SSL: Enabled")
    print("=" * 70)

def on_reload(server):
    """Called when a worker is reloaded (SIGHUP)"""
    print("🔄 Reloading Gunicorn workers...")

def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT"""
    print(f"⏹️  Worker {worker.pid} interrupted")

def worker_abort(worker):
    """Called when a worker is killed"""
    print(f"❌ Worker {worker.pid} aborted")
