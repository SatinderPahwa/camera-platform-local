#!/usr/bin/env python3
"""
Camera Dashboard Server - EMQX Edition
Flask web server providing camera management dashboard with event history and live streaming
No AWS IoT dependencies - fully offline capable
"""

import os
import sys
import json
import uuid
import logging
import requests
import zipfile
import io
import tempfile
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Add config and servers directories to path (must be before auth imports)
sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, jsonify, request, redirect, url_for, send_file, Response
import paho.mqtt.client as mqtt

# Import authentication modules
from auth import init_auth, require_auth
from auth_routes import auth_bp

try:
    from settings import *
except ImportError as e:
    print(f"❌ Failed to import configuration: {e}")
    sys.exit(1)

from database_manager import CameraDatabaseManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=str(Path(__file__).parent.parent / 'templates'))
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Configure authentication
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # 7 day sessions

# Initialize authentication
init_auth(app)

# Register authentication blueprint
app.register_blueprint(auth_bp)

# Initialize EMQX MQTT client for sending commands
mqtt_client = None
mqtt_connected = False
mqtt_lock = threading.Lock()

def on_mqtt_connect(client, userdata, flags, rc):
    """Callback for MQTT connection"""
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        logger.info("Dashboard connected to EMQX broker")
    else:
        mqtt_connected = False
        logger.error(f"Failed to connect to EMQX broker: {rc}")

def on_mqtt_disconnect(client, userdata, rc):
    """Callback for MQTT disconnection"""
    global mqtt_connected
    mqtt_connected = False
    logger.warning("Dashboard disconnected from EMQX broker")

def init_mqtt_client():
    """Initialize MQTT client in background thread"""
    global mqtt_client
    try:
        mqtt_client = mqtt.Client(client_id="camera_dashboard")
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect

        # Connect to local EMQX broker
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE)
        mqtt_client.loop_start()  # Start background thread

        logger.info(f"MQTT client connecting to {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    except Exception as e:
        logger.error(f"Failed to initialize MQTT client: {e}")
        mqtt_client = None

# Initialize MQTT client in background
init_mqtt_client()

class CameraController:
    """Controller for sending commands to cameras via EMQX MQTT"""

    def __init__(self, camera_id=None):
        self.camera_id = camera_id
        self.client = mqtt_client

    def generate_request_id(self):
        return str(uuid.uuid4())

    def send_mode_message(self, mode):
        """Send mode change message (ARMED/LIVESTREAMONLY/PRIVACY)"""
        topic = f"prod/honeycomb/{self.camera_id}/system/setmode"

        message = {
            "requestId": self.generate_request_id(),
            "creationTimestamp": datetime.utcnow().isoformat() + "Z",
            "sourceId": self.camera_id,
            "sourceType": "hive-cam",
            "mode": mode.upper(),
            "type": "NA",
            "durationMinutes": "NA",
            "intervalSeconds": "NA"
        }

        return self._publish_message(topic, message)

    def send_reboot_message(self, reason="web_interface"):
        """Send reboot command"""
        topic = f"prod/honeycomb/{self.camera_id}/system/reboot"

        message = {
            "requestId": self.generate_request_id(),
            "creationTimestamp": datetime.utcnow().isoformat() + "Z",
            "sourceId": self.camera_id,
            "sourceType": "hive-cam"
        }

        return self._publish_message(topic, message)

    def send_settings_message(self, settings):
        """Send camera settings update"""
        topic = f"prod/honeycomb/{self.camera_id}/settings/update"

        # Helper function to convert string booleans from form
        def to_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on')
            return default

        # Create base message with required fields
        message = {
            "requestId": self.generate_request_id(),
            "creationTimestamp": datetime.utcnow().isoformat() + "Z",
            "sourceId": self.camera_id,
            "sourceType": "hive-cam",
            # Default values for required fields if not provided in settings
            "resolution": settings.get("resolution", "720p"),
            "frameRate": settings.get("frameRate", "30"),
            "scheduleEnabled": to_bool(settings.get("scheduleEnabled"), False),
            "schedule": settings.get("schedule", []),
            "motionDetection": settings.get("motionDetection", "SMART"),
            "audioDetection": settings.get("audioDetection", "ALL"),
            "storage": settings.get("storage", "CLOUD"),
            "activityZone": settings.get("activityZone", "ALL"),
            "ledDot": to_bool(settings.get("ledDot"), True),
            "ledRing": to_bool(settings.get("ledRing"), True),
            "soundAlert": to_bool(settings.get("soundAlert"), True),
            "nightVision": settings.get("nightVision", "AUTO"),
            "invertImage": to_bool(settings.get("invertImage"), False),
            "cameraAudio": to_bool(settings.get("cameraAudio"), False),
            "cameraZoom": settings.get("cameraZoom", "1X"),
            "motionSensitivity": settings.get("motionSensitivity", "MEDIUM"),
            "audioSensitivity": settings.get("audioSensitivity", "MEDIUM"),
            "timeZone": settings.get("timeZone", "GMT"),
            "wdr": to_bool(settings.get("wdr"), False),
            "volume": settings.get("volume", "MEDIUM")
        }

        return self._publish_message(topic, message)

    def _publish_message(self, topic, message):
        """Publish message to EMQX broker"""
        global mqtt_connected

        if not self.client or not mqtt_connected:
            return {
                "success": False,
                "error": "MQTT client not connected to EMQX broker"
            }

        try:
            payload = json.dumps(message)
            result = self.client.publish(topic, payload, qos=1)

            # Check if publish succeeded (result.rc == 0 means success)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Sent message to {topic}: {message}")
                return {
                    "success": True,
                    "topic": topic,
                    "message": message
                }
            else:
                error_msg = f"MQTT publish failed with code {result.rc}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }

        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            return {
                "success": False,
                "error": str(e)
            }

class CameraDashboard:
    def __init__(self):
        self.db = CameraDatabaseManager()
        logger.info(f"Dashboard initialized with database-driven camera management")

    def get_camera_overview(self):
        """Get overview of all cameras with current status from database"""
        overview = []
        db_cameras = self.db.get_camera_status()

        for db_camera in db_cameras:
            camera_id = db_camera['camera_id']

            # Get recent activity count
            recent_activity = self.db.get_recent_activity_events(camera_id=camera_id, limit=10)
            activity_24h = len([event for event in recent_activity
                              if event['start_timestamp'] > (datetime.now().timestamp() - 86400)])

            overview.append({
                'id': camera_id,
                'name': db_camera['camera_name'] or f"Camera {camera_id[:8]}...",
                'ip': db_camera['ip_address'] or 'unknown',
                'status': db_camera['status'] or 'unknown',
                'connection_status': db_camera['connection_status'] or 'disconnected',
                'last_seen': db_camera['last_seen_str'],
                'connection_status_str': db_camera['connection_status_str'],
                'firmware_version': db_camera['firmware_version'] or 'Unknown',
                'activity_24h': activity_24h,
                'rtsp_url': f"rtsp://{db_camera['ip_address']}/stream0" if db_camera['ip_address'] else None
            })

        return overview

    def get_recent_events(self, limit=50, camera_id=None):
        """Get recent activity events across all cameras"""
        events = self.db.get_recent_activity_events(camera_id=camera_id, limit=limit)

        # Add additional info for display - get camera names from database
        db_cameras = {cam['camera_id']: cam['camera_name'] for cam in self.db.get_camera_status()}

        for event in events:
            event['camera_name'] = (
                db_cameras.get(event['camera_id']) or
                f"Camera {event['camera_id'][:8]}..."
            )
            event['duration_str'] = f"{event['duration_seconds']}s" if event['duration_seconds'] else "Unknown"

            # Add URLs for thumbnail and recording
            if event.get('thumbnail_path'):
                event['thumbnail_url'] = url_for('api_media_thumbnail', event_id=event['event_id'])
            else:
                event['thumbnail_url'] = None

            if event.get('recording_path'):
                event['recording_url'] = url_for('camera_recordings',
                                                  camera_id=event['camera_id']) + f"?event={event['event_id']}"
            else:
                event['recording_url'] = None

        return events

    def get_database_stats(self):
        """Get database statistics for dashboard"""
        return self.db.get_database_stats()

# Initialize dashboard
dashboard = CameraDashboard()

@app.route('/')
@require_auth
def index():
    """Main dashboard page"""
    camera_overview = dashboard.get_camera_overview()
    recent_events = dashboard.get_recent_events(limit=20)
    stats = dashboard.get_database_stats()

    return render_template('dashboard.html',
                         cameras=camera_overview,
                         recent_events=recent_events,
                         stats=stats,
                         page_title="Camera Dashboard")

@app.route('/api/cameras')
@require_auth
def api_cameras():
    """API endpoint for camera status"""
    return jsonify(dashboard.get_camera_overview())

@app.route('/api/events')
@require_auth
def api_events():
    """API endpoint for recent events"""
    camera_id = request.args.get('camera_id')
    limit = int(request.args.get('limit', 50))

    events = dashboard.get_recent_events(limit=limit, camera_id=camera_id)
    return jsonify(events)

@app.route('/api/stats')
@require_auth
def api_stats():
    """API endpoint for database statistics"""
    return jsonify(dashboard.get_database_stats())

@app.route('/api/recordings/<camera_id>')
@require_auth
def api_recordings(camera_id):
    """API endpoint for camera recordings with thumbnails"""
    try:
        # Get activity events with recordings
        events = dashboard.db.get_recent_activity_events(camera_id=camera_id, limit=1000)

        # Filter events that have recordings (recording_path or thumbnail_path populated)
        recordings = []
        for event in events:
            # Skip events without any media files
            if not event.get('recording_path') and not event.get('thumbnail_path'):
                continue

            # Format the recording entry
            recording = {
                'event_id': event['event_id'],
                'timestamp': event['start_timestamp'],
                'date': datetime.fromtimestamp(event['start_timestamp']).strftime('%Y-%m-%d'),
                'time': datetime.fromtimestamp(event['start_timestamp']).strftime('%H:%M'),
                'activity_type': event['activity_type'],
                'duration_seconds': event['duration_seconds'],
                'recording_filename': event.get('recording_filename'),
                'recording_path': event.get('recording_path'),
                'recording_size': event.get('recording_size'),
                'thumbnail_path': event.get('thumbnail_path'),
                'upload_status': event.get('upload_status', 'unknown')
            }
            recordings.append(recording)

        # Sort by timestamp descending (newest first)
        recordings.sort(key=lambda x: x['timestamp'], reverse=True)

        return jsonify({
            'camera_id': camera_id,
            'recordings': recordings,
            'total_count': len(recordings)
        })

    except Exception as e:
        logger.error(f"Failed to get recordings for {camera_id}: {e}")
        return jsonify({
            'error': str(e),
            'camera_id': camera_id
        }), 500

@app.route('/api/media/thumbnail/<event_id>')
def api_media_thumbnail(event_id):
    """Serve thumbnail image for an event (extracted from ZIP)"""
    try:
        # Get event from database
        event = dashboard.db.get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        thumbnail_path = event.get('thumbnail_path')

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            return jsonify({'error': 'Thumbnail not found'}), 404

        # Check if it's a ZIP file (camera uploads thumbnails as ZIP)
        if thumbnail_path.endswith('.zip'):
            try:
                with zipfile.ZipFile(thumbnail_path, 'r') as zip_file:
                    # Get list of files in ZIP
                    file_list = zip_file.namelist()

                    # Find the thumbnail image (usually a .jpeg or .jpg file)
                    image_file = None
                    for filename in file_list:
                        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                            image_file = filename
                            break

                    if not image_file:
                        return jsonify({'error': 'No image found in thumbnail ZIP'}), 404

                    # Extract and serve the image
                    image_data = zip_file.read(image_file)

                    # Determine content type
                    content_type = 'image/jpeg'
                    if image_file.lower().endswith('.png'):
                        content_type = 'image/png'

                    return Response(image_data, mimetype=content_type)

            except zipfile.BadZipFile:
                logger.error(f"Invalid ZIP file: {thumbnail_path}")
                return jsonify({'error': 'Invalid thumbnail file'}), 500
        else:
            # Direct image file (not ZIP)
            return send_file(thumbnail_path, mimetype='image/jpeg')

    except Exception as e:
        logger.error(f"Failed to serve thumbnail for {event_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/playlist/<event_id>.m3u8')
def api_media_playlist(event_id):
    """Generate HLS playlist for an event (from extracted files)"""
    try:
        # Get event from database
        event = dashboard.db.get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        recording_path = event.get('recording_path')

        if not recording_path or not os.path.exists(recording_path):
            return jsonify({'error': 'Recording not found'}), 404

        # Handle both folder and ZIP file paths
        # If recording_path points to ZIP, use parent folder (contains extracted files)
        if recording_path.endswith('.zip'):
            event_folder = Path(recording_path).parent
        else:
            event_folder = Path(recording_path)

        # Find all .ts segments in the extracted folder (prefer 1080p, fallback to 720p)
        segments_1080 = sorted(event_folder.glob('1080p/*.ts') or event_folder.glob('/1080p/*.ts'))
        segments_720 = sorted(event_folder.glob('720p/*.ts') or event_folder.glob('/720p/*.ts'))

        segments = segments_1080 if segments_1080 else segments_720

        if not segments:
            return jsonify({'error': 'No video segments found in recording'}), 404

        # Check for AES key
        aes_key_path = event_folder / 'aes.key' if (event_folder / 'aes.key').exists() else (event_folder / '/aes.key' if (event_folder / '/aes.key').exists() else None)

        # Generate HLS playlist
        playlist = "#EXTM3U\n"
        playlist += "#EXT-X-VERSION:3\n"
        playlist += "#EXT-X-TARGETDURATION:3\n"  # Camera uses 3-second segments
        playlist += "#EXT-X-MEDIA-SEQUENCE:0\n"

        # Add encryption key if present
        # Camera uses zero IV for all segments (required for Safari native HLS playback)
        if aes_key_path:
            playlist += f'#EXT-X-KEY:METHOD=AES-128,URI="/api/media/key/{event_id}",IV=0x00000000000000000000000000000000\n'

        # Add segments (sorted by segment number)
        # Camera uses 3-second segments (last segment may be shorter)
        segment_files = sorted(segments, key=lambda x: int(x.stem))
        for segment_path in segment_files:
            segment_name = segment_path.name
            playlist += "#EXTINF:3.0,\n"
            playlist += f"/api/media/segment/{event_id}/{segment_name}\n"

        playlist += "#EXT-X-ENDLIST\n"

        # Return with CORS headers for Safari compatibility
        response = Response(playlist, mimetype='application/vnd.apple.mpegurl')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        logger.error(f"Failed to generate playlist for {event_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/key/<event_id>')
def api_media_key(event_id):
    """Serve AES encryption key for HLS playback (from extracted folder)"""
    try:
        event = dashboard.db.get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        recording_path = event.get('recording_path')

        if not recording_path or not os.path.exists(recording_path):
            return jsonify({'error': 'Recording not found'}), 404

        # Handle both folder and ZIP file paths
        if recording_path.endswith('.zip'):
            event_folder = Path(recording_path).parent
        else:
            event_folder = Path(recording_path)

        # Check for AES key (with or without leading slash)
        aes_key_path = event_folder / 'aes.key'
        if not aes_key_path.exists():
            aes_key_path = event_folder / '/aes.key'

        if not aes_key_path.exists():
            return jsonify({'error': 'Encryption key not found'}), 404

        # Send file with CORS headers for Safari compatibility
        response = send_file(aes_key_path, mimetype='application/octet-stream')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        logger.error(f"Failed to serve key for {event_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/segment/<event_id>/<segment_name>')
def api_media_segment(event_id, segment_name):
    """Serve individual video segment for HLS playback (from extracted folder)"""
    try:
        event = dashboard.db.get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        recording_path = event.get('recording_path')

        if not recording_path or not os.path.exists(recording_path):
            return jsonify({'error': 'Recording not found'}), 404

        # Handle both folder and ZIP file paths
        if recording_path.endswith('.zip'):
            event_folder = Path(recording_path).parent
        else:
            event_folder = Path(recording_path)

        # Try both resolutions (prefer 1080p)
        segment_path_1080 = event_folder / '1080p' / segment_name
        segment_path_1080_slash = event_folder / '/1080p' / segment_name
        segment_path_720 = event_folder / '720p' / segment_name
        segment_path_720_slash = event_folder / '/720p' / segment_name

        segment_path = None
        if segment_path_1080.exists():
            segment_path = segment_path_1080
        elif segment_path_1080_slash.exists():
            segment_path = segment_path_1080_slash
        elif segment_path_720.exists():
            segment_path = segment_path_720
        elif segment_path_720_slash.exists():
            segment_path = segment_path_720_slash

        if not segment_path:
            return jsonify({'error': f'Segment not found: {segment_name}'}), 404

        # Send file with CORS headers for Safari compatibility
        response = send_file(segment_path, mimetype='video/MP2T')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        logger.error(f"Failed to serve segment {segment_name} for {event_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/download/<event_id>')
def api_media_download(event_id):
    """Download recording as MP4 file (handles AES-128 encrypted HLS segments)"""
    try:
        event = dashboard.db.get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        recording_path = event.get('recording_path')

        if not recording_path or not os.path.exists(recording_path):
            return jsonify({'error': 'Recording not found'}), 404

        # recording_path now points to event folder with extracted files
        event_folder = Path(recording_path)

        # Find all .ts segments (prefer 1080p, fallback to 720p)
        segments_1080 = sorted(event_folder.glob('1080p/*.ts'))
        segments_720 = sorted(event_folder.glob('720p/*.ts'))

        segments = segments_1080 if segments_1080 else segments_720

        if not segments:
            return jsonify({'error': 'No video segments found'}), 404

        # Check for AES encryption key
        aes_key_path = event_folder / 'aes.key'
        has_encryption = aes_key_path.exists()

        # Create temporary directory for ffmpeg processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create M3U8 playlist for ffmpeg (handles encryption automatically)
            playlist_path = temp_path / 'playlist.m3u8'
            with open(playlist_path, 'w') as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                f.write("#EXT-X-TARGETDURATION:10\n")
                f.write("#EXT-X-MEDIA-SEQUENCE:0\n")

                # Add encryption key if present
                if has_encryption:
                    f.write(f'#EXT-X-KEY:METHOD=AES-128,URI="{aes_key_path}"\n')

                # Add segments (sorted by segment number)
                for segment in sorted(segments, key=lambda x: int(x.stem)):
                    f.write("#EXTINF:10.0,\n")
                    f.write(f"{segment}\n")

                f.write("#EXT-X-ENDLIST\n")

            # Output MP4 file
            output_file = temp_path / f'{event_id}.mp4'

            # Use ffmpeg to convert HLS to MP4 (handles decryption automatically)
            cmd = [
                'ffmpeg',
                '-protocol_whitelist', 'file,http,https,tcp,tls,crypto',
                '-allowed_extensions', 'ALL',
                '-i', str(playlist_path),
                '-c', 'copy',
                '-movflags', '+faststart',  # Optimize for web playback
                str(output_file)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return jsonify({'error': 'Failed to convert recording to MP4'}), 500

            # Send the file
            return send_file(
                output_file,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=f'recording_{event_id}_{event.get("start_timestamp", "")}.mp4'
            )

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Conversion timeout'}), 500
    except Exception as e:
        logger.error(f"Failed to download recording for {event_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/camera/<camera_id>')
@require_auth
def camera_detail(camera_id):
    """Individual camera detail page"""
    # Get camera data from database
    camera_overview = dashboard.get_camera_overview()
    camera_info = next((cam for cam in camera_overview if cam['id'] == camera_id), None)

    if not camera_info:
        return "Camera not found", 404

    events = dashboard.get_recent_events(limit=100, camera_id=camera_id)

    return render_template('camera_detail.html',
                         camera=camera_info,
                         events=events,
                         page_title=f"{camera_info['name']} - Details")

@app.route('/camera/<camera_id>/recordings')
@require_auth
def camera_recordings(camera_id):
    """Camera recordings page with playback"""
    # Get camera data from database
    camera_overview = dashboard.get_camera_overview()
    camera_info = next((cam for cam in camera_overview if cam['id'] == camera_id), None)

    if not camera_info:
        return "Camera not found", 404

    return render_template('recordings.html',
                         camera=camera_info,
                         page_title=f"{camera_info['name']} - Recordings")

@app.route('/events')
@require_auth
def events_page():
    """Events history page with pagination and filters"""
    camera_filter = request.args.get('camera')
    activity_filter = request.args.get('activity')
    page = int(request.args.get('page', 1))
    page_size = 20

    # Map user-friendly filter to actual database event types
    # Database has exactly 3 event types: MOTION, MOTION_SMART, AUDIO_ALL
    activity_types = None
    if activity_filter:
        activity_type_map = {
            'PERSON': ['MOTION_SMART'],  # Person detection
            'MOTION': ['MOTION'],         # General motion detection
            'SOUND': ['AUDIO_ALL']        # Sound detection above threshold
        }
        activity_types = activity_type_map.get(activity_filter)

    # Get total count (fetch more than needed for pagination calculation)
    # We need to fetch all to calculate total pages, but with SQL filtering this is efficient
    all_events = dashboard.db.get_recent_activity_events(
        camera_id=camera_filter,
        activity_types=activity_types,
        limit=10000  # High limit to get all matching events for count
    )

    # Calculate pagination
    total_events = len(all_events)
    total_pages = (total_events + page_size - 1) // page_size  # Ceiling division
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    # Get events for current page (slice from already filtered results)
    events = all_events[start_idx:end_idx]

    # Add URLs for thumbnails and recordings
    for event in events:
        if event.get('thumbnail_path'):
            event['thumbnail_url'] = url_for('api_media_thumbnail', event_id=event['event_id'])
        else:
            event['thumbnail_url'] = None

        if event.get('recording_path'):
            event['recording_url'] = url_for('camera_recordings',
                                              camera_id=event['camera_id']) + f"?event={event['event_id']}"
        else:
            event['recording_url'] = None

    cameras = dashboard.get_camera_overview()

    return render_template('events.html',
                         events=events,
                         cameras=cameras,
                         selected_camera=camera_filter,
                         selected_activity=activity_filter,
                         page=page,
                         total_pages=total_pages,
                         total_events=total_events,
                         page_title="Activity Events")

# Camera control API endpoints
@app.route('/api/control/mode/<camera_id>/<mode>', methods=['POST'])
@require_auth
def api_control_mode(camera_id, mode):
    """Send mode change command to camera (ARMED/LIVESTREAMONLY/PRIVACY)"""
    if mode.upper() not in ['ARMED', 'LIVESTREAMONLY', 'PRIVACY']:
        return jsonify({
            "success": False,
            "error": f"Invalid mode: {mode}. Must be ARMED, LIVESTREAMONLY, or PRIVACY"
        }), 400

    controller = CameraController(camera_id=camera_id)
    result = controller.send_mode_message(mode)

    # Update camera status in database
    if result.get("success"):
        try:
            dashboard.db.update_camera_info(
                camera_id=camera_id,
                status=mode.lower()
            )
        except Exception as e:
            logger.error(f"Failed to update camera status in database: {e}")

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500

@app.route('/api/control/reboot/<camera_id>', methods=['POST'])
@require_auth
def api_control_reboot(camera_id):
    """Send reboot command to camera"""
    controller = CameraController(camera_id=camera_id)
    result = controller.send_reboot_message()

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500

@app.route('/api/control/settings/<camera_id>', methods=['POST'])
@require_auth
def api_control_settings(camera_id):
    """Send camera settings update and store in database"""
    try:
        settings = request.get_json()
        if not settings:
            return jsonify({
                "success": False,
                "error": "Settings data required"
            }), 400

        controller = CameraController(camera_id=camera_id)
        result = controller.send_settings_message(settings)

        if result["success"]:
            # Store each setting in database
            try:
                # List of settings that should be stored as booleans
                boolean_settings = ['ledDot', 'ledRing', 'soundAlert', 'invertImage',
                                   'cameraAudio', 'scheduleEnabled', 'wdr']

                for setting_name, setting_value in settings.items():
                    # Convert string booleans to actual booleans for boolean settings
                    if setting_name in boolean_settings and isinstance(setting_value, str):
                        setting_value = setting_value.lower() in ('true', '1', 'yes', 'on')

                    # Determine setting type
                    if isinstance(setting_value, bool):
                        setting_type = 'boolean'
                    elif isinstance(setting_value, int):
                        setting_type = 'integer'
                    elif isinstance(setting_value, (list, dict)):
                        setting_type = 'json'
                    else:
                        setting_type = 'string'

                    # Convert value to string for storage
                    if isinstance(setting_value, (list, dict)):
                        value_str = json.dumps(setting_value)
                    else:
                        value_str = str(setting_value)

                    dashboard.db.set_camera_state(
                        camera_id=camera_id,
                        setting_name=setting_name,
                        setting_value=value_str,
                        setting_type=setting_type
                    )

                logger.info(f"Stored {len(settings)} settings for camera {camera_id}")
                result['database_stored'] = True
                result['settings_count'] = len(settings)
            except Exception as e:
                logger.error(f"Failed to store settings in database: {e}")
                result['database_stored'] = False
                result['database_error'] = str(e)
                # Don't fail the request if database storage fails

            return jsonify(result)
        else:
            return jsonify(result), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/control/settings/<camera_id>', methods=['GET'])
@require_auth
def api_get_settings(camera_id):
    """Get stored camera settings from database"""
    try:
        settings_data = dashboard.db.get_camera_state(camera_id)

        # get_camera_state returns dict like: {"setting_name": {"value": "...", "type": "...", "timestamp": ...}}
        settings_dict = {}
        for setting_name, setting_info in settings_data.items():
            setting_value = setting_info['value']
            setting_type = setting_info['type']

            # Convert value back to original type
            if setting_type == 'boolean':
                settings_dict[setting_name] = setting_value.lower() in ('true', '1', 'yes')
            elif setting_type == 'integer':
                settings_dict[setting_name] = int(setting_value)
            elif setting_type == 'json':
                settings_dict[setting_name] = json.loads(setting_value)
            else:
                # For strings, check if it's a boolean-like value (form submissions send "true"/"false" as strings)
                if setting_value.lower() in ('true', 'false'):
                    settings_dict[setting_name] = setting_value.lower() == 'true'
                else:
                    settings_dict[setting_name] = setting_value

        return jsonify({
            "success": True,
            "camera_id": camera_id,
            "settings": settings_dict,
            "settings_count": len(settings_dict)
        })

    except Exception as e:
        logger.error(f"Failed to get settings for {camera_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/control/rename/<camera_id>', methods=['POST'])
@require_auth
def api_control_rename(camera_id):
    """Rename a camera"""
    try:
        data = request.get_json() or {}
        new_name = data.get('name', '').strip()

        if not new_name:
            return jsonify({
                "success": False,
                "error": "Camera name cannot be empty"
            }), 400

        # Update camera name in database
        dashboard.db.update_camera_info(
            camera_id=camera_id,
            camera_name=new_name
        )

        logger.info(f"Renamed camera {camera_id} to '{new_name}'")

        return jsonify({
            "success": True,
            "camera_id": camera_id,
            "name": new_name,
            "message": f"Camera renamed to '{new_name}'"
        })

    except Exception as e:
        logger.error(f"Failed to rename camera {camera_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/aws/status')
def api_aws_status():
    """Check AWS IoT connection status"""
    return jsonify({
        "aws_iot_available": iot_client is not None,
        "region": AWS_REGION,
        "timestamp": datetime.now().isoformat()
    })

# =============================================================================
# Livestreaming API Proxy Endpoints
# =============================================================================

# Livestreaming API configuration
LIVESTREAM_API_URL = os.getenv('LIVESTREAM_API_URL', 'http://localhost:8080')
LIVESTREAM_ENABLED = os.getenv('LIVESTREAM_ENABLED', 'true').lower() == 'true'

@app.route('/api/livestream/streams', methods=['GET'])
@require_auth
def api_livestream_list():
    """List all active livestreams"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.get(f"{LIVESTREAM_API_URL}/streams", timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get livestreams: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@app.route('/api/livestream/streams/<camera_id>', methods=['GET'])
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
        logger.error(f"Failed to get livestream for {camera_id}: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@app.route('/api/livestream/streams/<camera_id>/start', methods=['POST'])
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
        logger.error(f"Failed to start livestream for {camera_id}: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@app.route('/api/livestream/streams/<camera_id>/stop', methods=['POST'])
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
        logger.error(f"Failed to stop livestream for {camera_id}: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@app.route('/api/livestream/viewers', methods=['GET'])
@require_auth
def api_livestream_viewers():
    """Get all active viewers"""
    if not LIVESTREAM_ENABLED:
        return jsonify({"error": "Livestreaming not enabled"}), 503

    try:
        response = requests.get(f"{LIVESTREAM_API_URL}/viewers", timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get viewers: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@app.route('/api/livestream/viewers/<camera_id>', methods=['GET'])
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
        logger.error(f"Failed to get viewers for {camera_id}: {e}")
        return jsonify({"error": "Livestreaming service unavailable"}), 503

@app.route('/api/livestream/health', methods=['GET'])
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
        logger.error(f"Livestream health check failed: {e}")
        return jsonify({
            "enabled": True,
            "status": "unavailable",
            "error": str(e)
        }), 503

@app.route('/livestream/viewer')
@require_auth
def livestream_viewer():
    """Livestream viewer page"""
    camera_id = request.args.get('camera', '')

    # TURN server configuration (optional) - loaded from settings.py
    turn_config = {
        'url': TURN_SERVER_URL,
        'username': TURN_SERVER_USERNAME,
        'password': TURN_SERVER_PASSWORD
    }

    # Debug logging
    logger.info(f"🔄 TURN Config being passed to template: {turn_config}")

    return render_template('livestream_viewer.html',
                         camera_id=camera_id,
                         livestream_api_url=LIVESTREAM_API_URL,
                         signaling_url=os.getenv('LIVESTREAM_SIGNALING_URL', 'ws://localhost:8765'),
                         turn_config=turn_config,
                         page_title="Livestream Viewer")

# =============================================================================
# Admin Panel Endpoints
# =============================================================================

@app.route('/admin')
@require_auth
def admin_page():
    """Admin panel page"""
    stats = dashboard.get_database_stats()
    cameras = dashboard.get_camera_overview()

    # Calculate storage statistics
    storage_stats = {
        'total_events': stats.get('activity_events', 0),
        'total_cameras': len(cameras),
        'events_24h': stats.get('activity_events_24h', 0)
    }

    return render_template('admin.html',
                         cameras=cameras,
                         stats=stats,
                         storage_stats=storage_stats,
                         page_title="Admin Panel")

@app.route('/api/admin/cleanup', methods=['POST'])
@require_auth
def api_admin_cleanup():
    """Trigger cleanup of old recordings"""
    try:
        data = request.get_json() or {}
        days_to_keep = int(data.get('days', 28))
        dry_run = data.get('dry_run', False)

        if days_to_keep < 1:
            return jsonify({
                "success": False,
                "error": "days must be at least 1"
            }), 400

        # Import cleanup script
        import subprocess
        import tempfile

        # Build command
        cleanup_script = str(Path(__file__).parent.parent / 'tools' / 'cleanup_old_recordings.py')
        cmd = [sys.executable, cleanup_script, '--days', str(days_to_keep), '--skip-confirmation']

        if dry_run:
            cmd.append('--dry-run')

        # Run cleanup script and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            # Parse output for statistics
            output_lines = result.stdout.split('\n')

            # Extract stats from output (look for summary section)
            stats = {
                'events_deleted': 0,
                'files_deleted': 0,
                'orphaned_db_entries': 0,
                'space_freed': '0 B',
                'dry_run': dry_run
            }

            for line in output_lines:
                # Parse both dry-run and actual run output
                if 'Events to delete from DB:' in line or 'Events processed:' in line:
                    stats['events_deleted'] = int(line.split(':')[-1].strip())
                elif 'Files to delete:' in line or 'Files deleted:' in line:
                    stats['files_deleted'] = int(line.split(':')[-1].strip())
                elif 'Orphaned DB entries' in line:
                    stats['orphaned_db_entries'] = int(line.split(':')[-1].strip())
                elif 'Total space to free:' in line or 'Space freed:' in line:
                    stats['space_freed'] = line.split(':')[-1].strip()

            return jsonify({
                "success": True,
                "stats": stats,
                "output": result.stdout,
                "message": f"Cleanup {'preview' if dry_run else 'completed'} successfully"
            })
        else:
            logger.error(f"Cleanup failed: {result.stderr}")
            return jsonify({
                "success": False,
                "error": "Cleanup script failed",
                "details": result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Cleanup operation timed out"
        }), 500
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/admin/storage/stats', methods=['GET'])
@require_auth
def api_admin_storage_stats():
    """Get detailed storage statistics by scanning filesystem"""
    try:
        import sqlite3
        from datetime import datetime, timedelta

        # Since recording_size is not populated in database, scan filesystem instead
        upload_dir = UPLOAD_BASE_DIR

        now = int(datetime.now().timestamp())
        week_ago = now - (7 * 86400)
        two_weeks_ago = now - (14 * 86400)
        month_ago = now - (28 * 86400)

        # Initialize counters
        stats_by_age = {
            'week': {'count': 0, 'size_bytes': 0},
            'two_weeks': {'count': 0, 'size_bytes': 0},
            'month': {'count': 0, 'size_bytes': 0},
            'older_than_month': {'count': 0, 'size_bytes': 0}
        }

        total_size_bytes = 0
        total_count = 0

        # Scan upload directory
        if upload_dir.exists():
            for camera_dir in upload_dir.iterdir():
                if not camera_dir.is_dir():
                    continue

                for category_dir in camera_dir.iterdir():
                    if not category_dir.is_dir():
                        continue

                    # Files can be directly in category_dir OR in event_id subdirectories
                    for item in category_dir.iterdir():
                        # Skip system files
                        if item.name.startswith('.') or item.name in ['upload_log.txt', 'Thumbs.db']:
                            continue

                        files_to_scan = []

                        # If it's a directory (event_id), scan files inside it
                        if item.is_dir():
                            for file_path in item.iterdir():
                                if file_path.is_file():
                                    files_to_scan.append(file_path)
                        # If it's a file directly in category_dir
                        elif item.is_file():
                            files_to_scan.append(item)

                        # Process all collected files
                        for file_path in files_to_scan:
                            # Skip system files
                            if file_path.name.startswith('.') or file_path.name in ['upload_log.txt', 'Thumbs.db', 'aes.key']:
                                continue

                            # Only count actual recording files (activity ZIPs and thumbnails)
                            recording_extensions = {'.zip', '.jpg', '.jpeg', '.png'}
                            if file_path.suffix.lower() not in recording_extensions:
                                continue

                            try:
                                # Get file size and modification time
                                file_size = file_path.stat().st_size
                                file_mtime = int(file_path.stat().st_mtime)

                                total_size_bytes += file_size
                                total_count += 1

                                # Categorize by age
                                if file_mtime > week_ago:
                                    stats_by_age['week']['count'] += 1
                                    stats_by_age['week']['size_bytes'] += file_size

                                if file_mtime > two_weeks_ago:
                                    stats_by_age['two_weeks']['count'] += 1
                                    stats_by_age['two_weeks']['size_bytes'] += file_size

                                if file_mtime > month_ago:
                                    stats_by_age['month']['count'] += 1
                                    stats_by_age['month']['size_bytes'] += file_size
                                elif file_mtime <= month_ago:
                                    stats_by_age['older_than_month']['count'] += 1
                                    stats_by_age['older_than_month']['size_bytes'] += file_size

                            except (OSError, PermissionError) as e:
                                logger.warning(f"Could not stat file {file_path}: {e}")
                                continue

        return jsonify({
            "success": True,
            "total_size_bytes": total_size_bytes,
            "total_size_mb": round(total_size_bytes / 1024 / 1024, 2),
            "total_count": total_count,
            "by_age": {
                "week": {
                    "count": stats_by_age['week']['count'],
                    "size_mb": round(stats_by_age['week']['size_bytes'] / 1024 / 1024, 2)
                },
                "two_weeks": {
                    "count": stats_by_age['two_weeks']['count'],
                    "size_mb": round(stats_by_age['two_weeks']['size_bytes'] / 1024 / 1024, 2)
                },
                "month": {
                    "count": stats_by_age['month']['count'],
                    "size_mb": round(stats_by_age['month']['size_bytes'] / 1024 / 1024, 2)
                },
                "older_than_month": {
                    "count": stats_by_age['older_than_month']['count'],
                    "size_mb": round(stats_by_age['older_than_month']['size_bytes'] / 1024 / 1024, 2)
                }
            }
        })
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/admin/camera/add', methods=['POST'])
@require_auth
def api_admin_add_camera():
    """Add a new camera - creates AWS IoT resources and database entry"""
    try:
        data = request.get_json() or {}
        camera_id = data.get('camera_id', '').strip().upper()
        camera_name = data.get('camera_name', '').strip()
        camera_ip = data.get('camera_ip', '').strip()

        # Validate input
        if not camera_id or not camera_name:
            return jsonify({
                "success": False,
                "error": "camera_id and camera_name are required"
            }), 400

        # Validate camera ID format (32 hex characters)
        if len(camera_id) != 32 or not all(c in '0123456789ABCDEFabcdef' for c in camera_id):
            return jsonify({
                "success": False,
                "error": "Invalid camera ID format. Must be 32 hex characters."
            }), 400

        # Call the add_camera tool via subprocess (use current Python interpreter from venv)
        add_camera_script = str(Path(__file__).parent.parent / 'tools' / 'add_camera.py')
        cmd = [sys.executable, add_camera_script, camera_id, camera_name, camera_ip or 'unknown']

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            # Parse output for certificate paths
            cert_dir = str(Path(__file__).parent.parent / 'certificates' / camera_id)

            return jsonify({
                "success": True,
                "camera_id": camera_id,
                "camera_name": camera_name,
                "camera_ip": camera_ip,
                "cert_dir": cert_dir,
                "output": result.stdout,
                "message": f"Camera {camera_name} added successfully"
            })
        else:
            logger.error(f"Add camera failed: {result.stderr}")
            return jsonify({
                "success": False,
                "error": "Failed to add camera",
                "details": result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Camera registration timed out"
        }), 500
    except Exception as e:
        logger.error(f"Add camera failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/admin/camera/push_config', methods=['POST'])
@require_auth
def api_admin_push_config():
    """Push configuration files to camera via FTP"""
    try:
        data = request.get_json() or {}
        camera_id = data.get('camera_id', '').strip().upper()
        camera_ip = data.get('camera_ip', '').strip()
        camera_password = data.get('camera_password', '').strip()
        server_ip = data.get('server_ip', '').strip()

        if not all([camera_id, camera_ip, camera_password, server_ip]):
            return jsonify({
                "success": False,
                "error": "camera_id, camera_ip, camera_password, and server_ip are required"
            }), 400

        # If server_ip doesn't include port and CONFIG_SERVER_PORT is not 443 (HTTPS default), append it
        if ':' not in server_ip and CONFIG_SERVER_PORT != 443:
            server_ip = f"{server_ip}:{CONFIG_SERVER_PORT}"

        cert_dir = Path(__file__).parent.parent / 'certificates' / camera_id
        mqtt_ca_file = cert_dir / 'working_mqttCA.crt'
        ca_bundle_file = Path(__file__).parent.parent / 'camera_setup' / 'ready_to_push' / 'ca-bundle.trust.crt'
        cali_mqtt_ca_file = Path(__file__).parent.parent / 'camera_setup' / 'ready_to_push' / 'cali-mqttCA.crt'

        if not mqtt_ca_file.exists():
            return jsonify({
                "success": False,
                "error": f"mqttCA.crt not found for camera {camera_id}"
            }), 404

        if not ca_bundle_file.exists():
            return jsonify({
                "success": False,
                "error": f"ca-bundle.trust.crt not found at {ca_bundle_file}. Run camera_setup/build_camera_files.py to generate it."
            }), 404

        if not cali_mqtt_ca_file.exists():
            return jsonify({
                "success": False,
                "error": f"cali-mqttCA.crt not found at {cali_mqtt_ca_file}. Run camera_setup/build_camera_files.py to generate it."
            }), 404

        steps = []

        # Step 1: Upload ca-bundle.trust.crt via FTP (for HTTPS config server authentication)
        try:
            cmd = [
                'curl', '-T', str(ca_bundle_file),
                f'ftp://{camera_ip}/etc/ssl/certs/ca-bundle.trust.crt',
                '--user', f'root:{camera_password}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                steps.append(f"✓ Uploaded ca-bundle.trust.crt to /etc/ssl/certs/ (729 KB)")
            else:
                return jsonify({
                    "success": False,
                    "error": "Failed to upload ca-bundle.trust.crt via FTP",
                    "details": result.stderr
                }), 500

        except subprocess.TimeoutExpired:
            return jsonify({
                "success": False,
                "error": "FTP upload timeout for ca-bundle - check camera connectivity"
            }), 500

        # Step 2: Upload mqttCA.crt via FTP
        try:
            cmd = [
                'curl', '-T', str(mqtt_ca_file),
                f'ftp://{camera_ip}/root/certs/mqttCA.crt',
                '--user', f'root:{camera_password}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                steps.append("✓ Uploaded mqttCA.crt to /root/certs/mqttCA.crt (1187 bytes)")
            else:
                return jsonify({
                    "success": False,
                    "error": "Failed to upload mqttCA.crt via FTP",
                    "details": result.stderr
                }), 500

        except subprocess.TimeoutExpired:
            return jsonify({
                "success": False,
                "error": "FTP upload timeout - check camera connectivity"
            }), 500

        # Step 3: Upload cali-mqttCA.crt via FTP to /cali/certs/
        try:
            cmd = [
                'curl', '-T', str(cali_mqtt_ca_file),
                f'ftp://{camera_ip}/cali/certs/mqttCA.crt',
                '--user', f'root:{camera_password}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                steps.append("✓ Uploaded mqttCA.crt to /cali/certs/mqttCA.crt (3.5 KB)")
            else:
                return jsonify({
                    "success": False,
                    "error": "Failed to upload cali-mqttCA.crt via FTP",
                    "details": result.stderr
                }), 500

        except subprocess.TimeoutExpired:
            return jsonify({
                "success": False,
                "error": "FTP upload timeout for cali-mqttCA.crt"
            }), 500

        # Step 4: Download masterctrl.db from camera via FTP, update it, and push back
        try:
            import sqlite3

            # Create a temporary file for the database
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
                tmp_db_path = tmp_db.name

            # Download database from camera via FTP
            cmd = [
                'curl', '-o', tmp_db_path,
                f'ftp://{camera_ip}/cali/master_ctrl.db',
                '--user', f'root:{camera_password}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                steps.append(f"⚠ Could not download masterctrl.db from camera (manual update may be needed)")
                logger.warning(f"FTP download failed for {camera_ip}: {result.stderr}")
            else:
                # Update the database with server IP
                try:
                    conn = sqlite3.connect(tmp_db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE serverConf SET configSrvHost=? WHERE ID=1", (server_ip,))
                    conn.commit()
                    conn.close()

                    # Upload updated database back to camera
                    cmd = [
                        'curl', '-T', tmp_db_path,
                        f'ftp://{camera_ip}/cali/master_ctrl.db',
                        '--user', f'root:{camera_password}'
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                    if result.returncode == 0:
                        steps.append(f"✓ Updated masterctrl.db with server IP: {server_ip}")
                    else:
                        steps.append(f"⚠ Could not upload masterctrl.db to camera (manual update may be needed)")
                        logger.warning(f"FTP upload of database failed for {camera_ip}: {result.stderr}")

                except sqlite3.Error as e:
                    steps.append(f"⚠ Could not update masterctrl.db (database error: {str(e)})")
                    logger.error(f"SQLite error updating database: {e}")
                finally:
                    # Clean up temp file
                    if os.path.exists(tmp_db_path):
                        os.unlink(tmp_db_path)

        except subprocess.TimeoutExpired:
            steps.append("⚠ FTP timeout - skipping masterctrl.db update (manual update needed)")
        except Exception as e:
            steps.append(f"⚠ Error updating masterctrl.db: {str(e)}")
            logger.error(f"Error updating database: {e}")

        # Step 3: Send reboot command via telnet (since SSH is not available)
        steps.append("✓ Configuration complete - camera should be rebooted manually")

        return jsonify({
            "success": True,
            "camera_id": camera_id,
            "camera_ip": camera_ip,
            "steps": steps,
            "message": "Configuration pushed successfully"
        })

    except Exception as e:
        logger.error(f"Push config failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/admin/camera/<camera_id>/files', methods=['GET'])
@require_auth
def api_admin_camera_files(camera_id):
    """Get download URLs for camera setup files"""
    try:
        cert_dir = Path(__file__).parent.parent / 'certificates' / camera_id

        if not cert_dir.exists():
            return jsonify({
                "success": False,
                "error": "Camera certificates not found"
            }), 404

        # Check which files exist
        files = {
            "mqttCA_crt": (cert_dir / "working_mqttCA.crt").exists(),
            "cert_pem": (cert_dir / "cert.pem").exists(),
            "key_pem": (cert_dir / "key.pem").exists(),
            "info_json": (cert_dir / "info.json").exists()
        }

        return jsonify({
            "success": True,
            "camera_id": camera_id,
            "files": files,
            "cert_dir": str(cert_dir)
        })

    except Exception as e:
        logger.error(f"Failed to check camera files: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/admin/camera/<camera_id>/download/<filename>', methods=['GET'])
@require_auth
def api_admin_download_file(camera_id, filename):
    """Download camera setup files"""
    try:
        # Whitelist allowed files
        allowed_files = {
            'mqttCA.crt': 'working_mqttCA.crt',
            'cert.pem': 'cert.pem',
            'key.pem': 'key.pem',
            'info.json': 'info.json'
        }

        if filename not in allowed_files:
            return jsonify({"error": "File not allowed"}), 403

        cert_dir = Path(__file__).parent.parent / 'certificates' / camera_id
        file_path = cert_dir / allowed_files[filename]

        if not file_path.exists():
            return jsonify({"error": "File not found"}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        return jsonify({"error": str(e)}), 500

def run_slack_cleanup_job(job_id, mode):
    """Background function to run Slack cleanup"""
    try:
        with slack_cleanup_jobs_lock:
            slack_cleanup_jobs[job_id]['status'] = 'running'
            slack_cleanup_jobs[job_id]['started_at'] = datetime.now().isoformat()

        # Build command
        script_path = str(Path(__file__).parent.parent / 'tools' / 'slack_cleanup_channel.py')
        cmd = [sys.executable, script_path]

        if mode == '24h':
            cmd.extend(['--older-than', '24h'])
        # If mode is 'all', no additional args needed

        logger.info(f"Running Slack cleanup job {job_id}: {' '.join(cmd)}")

        # Run the cleanup script
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        # Parse output to extract statistics
        # Look for lines like:
        #   ✅ Deleted: 175
        #   ⚠️  Skipped: 2
        #   ❌ Failed: 1
        #   📊 Total: 178

        deleted = 0
        skipped = 0
        failed = 0
        total = 0

        for line in result.stdout.split('\n'):
            if '✅ Deleted:' in line:
                deleted = int(line.split(':')[1].strip())
            elif '⚠️  Skipped:' in line or 'Skipped:' in line:
                skipped = int(line.split(':')[1].strip())
            elif '❌ Failed:' in line:
                failed = int(line.split(':')[1].strip())
            elif '📊 Total:' in line:
                total = int(line.split(':')[1].strip())

        with slack_cleanup_jobs_lock:
            if result.returncode == 0:
                slack_cleanup_jobs[job_id]['status'] = 'completed'
                slack_cleanup_jobs[job_id]['result'] = {
                    'deleted': deleted,
                    'skipped': skipped,
                    'failed': failed,
                    'total': total
                }
                slack_cleanup_jobs[job_id]['output'] = result.stdout
                logger.info(f"Slack cleanup job {job_id} completed successfully")
            else:
                slack_cleanup_jobs[job_id]['status'] = 'failed'
                slack_cleanup_jobs[job_id]['error'] = result.stderr or "Unknown error"
                logger.error(f"Slack cleanup job {job_id} failed: {result.stderr}")

            slack_cleanup_jobs[job_id]['completed_at'] = datetime.now().isoformat()

    except subprocess.TimeoutExpired:
        with slack_cleanup_jobs_lock:
            slack_cleanup_jobs[job_id]['status'] = 'failed'
            slack_cleanup_jobs[job_id]['error'] = 'Job timed out after 10 minutes'
            slack_cleanup_jobs[job_id]['completed_at'] = datetime.now().isoformat()
        logger.error(f"Slack cleanup job {job_id} timed out")

    except Exception as e:
        with slack_cleanup_jobs_lock:
            slack_cleanup_jobs[job_id]['status'] = 'failed'
            slack_cleanup_jobs[job_id]['error'] = str(e)
            slack_cleanup_jobs[job_id]['completed_at'] = datetime.now().isoformat()
        logger.error(f"Slack cleanup job {job_id} failed with exception: {e}")

@app.route('/api/admin/slack/cleanup', methods=['POST'])
@require_auth
def api_admin_slack_cleanup():
    """Start background Slack cleanup job"""
    try:
        data = request.get_json() or {}
        mode = data.get('mode', 'all')  # 'all' or '24h'

        if mode not in ['all', '24h']:
            return jsonify({
                "success": False,
                "error": "Invalid mode. Must be 'all' or '24h'"
            }), 400

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Initialize job tracking
        with slack_cleanup_jobs_lock:
            slack_cleanup_jobs[job_id] = {
                'status': 'pending',
                'mode': mode,
                'created_at': datetime.now().isoformat(),
                'progress': {
                    'deleted': 0,
                    'skipped': 0,
                    'failed': 0
                }
            }

        # Start background thread
        thread = threading.Thread(
            target=run_slack_cleanup_job,
            args=(job_id, mode),
            daemon=True
        )
        thread.start()

        logger.info(f"Started Slack cleanup job {job_id} (mode: {mode})")

        return jsonify({
            "success": True,
            "job_id": job_id,
            "message": f"Slack cleanup job started (mode: {mode})"
        })

    except Exception as e:
        logger.error(f"Failed to start Slack cleanup job: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/admin/slack/cleanup/<job_id>/status', methods=['GET'])
@require_auth
def api_admin_slack_cleanup_status(job_id):
    """Get status of Slack cleanup job"""
    try:
        with slack_cleanup_jobs_lock:
            if job_id not in slack_cleanup_jobs:
                return jsonify({
                    "success": False,
                    "error": "Job not found"
                }), 404

            job = slack_cleanup_jobs[job_id]

            response = {
                "success": True,
                "job_id": job_id,
                "status": job['status'],
                "mode": job['mode'],
                "created_at": job['created_at']
            }

            if job['status'] == 'running':
                response['started_at'] = job.get('started_at')
                response['progress'] = job.get('progress', {})

            elif job['status'] == 'completed':
                response['completed_at'] = job.get('completed_at')
                response['result'] = job.get('result', {})
                response['output'] = job.get('output', '')

            elif job['status'] == 'failed':
                response['completed_at'] = job.get('completed_at')
                response['error'] = job.get('error', 'Unknown error')

            return jsonify(response)

    except Exception as e:
        logger.error(f"Failed to get Slack cleanup job status: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        stats = dashboard.get_database_stats()
        overview = dashboard.get_camera_overview()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'cameras': len(overview),
            'events': stats.get('activity_events', 0),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# PWA Support
@app.route('/service-worker.js')
def serve_service_worker():
    """
    Serve service worker from root path to give it proper scope.

    Service workers can only control pages within their scope.
    By serving from root (/service-worker.js), it gets scope=/
    which allows it to control all pages for PWA functionality.

    Also sets proper cache headers to ensure browser always gets latest version.
    """
    static_dir = Path(__file__).parent.parent / 'static'
    response = send_file(static_dir / 'service-worker.js', mimetype='application/javascript')
    # Prevent caching to ensure service worker updates are picked up
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (manifest, icons, etc.)"""
    static_dir = Path(__file__).parent.parent / 'static'
    return send_file(static_dir / filename)

def main():
    """Run the dashboard server"""
    print("📱 Camera Dashboard Server")
    print("=" * 50)

    # Show initial status
    overview = dashboard.get_camera_overview()
    stats = dashboard.get_database_stats()

    print(f"\n📊 Dashboard Status:")
    print(f"   Cameras: {len(overview)}")
    print(f"   Database Events: {stats['activity_events']}")
    print(f"   Status Events: {stats['status_events']}")

    print(f"\n📷 Camera Status:")
    for camera in overview:
        print(f"   {camera['name']}: {camera['status']} ({camera['activity_24h']} events 24h)")

    # SSL configuration for dashboard (optional - for browser HTTPS access)
    # Use dashboard-specific certificates (e.g., Let's Encrypt for iOS Safari support)
    ssl_context = None
    ssl_cert = os.getenv('DASHBOARD_SSL_CERT_FILE')
    ssl_key = os.getenv('DASHBOARD_SSL_KEY_FILE')

    if ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        ssl_context = (ssl_cert, ssl_key)
        protocol = "https"
        print(f"\n🔒 Dashboard SSL enabled with certificate: {ssl_cert}")
    else:
        protocol = "http"
        print(f"\n⚠️  Dashboard running HTTP (browsers will work, but iOS Safari WebRTC requires HTTPS)")

    print(f"🌐 Starting dashboard server...")
    print(f"   URL: {protocol}://{DASHBOARD_SERVER_HOST}:{DASHBOARD_SERVER_PORT}")

    app.run(
        host=DASHBOARD_SERVER_HOST,
        port=DASHBOARD_SERVER_PORT,
        debug=DEBUG,
        use_reloader=False,  # Prevent Flask from forking reloader process
        threaded=True,  # Enable multi-threading to handle concurrent requests
        ssl_context=ssl_context
    )

if __name__ == "__main__":
    main()