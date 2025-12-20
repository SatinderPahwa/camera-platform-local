"""
Authentication module for Camera Dashboard
Provides Google OAuth, admin fallback, and IP-based bypass
"""

import os
import bcrypt
import ipaddress
from functools import wraps
from flask import request, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, current_user
from authlib.integrations.flask_client import OAuth

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'

# Initialize OAuth
oauth = OAuth()

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, email, name, auth_type='google'):
        self.id = id
        self.email = email
        self.name = name
        self.auth_type = auth_type  # 'google' or 'admin'

    def is_admin(self):
        return self.auth_type == 'admin'

    def is_authorized_domain(self):
        """Check if user email is from authorized domain (@pahwa.net)"""
        if self.auth_type == 'admin':
            return True
        return self.email.endswith('@pahwa.net')

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Load user from session"""
    if 'user_data' in session:
        user_data = session['user_data']
        return User(
            id=user_data['id'],
            email=user_data['email'],
            name=user_data['name'],
            auth_type=user_data.get('auth_type', 'google')
        )
    return None

def is_local_network(ip_address):
    """
    Check if IP address is from local network (192.168.x.x)
    Returns True if local, False if external
    """
    try:
        ip = ipaddress.ip_address(ip_address)

        # Check for private network ranges
        # 192.168.0.0/16 - Common home networks
        # 10.0.0.0/8 - Private networks
        # 172.16.0.0/12 - Private networks
        # 127.0.0.0/8 - Loopback
        private_networks = [
            ipaddress.ip_network('192.168.0.0/16'),
            ipaddress.ip_network('10.0.0.0/8'),
            ipaddress.ip_network('172.16.0.0/12'),
            ipaddress.ip_network('127.0.0.0/8'),
        ]

        for network in private_networks:
            if ip in network:
                return True

        return False
    except ValueError:
        # Invalid IP address
        return False

def get_client_ip():
    """
    Get real client IP address, considering proxy headers
    """
    # Check for X-Forwarded-For header (set by nginx/reverse proxy)
    if 'X-Forwarded-For' in request.headers:
        # X-Forwarded-For can contain multiple IPs, take the first one
        ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
    elif 'X-Real-IP' in request.headers:
        ip = request.headers['X-Real-IP']
    else:
        ip = request.remote_addr

    return ip

def require_auth(f):
    """
    Decorator to require authentication
    Bypasses auth for local network requests (192.168.x.x)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = get_client_ip()

        # Bypass authentication for local network
        if is_local_network(client_ip):
            return f(*args, **kwargs)

        # Require authentication for external requests
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        # Check if user is authorized (domain check)
        if not current_user.is_authorized_domain():
            flash('Access denied: Unauthorized domain', 'error')
            return redirect(url_for('auth.logout'))

        return f(*args, **kwargs)

    return decorated_function

def init_auth(app):
    """
    Initialize authentication system
    """
    # Set up Flask-Login
    login_manager.init_app(app)

    # Set up OAuth
    oauth.init_app(app)

    # Configure Google OAuth
    google_client_id = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if google_client_id and google_client_secret:
        oauth.register(
            name='google',
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile'
            }
        )
    else:
        app.logger.warning('Google OAuth not configured - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required')

# Admin authentication functions
def hash_password(password):
    """Hash password with bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    """Verify password against bcrypt hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def verify_admin_credentials(username, password):
    """
    Verify admin credentials
    Returns User object if valid, None otherwise
    """
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password_hash = os.getenv('ADMIN_PASSWORD_HASH')

    if not admin_password_hash:
        # No admin password set
        return None

    if username != admin_username:
        return None

    # Verify password
    if verify_password(password, admin_password_hash.encode('utf-8')):
        return User(
            id='admin',
            email='admin@local',
            name='Administrator',
            auth_type='admin'
        )

    return None
