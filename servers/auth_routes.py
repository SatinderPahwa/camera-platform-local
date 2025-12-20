"""
Authentication routes for Camera Dashboard
Handles Google OAuth, admin login, and logout
"""

from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_user, logout_user, current_user
from auth import oauth, verify_admin_credentials, User, get_client_ip, is_local_network

# Create authentication blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login')
def login():
    """
    Login page
    Shows Google OAuth and admin login options
    """
    # Check if already authenticated
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    # Check if from local network (no auth needed)
    client_ip = get_client_ip()
    if is_local_network(client_ip):
        flash('You are on the local network - no authentication required', 'info')
        return redirect(url_for('index'))

    # Get next URL (redirect after login)
    next_url = request.args.get('next', url_for('index'))

    return render_template('auth/login.html', next_url=next_url)

@auth_bp.route('/login/google')
def login_google():
    """
    Initiate Google OAuth login
    """
    # Store next URL in session
    next_url = request.args.get('next', url_for('index'))
    session['next_url'] = next_url

    # Redirect to Google OAuth
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/callback/google')
def google_callback():
    """
    Google OAuth callback
    """
    try:
        # Get OAuth token
        token = oauth.google.authorize_access_token()

        # Get user info
        user_info = token.get('userinfo')

        if not user_info:
            flash('Failed to get user information from Google', 'error')
            return redirect(url_for('auth.login'))

        # Extract user details
        email = user_info.get('email')
        name = user_info.get('name', email)
        google_id = user_info.get('sub')

        # Check domain restriction (@pahwa.net)
        if not email.endswith('@pahwa.net'):
            flash('Access denied: Only @pahwa.net emails are allowed', 'error')
            return redirect(url_for('auth.login'))

        # Create user object
        user = User(
            id=google_id,
            email=email,
            name=name,
            auth_type='google'
        )

        # Store user data in session
        session['user_data'] = {
            'id': google_id,
            'email': email,
            'name': name,
            'auth_type': 'google'
        }

        # Log in user
        login_user(user)

        flash(f'Welcome, {name}!', 'success')

        # Redirect to next URL or home
        next_url = session.pop('next_url', url_for('index'))
        return redirect(next_url)

    except Exception as e:
        flash(f'Authentication failed: {str(e)}', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/login/admin', methods=['POST'])
def login_admin():
    """
    Admin login with username/password
    """
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash('Username and password required', 'error')
        return redirect(url_for('auth.login'))

    # Verify admin credentials
    user = verify_admin_credentials(username, password)

    if not user:
        flash('Invalid username or password', 'error')
        return redirect(url_for('auth.login'))

    # Store user data in session
    session['user_data'] = {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'auth_type': user.auth_type
    }

    # Log in user
    login_user(user)

    flash(f'Welcome, {user.name}!', 'success')

    # Redirect to next URL or home
    next_url = request.args.get('next', url_for('index'))
    return redirect(next_url)

@auth_bp.route('/logout')
def logout():
    """
    Logout current user
    """
    # Log out user
    logout_user()

    # Clear session
    session.clear()

    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/status')
def status():
    """
    Check authentication status (for debugging)
    """
    client_ip = get_client_ip()
    is_local = is_local_network(client_ip)

    return {
        'authenticated': current_user.is_authenticated,
        'client_ip': client_ip,
        'is_local_network': is_local,
        'requires_auth': not is_local,
        'user': {
            'email': current_user.email if current_user.is_authenticated else None,
            'name': current_user.name if current_user.is_authenticated else None,
            'auth_type': current_user.auth_type if current_user.is_authenticated else None
        } if current_user.is_authenticated else None
    }
