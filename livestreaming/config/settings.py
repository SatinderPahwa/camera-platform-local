"""
Livestreaming Configuration Settings

Production-grade configuration for camera BCGH livestreaming via Kurento Media Server.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
LOG_DIR.mkdir(exist_ok=True)

# Load environment variables from parent project's .env file
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    import warnings
    warnings.warn(f".env file not found at {env_file}")

# ============================================================================
# Kurento Media Server Configuration
# ============================================================================

# Kurento WebSocket URL
KURENTO_WS_URL = os.getenv("KURENTO_WS_URL", "ws://localhost:8888/kurento")

# STUN server for ICE candidate generation (both KMS and browser)
STUN_SERVER = os.getenv("STUN_SERVER", "stun.l.google.com")
STUN_PORT = int(os.getenv("STUN_PORT", "19302"))

# IP addresses for SDP offers
# LOCAL_IP: Used when viewer is on same local network (avoids NAT hairpinning issues)
# EXTERNAL_IP: Used when viewer is remote (requires port forwarding)
# The system automatically detects viewer location and uses appropriate IP
# REQUIRED: These must be set in .env file - no defaults provided
LOCAL_IP = os.getenv("LOCAL_IP")
EXTERNAL_IP = os.getenv("EXTERNAL_IP")
LOCAL_NETWORK_PREFIX = os.getenv("LOCAL_NETWORK_PREFIX")

# Kurento port range for RTP/RTCP
KMS_MIN_PORT = int(os.getenv("KMS_MIN_PORT", "5000"))
KMS_MAX_PORT = int(os.getenv("KMS_MAX_PORT", "5050"))

# ============================================================================
# Camera RTP Configuration
# ============================================================================

# Fixed ports for camera RTP streams (from POC2)
CAMERA_RTP_VIDEO_PORT = 5006
CAMERA_RTP_AUDIO_PORT = 5008
CAMERA_RTCP_PORT = 5007

# Bandwidth settings for REMB
MAX_VIDEO_RECV_BANDWIDTH = 5000  # Kbps (triggers REMB generation)
MIN_VIDEO_RECV_BANDWIDTH = 500   # Kbps

# ============================================================================
# Hive Camera SDP Requirements
# ============================================================================

# Custom SDP attributes required by Hive cameras
HIVE_SDP_ATTRIBUTES = {
    "x-skl-ssrca": True,  # Audio SSRC attribute
    "x-skl-ssrcv": True,  # Video SSRC attribute
    "x-skl-cname": True,  # CNAME attribute
}

# Default SDP values
DEFAULT_SDP_SESSION_NAME = "Camera Livestream"
DEFAULT_SDP_AUDIO_CODEC = "opus/48000/2"
DEFAULT_SDP_VIDEO_CODEC = "H264/90000"

# ============================================================================
# EMQX MQTT Configuration
# ============================================================================

# Broker settings
EMQX_BROKER_HOST = os.getenv("EMQX_BROKER_HOST", "127.0.0.1")
EMQX_BROKER_PORT = int(os.getenv("EMQX_BROKER_PORT", "8883"))
EMQX_CLIENT_ID = os.getenv("EMQX_LIVESTREAM_CLIENT_ID", "livestream_service")

# Certificate paths (for TLS connection)
EMQX_CA_CERT = os.getenv("EMQX_CA_CERT", str(PROJECT_ROOT / "certificates/ca.crt"))
EMQX_CLIENT_CERT = os.getenv("EMQX_CLIENT_CERT", str(PROJECT_ROOT / "certificates/camera_client.crt"))
EMQX_CLIENT_KEY = os.getenv("EMQX_CLIENT_KEY", str(PROJECT_ROOT / "certificates/camera_client.key"))

# MQTT topic patterns
MQTT_STREAM_PLAY_TOPIC = "prod/honeycomb/{camera_id}/stream/play"
MQTT_STREAM_STOP_TOPIC = "prod/honeycomb/{camera_id}/stream/stop"
MQTT_KEEPALIVE_TOPIC = "prod/honeycomb/{camera_id}/stream/keepalive"

# ============================================================================
# API Server Configuration
# ============================================================================

# API server settings
API_SERVER_HOST = os.getenv("API_SERVER_HOST", "0.0.0.0")
API_SERVER_PORT = int(os.getenv("API_SERVER_PORT", "8080"))

# CORS settings (for dashboard integration)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5000",  # Dashboard server
    "http://127.0.0.1:5000",
]

# Request timeout
API_REQUEST_TIMEOUT = 30  # seconds

# ============================================================================
# WebSocket Signaling Server Configuration
# ============================================================================

# Signaling server for WebRTC viewer connections
SIGNALING_SERVER_HOST = os.getenv("SIGNALING_SERVER_HOST", "0.0.0.0")
SIGNALING_SERVER_PORT = int(os.getenv("SIGNALING_SERVER_PORT", "8765"))

# WebSocket settings
WS_PING_INTERVAL = 30  # seconds
WS_PING_TIMEOUT = 10   # seconds

# ============================================================================
# Stream Session Configuration
# ============================================================================

# Keepalive settings (prevent camera timeout)
KEEPALIVE_INTERVAL = 15  # seconds (send every 15 seconds)
KEEPALIVE_TIMEOUT = 15  # seconds (fail if no response)

# Session timeouts
STREAM_START_TIMEOUT = 30   # seconds to start stream
STREAM_IDLE_TIMEOUT = 300   # seconds of no viewers before auto-stop
VIEWER_CONNECT_TIMEOUT = 20  # seconds for viewer to connect

# Maximum concurrent streams per camera
MAX_STREAMS_PER_CAMERA = 1  # Currently one stream per camera

# Maximum viewers per stream
MAX_VIEWERS_PER_STREAM = 10

# ============================================================================
# Database Configuration
# ============================================================================

# Use the main project database
DATABASE_PATH = str(DATA_DIR / "camera_events.db")

# Stream session table name
STREAM_SESSIONS_TABLE = "stream_sessions"
VIEWER_SESSIONS_TABLE = "viewer_sessions"

# ============================================================================
# Logging Configuration
# ============================================================================

# Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Log file paths
API_SERVER_LOG = str(LOG_DIR / "api_server.log")
SIGNALING_SERVER_LOG = str(LOG_DIR / "signaling_server.log")
STREAM_MANAGER_LOG = str(LOG_DIR / "stream_manager.log")
KURENTO_CLIENT_LOG = str(LOG_DIR / "kurento_client.log")

# Log rotation
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================================
# Security Configuration (Future: External Access)
# ============================================================================

# Authentication (disabled for local network use)
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", None)  # Set for production
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60

# Rate limiting (requests per minute)
RATE_LIMIT_ENABLED = False  # Enable for external access
RATE_LIMIT_REQUESTS = 60    # per IP per minute

# TLS/SSL (for HTTPS/WSS)
TLS_ENABLED = os.getenv("TLS_ENABLED", "false").lower() == "true"
TLS_CERT_PATH = os.getenv("TLS_CERT_PATH", None)
TLS_KEY_PATH = os.getenv("TLS_KEY_PATH", None)

# ============================================================================
# Feature Flags
# ============================================================================

# Enable/disable features
ENABLE_STREAM_RECORDING = False  # Future feature
ENABLE_STREAM_ANALYTICS = False  # Future feature
ENABLE_MULTI_BITRATE = False     # Future feature

# ============================================================================
# Development/Debug Settings
# ============================================================================

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Verbose logging for debugging
VERBOSE_SDP_LOGGING = DEBUG  # Log full SDP offers/answers
VERBOSE_ICE_LOGGING = DEBUG  # Log all ICE candidates

# Health check settings
HEALTH_CHECK_ENABLED = True
HEALTH_CHECK_INTERVAL = 60  # seconds

# ============================================================================
# Validation
# ============================================================================

def validate_config():
    """Validate configuration settings"""
    errors = []

    # Check required paths
    if not DATA_DIR.exists():
        errors.append(f"Data directory not found: {DATA_DIR}")

    # Check required network configuration
    if not LOCAL_IP:
        errors.append("LOCAL_IP must be set in environment (.env file)")

    if not EXTERNAL_IP:
        errors.append("EXTERNAL_IP must be set in environment (.env file)")

    if not LOCAL_NETWORK_PREFIX:
        errors.append("LOCAL_NETWORK_PREFIX must be set in environment (.env file)")

    # Check EMQX certificates
    if not os.path.exists(EMQX_CA_CERT):
        errors.append(f"EMQX CA certificate not found: {EMQX_CA_CERT}")
    if not os.path.exists(EMQX_CLIENT_CERT):
        errors.append(f"EMQX client certificate not found: {EMQX_CLIENT_CERT}")
    if not os.path.exists(EMQX_CLIENT_KEY):
        errors.append(f"EMQX client key not found: {EMQX_CLIENT_KEY}")

    # Check external IP is set to a valid value
    if EXTERNAL_IP == "0.0.0.0":
        errors.append("EXTERNAL_IP must be set to a routable IP address")

    # Warn if using old hardcoded values (from before production readiness fixes)
    if EXTERNAL_IP == "86.20.156.73":
        import warnings
        warnings.warn("EXTERNAL_IP is set to example value - update for your deployment")

    # Check Kurento URL format
    if not KURENTO_WS_URL.startswith("ws://") and not KURENTO_WS_URL.startswith("wss://"):
        errors.append("KURENTO_WS_URL must start with ws:// or wss://")

    # Check auth settings if enabled
    if AUTH_ENABLED and not JWT_SECRET_KEY:
        errors.append("JWT_SECRET_KEY must be set when AUTH_ENABLED=true")

    # Check TLS settings if enabled
    if TLS_ENABLED:
        if not TLS_CERT_PATH or not TLS_KEY_PATH:
            errors.append("TLS_CERT_PATH and TLS_KEY_PATH required when TLS_ENABLED=true")

    return errors

# Run validation on import
validation_errors = validate_config()
if validation_errors:
    import warnings
    for error in validation_errors:
        warnings.warn(f"Configuration warning: {error}")

# ============================================================================
# Helper Functions
# ============================================================================

def get_camera_mqtt_topic(camera_id: str, topic_type: str = "play") -> str:
    """Get MQTT topic for camera stream command"""
    topic_map = {
        "play": MQTT_STREAM_PLAY_TOPIC,
        "stop": MQTT_STREAM_STOP_TOPIC,
        "keepalive": MQTT_KEEPALIVE_TOPIC,
    }
    template = topic_map.get(topic_type, MQTT_STREAM_PLAY_TOPIC)
    return template.format(camera_id=camera_id)

def get_stun_url() -> str:
    """Get STUN server URL"""
    return f"stun:{STUN_SERVER}:{STUN_PORT}"

def get_external_connection_string(port: int) -> str:
    """Get external connection string for SDP"""
    return f"{EXTERNAL_IP}:{port}"

# ============================================================================
# Export Configuration
# ============================================================================

__all__ = [
    # Kurento
    "KURENTO_WS_URL",
    "STUN_SERVER",
    "STUN_PORT",
    "LOCAL_IP",
    "EXTERNAL_IP",
    "LOCAL_NETWORK_PREFIX",
    "KMS_MIN_PORT",
    "KMS_MAX_PORT",

    # Camera RTP
    "CAMERA_RTP_VIDEO_PORT",
    "CAMERA_RTP_AUDIO_PORT",
    "CAMERA_RTCP_PORT",
    "MAX_VIDEO_RECV_BANDWIDTH",
    "MIN_VIDEO_RECV_BANDWIDTH",

    # EMQX MQTT
    "EMQX_BROKER_HOST",
    "EMQX_BROKER_PORT",
    "EMQX_CLIENT_ID",
    "EMQX_CA_CERT",
    "EMQX_CLIENT_CERT",
    "EMQX_CLIENT_KEY",
    "get_camera_mqtt_topic",

    # API Server
    "API_SERVER_HOST",
    "API_SERVER_PORT",
    "CORS_ALLOWED_ORIGINS",

    # Signaling Server
    "SIGNALING_SERVER_HOST",
    "SIGNALING_SERVER_PORT",

    # Sessions
    "KEEPALIVE_INTERVAL",
    "MAX_STREAMS_PER_CAMERA",
    "MAX_VIEWERS_PER_STREAM",

    # Database
    "DATABASE_PATH",
    "STREAM_SESSIONS_TABLE",
    "VIEWER_SESSIONS_TABLE",

    # Logging
    "LOG_LEVEL",
    "LOG_FORMAT",
    "API_SERVER_LOG",
    "SIGNALING_SERVER_LOG",
    "STREAM_MANAGER_LOG",

    # Helpers
    "get_stun_url",
    "get_external_connection_string",
]
