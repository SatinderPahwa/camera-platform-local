#!/usr/bin/env python3
"""
Camera Platform Configuration Settings
Loads configuration from environment variables and .env file
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Load environment variables from .env file
env_file = PROJECT_ROOT / '.env'
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Loaded configuration from {env_file}")
else:
    print(f"⚠️  No .env file found - using environment variables only")
    print(f"💡 Run setup_platform.py to generate .env file")

# Helper function to get environment variables with defaults
def get_env(key: str, default=None, cast_type=str):
    """Get environment variable with type casting and default values"""
    value = os.getenv(key, default)
    if value is None:
        return None

    if cast_type == bool:
        # If value is already a bool (from default), return it directly
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('true', '1', 'yes', 'on')
    elif cast_type == int:
        return int(value)
    elif cast_type == float:
        return float(value)
    else:
        return str(value)

# ============================================================================
# EMQX Broker Configuration
# ============================================================================
EMQX_BROKER_ENDPOINT = get_env('EMQX_BROKER_ENDPOINT', 'camera.local')
EMQX_BROKER_PORT = get_env('EMQX_BROKER_PORT', 8883, int)

# ============================================================================
# Server Configuration
# ============================================================================
CONFIG_SERVER_HOST = get_env('CONFIG_SERVER_HOST', '0.0.0.0')
CONFIG_SERVER_PORT = get_env('CONFIG_SERVER_PORT', 80, int)
DASHBOARD_SERVER_HOST = get_env('DASHBOARD_SERVER_HOST', '0.0.0.0')
DASHBOARD_SERVER_PORT = get_env('DASHBOARD_SERVER_PORT', 5000, int)
DASHBOARD_URL = get_env('DASHBOARD_URL', f'http://localhost:5000')

# ============================================================================
# MQTT Configuration
# ============================================================================
MQTT_BROKER_HOST = get_env('MQTT_BROKER_HOST', '127.0.0.1')
MQTT_BROKER_PORT = get_env('MQTT_BROKER_PORT', 8883, int)
MQTT_KEEPALIVE = get_env('MQTT_KEEPALIVE', 60, int)
MQTT_USE_TLS = get_env('MQTT_USE_TLS', False, bool)
PROCESSOR_CLIENT_ID = get_env('PROCESSOR_CLIENT_ID', 'camera_event_processor')

# ============================================================================
# File Upload Configuration
# ============================================================================
UPLOAD_BASE_DIR = Path(get_env('UPLOAD_BASE_DIR', './data/uploads'))
if not UPLOAD_BASE_DIR.is_absolute():
    UPLOAD_BASE_DIR = PROJECT_ROOT / UPLOAD_BASE_DIR
UPLOAD_LOG_FILE = UPLOAD_BASE_DIR / "upload_log.txt"

# ============================================================================
# Certificate Configuration
# ============================================================================
CERT_BASE_DIR = PROJECT_ROOT / 'certificates'

# ============================================================================
# Database Configuration
# ============================================================================
DATABASE_PATH = Path(get_env('DATABASE_PATH', './data/camera_events.db'))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = PROJECT_ROOT / DATABASE_PATH

# ============================================================================
# Telegram Configuration
# ============================================================================
TELEGRAM_ENABLED = get_env('TELEGRAM_ENABLED', True, bool)
TELEGRAM_BOT_TOKEN = get_env('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = get_env('TELEGRAM_CHAT_ID', '')
TELEGRAM_NOTIFY_MOTION = get_env('TELEGRAM_NOTIFY_MOTION', True, bool)
TELEGRAM_NOTIFY_PERSON = get_env('TELEGRAM_NOTIFY_PERSON', True, bool)
TELEGRAM_NOTIFY_SOUND = get_env('TELEGRAM_NOTIFY_SOUND', False, bool)

# ============================================================================
# Authentication Configuration
# ============================================================================
FLASK_SECRET_KEY = get_env('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
ADMIN_USERNAME = get_env('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = get_env('ADMIN_PASSWORD', 'change-me')

# Google OAuth (Optional)
GOOGLE_CLIENT_ID = get_env('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = get_env('GOOGLE_CLIENT_SECRET', '')

# ============================================================================
# TURN Server Configuration
# ============================================================================
TURN_SERVER_URL = get_env('TURN_SERVER_URL', '')
TURN_SERVER_USERNAME = get_env('TURN_SERVER_USERNAME', '')
TURN_SERVER_PASSWORD = get_env('TURN_SERVER_PASSWORD', '')

# ============================================================================
# Logging Configuration
# ============================================================================
LOG_DIR = PROJECT_ROOT / 'logs'
LOG_LEVEL = get_env('LOG_LEVEL', 'INFO')

# ============================================================================
# Environment
# ============================================================================
ENVIRONMENT = get_env('ENVIRONMENT', 'production')
DEBUG = get_env('DEBUG', False, bool)

# ============================================================================
# Streaming Configuration
# ============================================================================
STREAM_OUTPUT_DIR = Path(get_env('STREAM_OUTPUT_DIR', '/tmp/hive_stream'))
VIDEO_PORT = get_env('VIDEO_PORT', 50434, int)
AUDIO_PORT = get_env('AUDIO_PORT', 32552, int)
LIVESTREAM_ENABLED = get_env('LIVESTREAM_ENABLED', True, bool)
LIVESTREAM_API_URL = get_env('LIVESTREAM_API_URL', 'http://localhost:8080')
LIVESTREAM_SIGNALING_URL = get_env('LIVESTREAM_SIGNALING_URL', 'ws://localhost:8765')

# Create required directories
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
STREAM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Configuration summary
def print_config_summary():
    """Print configuration summary for debugging"""
    if DEBUG:
        print("\n" + "="*60)
        print("🔧 CAMERA PLATFORM CONFIGURATION")
        print("="*60)
        print(f"📁 Project Root: {PROJECT_ROOT}")
        print(f"🌍 Environment: {ENVIRONMENT}")
        print(f"🔍 Debug Mode: {DEBUG}")
        print(f"📡 EMQX Broker: {EMQX_BROKER_ENDPOINT}:{EMQX_BROKER_PORT}")
        print(f"📊 Config Server: {CONFIG_SERVER_HOST}:{CONFIG_SERVER_PORT}")
        print(f"📱 Dashboard: {DASHBOARD_SERVER_HOST}:{DASHBOARD_SERVER_PORT}")
        print(f"📁 Upload Directory: {UPLOAD_BASE_DIR}")
        print(f"📁 Certificate Directory: {CERT_BASE_DIR}")
        print(f"📁 Database: {DATABASE_PATH}")
        print(f"📁 Log Directory: {LOG_DIR}")
        print(f"📱 Telegram Enabled: {TELEGRAM_ENABLED}")
        print("="*60 + "\n")

# Print config summary on import if debug enabled
if DEBUG:
    print_config_summary()
