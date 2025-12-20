#!/usr/bin/env python3
"""
Authentication routes for Camera Dashboard
Handles login, logout, and OAuth callbacks
"""

import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from auth import oauth, check_basic_auth, check_google_domain

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler"""
    if request.method == 'POST':
        # Handle basic auth login
        username = request.form.get('username')
        password = request.form.get('password')

        if check_basic_auth(username, password):
            session['user'] = {
                'username': username,
                'auth_type': 'basic'
            }
            # Redirect to originally requested page or dashboard
            next_page = session.pop('next', '/')
            return redirect(next_page)
        else:
            flash('Invalid username or password', 'error')
            return render_template('login.html', error='Invalid credentials')

    # GET request - show login page
    google_enabled = oauth is not None
    return render_template('login.html', google_enabled=google_enabled)

@auth_bp.route('/google')
def google_login():
    """Redirect to Google OAuth"""
    if not oauth:
        flash('Google OAuth not configured', 'error')
        return redirect(url_for('auth.login'))

    # Store the page they wanted to access
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    if not oauth:
        return redirect(url_for('auth.login'))

    try:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.parse_id_token(token)

        email = user_info.get('email')

        # Check domain restriction
        if not check_google_domain(email):
            allowed_domain = os.getenv('GOOGLE_ALLOWED_DOMAIN', '')
            flash(f'Access denied. Only @{allowed_domain} emails are allowed.', 'error')
            return redirect(url_for('auth.login'))

        # Store user in session
        session['user'] = {
            'email': email,
            'name': user_info.get('name'),
            'picture': user_info.get('picture'),
            'auth_type': 'google'
        }

        # Redirect to originally requested page or dashboard
        next_page = session.pop('next', '/')
        return redirect(next_page)

    except Exception as e:
        print(f"Google OAuth error: {e}")
        flash('Google authentication failed', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('auth.login'))
