#!/usr/bin/env python3
"""
Authentication module for Camera Dashboard
Supports both Google OAuth and basic username/password authentication
"""

import os
import functools
from flask import session, redirect, url_for, request
from authlib.integrations.flask_client import OAuth

# Global OAuth instance
oauth = None

def init_auth(app):
    """Initialize authentication for the Flask app"""
    global oauth

    # Configure session
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

    # Initialize OAuth if Google credentials provided
    google_client_id = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if google_client_id and google_client_secret:
        oauth = OAuth(app)
        oauth.register(
            name='google',
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'}
        )
        print("✅ Google OAuth enabled")
    else:
        print("⚠️  Google OAuth not configured - using basic auth only")

def require_auth(f):
    """Decorator to require authentication for routes"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if 'user' not in session:
            # Store the original URL they wanted to access
            session['next'] = request.url
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def check_basic_auth(username, password):
    """Validate basic username/password authentication"""
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('ADMIN_PASSWORD')

    if not admin_password:
        print("⚠️  ADMIN_PASSWORD not set in .env file")
        return False

    return username == admin_username and password == admin_password

def check_google_domain(email):
    """Check if email is from allowed Google domain"""
    # Get allowed domain from environment (e.g., "pahwa.net")
    allowed_domain = os.getenv('GOOGLE_ALLOWED_DOMAIN', '')

    if not allowed_domain:
        # If no domain restriction, allow any Google account
        return True

    # Check if email ends with @domain
    return email.endswith(f'@{allowed_domain}')
