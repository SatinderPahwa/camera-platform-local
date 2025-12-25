#!/usr/bin/env python3
"""
WSGI Entry Point for Gunicorn
Serves the dashboard Flask application in production mode
"""

import sys
import os

# Add project directories to path
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_dir)
sys.path.insert(0, os.path.join(project_dir, 'config'))
sys.path.insert(0, os.path.join(project_dir, 'servers'))

# Import the Flask app from dashboard_server
from dashboard_server import app

# Export application for Gunicorn
application = app

if __name__ == "__main__":
    # This won't be called by Gunicorn, but useful for testing
    print("❌ This is a WSGI module for Gunicorn")
    print("Run with: gunicorn --config config/gunicorn_config.py servers.wsgi:application")
