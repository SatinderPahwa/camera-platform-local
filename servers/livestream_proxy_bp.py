import os
import logging
import requests
from flask import Blueprint, jsonify, request, url_for
from datetime import datetime
from functools import wraps

# Setup logging
logger = logging.getLogger(__name__)

# Livestreaming API configuration (loaded from environment)
LIVESTREAM_API_URL = os.getenv('LIVESTREAM_API_URL', 'http://localhost:8080')
LIVESTREAM_ENABLED = os.getenv('LIVESTREAM_ENABLED', 'true').lower() == 'true'

# Create a blueprint for livestreaming proxy routes
livestream_proxy_bp = Blueprint('livestream_proxy', __name__, url_prefix='/api/livestream')

# Authentication decorator (assuming it's available globally or passed)
# For now, we'll use a placeholder. Real 'require_auth' will come from main app.
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Placeholder for actual authentication check
        # In a real app, this would check session, tokens, etc.
        # For this proxy, we'll assume the main app's authentication
        # is handled before reaching these routes.
        logger.warning("Placeholder: Authentication not directly enforced in livestream_proxy blueprint. Ensure main app handles it.")
        return f(*args, **kwargs)
    return decorated_function

# --- Livestreaming API Proxy Endpoints ---

@livestream_proxy_bp.route('/streams', methods=['GET'])
@require_auth
def api_livestream_list():
    """List all active livestreams"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.get(f"{LIVESTREAM_API_URL}/streams", timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get livestreams from {LIVESTREAM_API_URL}/streams: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@livestream_proxy_bp.route('/streams/<camera_id>', methods=['GET'])
@require_auth
def api_livestream_get(camera_id):
    """Get livestream info for specific camera"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.get(
            f"{LIVESTREAM_API_URL}/streams/{camera_id}",
            timeout=5
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get livestream for {camera_id} from {LIVESTREAM_API_URL}/streams/{camera_id}: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@livestream_proxy_bp.route('/streams/<camera_id>/start', methods=['POST'])
@require_auth
def api_livestream_start(camera_id):
    """Start livestream for camera"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        # Forward request body if provided
        data = request.get_json(silent=True) or {}

        response = requests.post(
            f"{LIVESTREAM_API_URL}/streams/{camera_id}/start",
            json=data,
            timeout=30  # Longer timeout for stream start
        )

        result = response.json()

        # Log successful stream start
        if response.status_code in [200, 201]:
            logger.info(f"Livestream started for camera {camera_id[:8]}...")

        return jsonify(result), response.status_code

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to start livestream for {camera_id} from {LIVESTREAM_API_URL}/streams/{camera_id}/start: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@livestream_proxy_bp.route('/streams/<camera_id>/stop', methods=['POST'])
@require_auth
def api_livestream_stop(camera_id):
    """Stop livestream for camera"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.post(
            f"{LIVESTREAM_API_URL}/streams/{camera_id}/stop",
            timeout=10
        )

        result = response.json()

        # Log successful stream stop
        if response.status_code == 200:
            logger.info(f"Livestream stopped for camera {camera_id[:8]}...")

        return jsonify(result), response.status_code

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to stop livestream for {camera_id} from {LIVESTREAM_API_URL}/streams/{camera_id}/stop: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@livestream_proxy_bp.route('/viewers', methods=['GET'])
@require_auth
def api_livestream_viewers():
    """Get all active viewers"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.get(f"{LIVESTREAM_API_URL}/viewers", timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get viewers from {LIVESTREAM_API_URL}/viewers: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@livestream_proxy_bp.route('/viewers/<camera_id>', methods=['GET'])
@require_auth
def api_livestream_camera_viewers(camera_id):
    """Get viewers for specific camera"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.get(
            f"{LIVESTREAM_API_URL}/viewers/{camera_id}",
            timeout=5
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get viewers for {camera_id} from {LIVESTREAM_API_URL}/viewers/{camera_id}: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@livestream_proxy_bp.route('/health', methods=['GET'])
def api_livestream_health():
    """Check livestream service health"""
    if not LIVESTREAM_ENABLED:
        return jsonify({
            "enabled": False,
            "status": "disabled"
        })

    try:
        response = requests.get(f"{LIVESTREAM_API_URL}/health", timeout=5)
        health = response.json()
        health['enabled'] = True
        return jsonify(health), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Livestream health check failed to {LIVESTREAM_API_URL}/health: {e}")
        return jsonify({
            "enabled": True,
            "status": "unavailable",
            "error": str(e)
        }), 503
