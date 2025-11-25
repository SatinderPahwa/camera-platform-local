#!/usr/bin/env python3
"""
Enhanced HTTPS Config Server with File Upload Service
EMQX Edition - No AWS IoT dependency
"""

import json
import ssl
import socket
import os
import sys
import uuid
import re
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

# Add config directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))
try:
    from settings import *
except ImportError as e:
    print(f"❌ Failed to import settings: {e}")
    print("Make sure config/settings.py exists")
    sys.exit(1)

# Import database manager and telegram notifier
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from database_manager import CameraDatabaseManager
from telegram_notifier import get_telegram_notifier

# Initialize database connection
db = CameraDatabaseManager(str(DATABASE_PATH))

# Initialize Telegram notifier
telegram = get_telegram_notifier()

def parse_event_id_from_filename(filename):
    """
    Parse event_id from camera upload filename.

    Pattern: {event_id}-{seq}-{part}.zip
    Example: 379ec4f5-46a8-492b-b3b4-d390553f8a70-1-0.zip

    Returns:
        str: event_id (UUID) or None if not found
    """
    # Match pattern: UUID-number-number.zip
    pattern = r'^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})-\d+-\d+\.zip$'
    match = re.match(pattern, filename, re.IGNORECASE)

    if match:
        return match.group(1)
    return None

class ConfigHandler(BaseHTTPRequestHandler):
    # Set timeout for request handling (prevents hung connections)
    timeout = 60

    def do_GET(self):
        # Log all incoming requests
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] REQUEST: {self.command} {self.path}", flush=True)
        print(f"[{timestamp}] Client: {self.client_address}", flush=True)

        # Handle the request
        path = urlparse(self.path).path

        if path.startswith('/hivecam/cert/'):
            camera_id = path.split('/hivecam/cert/')[-1]
            self.send_certificate_response(camera_id)
        elif path.startswith('/hivecam/'):
            camera_id = path.split('/hivecam/')[-1]
            self.send_config_response(camera_id)
        elif path == '/health':
            self.send_health_response()
        else:
            print(f"[{timestamp}] ERROR: Unknown endpoint: {path}")
            self.send_error(404, "Not Found")

    def do_POST(self):
        # Handle POST requests (for file service)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] POST REQUEST: {self.path}", flush=True)

        path = urlparse(self.path).path

        if path == '/fileservice/presignedUploadUrl':
            self.handle_presigned_upload_request()
        elif path.startswith('/fileservice/upload/'):
            self.handle_direct_upload()
        else:
            # Log POST requests and handle same as GET for backwards compatibility
            self.do_GET()

    def do_PUT(self):
        # Handle PUT requests (direct file upload)
        self.handle_direct_upload()

    def send_health_response(self):
        """Health check endpoint"""
        response = json.dumps({"status": "healthy", "service": "config_server"})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response.encode())

    def send_config_response(self, camera_id):
        """Send camera configuration with EMQX broker endpoint"""
        # EMQX-based config (no AWS IoT)
        config = {
            "mqtt": {
                "broker": EMQX_BROKER_ENDPOINT,
                "port": EMQX_BROKER_PORT,
                "topics": {
                    "connect": f"prod/device/connection/hive-cam/{camera_id}",
                    "disconnect": f"prod/device/connection/hive-cam/{camera_id}",
                    "status": f"prod/device/status/hive-cam/{camera_id}",
                    "publish": f"prod/device/message/hive-cam/{camera_id}",
                    "subscribe": f"prod/honeycomb/{camera_id}"
                }
            },
            "timeServer": "time.google.com",
            "wakeupInterval": 604800,
            "statusInterval": 600,
            "fileUploadServerUrl": f"https://{CONFIG_SERVER_HOST}:{CONFIG_SERVER_PORT}/fileservice",
            "firmwareServerUrl": f"https://{CONFIG_SERVER_HOST}:{CONFIG_SERVER_PORT}/firmware",
            "certificateServerUrl": f"https://{CONFIG_SERVER_HOST}:{CONFIG_SERVER_PORT}"
        }

        response = json.dumps(config, indent=2)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response.encode())

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] SUCCESS: Config response sent to camera: {camera_id}")
        print(f"[{timestamp}] MQTT Broker: {EMQX_BROKER_ENDPOINT}:{EMQX_BROKER_PORT}")

    def send_certificate_response(self, camera_id):
        """Return EMQX certificates (shared by all cameras)"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            # Use shared certificates (same for all cameras)
            cert_dir = CERT_BASE_DIR
            ca_path = cert_dir / "ca.crt"
            cert_path = cert_dir / "camera_client.crt"
            key_path = cert_dir / "camera_client.key"

            # Check if certificates exist
            if not all([ca_path.exists(), cert_path.exists(), key_path.exists()]):
                print(f"[{timestamp}] ERROR: Certificates not found in {cert_dir}")
                print(f"  CA: {ca_path.exists()}")
                print(f"  Cert: {cert_path.exists()}")
                print(f"  Key: {key_path.exists()}")
                self.send_error(404, "Certificates not found - run setup_platform.py first")
                return

            # Read certificate files
            with open(cert_path, 'r') as f:
                client_cert = f.read().strip()

            with open(key_path, 'r') as f:
                client_key = f.read().strip()

            with open(ca_path, 'r') as f:
                ca_cert = f.read().strip()

            cert_response = {
                "certificatePem": client_cert.strip(),
                "privateKey": client_key.strip(),
                "caCertificate": ca_cert.strip()
            }

            response = json.dumps(cert_response, separators=(',', ':'))

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except Exception as e:
            print(f"[{timestamp}] ERROR: Failed to read certificates: {e}")
            self.send_error(500, "Certificate read error")
            return

        print(f"[{timestamp}] SUCCESS: EMQX certificates sent to camera: {camera_id}")

    def handle_presigned_upload_request(self):
        """Handle presigned upload URL requests"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode('utf-8')
                request_data = json.loads(body)
            else:
                self.send_error(400, "No request body")
                return

            filename = request_data.get('fileName')
            category = request_data.get('category', 'unknown')
            metadata = request_data.get('metadata', {})

            # Extract camera ID from metadata
            camera_id = metadata.get('x-amz-meta-sourceId', 'unknown')

            print(f"[{timestamp}] FILE UPLOAD REQUEST:")
            print(f"  Camera: {camera_id}")
            print(f"  Filename: {filename}")
            print(f"  Category: {category}")

            if metadata:
                print(f"  Metadata: {json.dumps(metadata, indent=4)}")

            # Generate unique upload URL
            upload_id = str(uuid.uuid4())
            upload_url = f"https://{CONFIG_SERVER_HOST}:{CONFIG_SERVER_PORT}/fileservice/upload/{camera_id}/{category}/{upload_id}/{filename}"

            # Create response
            response = {
                "url": upload_url
            }

            response_json = json.dumps(response)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json.encode())

            print(f"[{timestamp}] SUCCESS: Presigned URL generated for {camera_id}/{filename}")

        except Exception as e:
            print(f"[{timestamp}] ERROR: Failed to handle presigned upload request: {e}")
            error_response = {
                "code": "FS2001",
                "message": "Unexpected Error"
            }
            error_json = json.dumps(error_response)
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(error_json)))
            self.end_headers()
            self.wfile.write(error_json.encode())

    def handle_direct_upload(self):
        """Handle direct file upload via PUT"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            # Parse upload URL: /fileservice/upload/{camera_id}/{category}/{upload_id}/{filename}
            path_parts = self.path.strip('/').split('/')
            if len(path_parts) >= 6 and path_parts[0] == 'fileservice' and path_parts[1] == 'upload':
                url_camera_id = path_parts[2]
                category = path_parts[3]
                upload_id = path_parts[4]
                filename = '/'.join(path_parts[5:])
            else:
                self.send_error(400, "Invalid upload URL format")
                return

            # Extract actual camera ID and event ID from metadata headers
            camera_id = self.headers.get('x-amz-meta-sourceId', url_camera_id)
            event_id = self.headers.get('x-amz-meta-eventId')

            print(f"[{timestamp}] DIRECT UPLOAD:")
            print(f"  Camera: {camera_id}")
            print(f"  Category: {category}")
            print(f"  Filename: {filename}")
            if event_id:
                print(f"  Event ID: {event_id}")

            # Create directory structure
            upload_dir = UPLOAD_BASE_DIR / camera_id / category
            os.makedirs(upload_dir, exist_ok=True)
            os.chmod(upload_dir, 0o755)

            # Read file data
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                file_data = self.rfile.read(content_length)

                # Get event_id from metadata header or parse from filename
                db_event_id = event_id if event_id else parse_event_id_from_filename(filename)

                # For activity recordings, use event folder structure
                if category == "activity" and db_event_id:
                    event_folder = upload_dir / db_event_id
                    os.makedirs(event_folder, exist_ok=True)
                    os.chmod(event_folder, 0o755)

                    zip_file_path = event_folder / filename
                    with open(zip_file_path, 'wb') as f:
                        f.write(file_data)
                    os.chmod(zip_file_path, 0o644)

                    print(f"  ✓ ZIP saved: {zip_file_path} ({len(file_data)} bytes)")

                    # Extract ZIP contents
                    if filename.endswith('.zip') and file_data.startswith(b'PK'):
                        try:
                            with zipfile.ZipFile(zip_file_path, 'r') as zf:
                                zf.extractall(event_folder)
                            print(f"  ✓ ZIP extracted to {event_folder}")
                            file_path = str(event_folder)
                        except zipfile.BadZipFile as e:
                            print(f"  ⚠️  Failed to extract ZIP: {e}")
                            file_path = str(zip_file_path)
                    else:
                        file_path = str(zip_file_path)

                else:
                    # For thumbnails, save to event folder
                    if category == "thumbnail" and db_event_id:
                        activity_dir = UPLOAD_BASE_DIR / camera_id / "activity"
                        event_folder = activity_dir / db_event_id
                        os.makedirs(event_folder, exist_ok=True)
                        os.chmod(event_folder, 0o755)

                        file_path = os.path.join(event_folder, "thumbnail.zip")
                        with open(file_path, 'wb') as f:
                            f.write(file_data)
                        os.chmod(file_path, 0o644)

                        print(f"  ✓ Thumbnail saved: {file_path}")
                    else:
                        # Other files
                        file_path = os.path.join(upload_dir, filename)
                        with open(file_path, 'wb') as f:
                            f.write(file_data)
                        os.chmod(file_path, 0o644)
                        print(f"  ✓ File saved: {file_path}")

                # Update database with file paths
                if db_event_id:
                    try:
                        event = db.get_event_by_id(db_event_id)

                        if event:
                            update_data = {}

                            if category == "activity":
                                if not event.get('recording_path'):
                                    update_data['recording_filename'] = filename
                                    update_data['recording_path'] = file_path
                                    update_data['upload_status'] = 'completed'
                                    print(f"  📊 Updating database: activity recording")

                            elif category == "thumbnail":
                                if not event.get('thumbnail_path'):
                                    update_data['thumbnail_path'] = file_path
                                    print(f"  📊 Updating database: thumbnail")

                            if update_data:
                                db.update_activity_event(db_event_id, **update_data)
                                print(f"  ✅ Database updated")

                                # Send Telegram notification with thumbnail
                                if category == "thumbnail":
                                    import time
                                    time.sleep(0.5)
                                    updated_event = db.get_event_by_id(db_event_id)

                                    if updated_event and updated_event.get('telegram_msg_id'):
                                        try:
                                            telegram_result = telegram.update_notification_with_thumbnail(
                                                event_id=db_event_id,
                                                camera_id=camera_id,
                                                camera_name=updated_event.get('camera_name'),
                                                activity_type=updated_event.get('activity_type', 'MOTION'),
                                                timestamp=updated_event.get('start_timestamp', int(datetime.now().timestamp())),
                                                thumbnail_path=file_path,
                                                telegram_msg_id=updated_event.get('telegram_msg_id')
                                            )
                                            if telegram_result:
                                                print(f"  ✅ Telegram notification sent")
                                        except Exception as e:
                                            print(f"  ⚠️  Telegram notification failed: {e}")
                        else:
                            # Event doesn't exist - create it
                            print(f"  🆕 Creating event {db_event_id}")

                            activity_type = self.headers.get('x-amz-meta-activityType', 'MOTION')
                            start_timestamp = int(datetime.now().timestamp())

                            db.add_activity_start_event(
                                event_id=db_event_id,
                                camera_id=camera_id,
                                camera_name=None,
                                activity_type=activity_type,
                                timestamp=start_timestamp,
                                confidence=None
                            )

                            # Update with file paths
                            update_fields = {}
                            if category == "thumbnail":
                                update_fields['thumbnail_path'] = file_path
                            elif category == "activity":
                                update_fields['recording_path'] = file_path
                                update_fields['recording_filename'] = filename
                                update_fields['upload_status'] = 'completed'

                            if update_fields:
                                db.update_activity_event(db_event_id, **update_fields)

                            print(f"  ✅ Event created in database")

                    except Exception as e:
                        print(f"  ❌ Database update failed: {e}")

                # Send success response
                self.send_response(200)
                self.end_headers()

            else:
                self.send_error(400, "No file content")

        except Exception as e:
            print(f"[{timestamp}] ERROR: Failed to handle upload: {e}")
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()

def main():
    host = CONFIG_SERVER_HOST
    port = CONFIG_SERVER_PORT

    print("=" * 70)
    print("🎯 Enhanced Config Server - EMQX Edition")
    print("=" * 70)
    print(f"Starting on {host}:{port}")
    print()
    print("Endpoints:")
    print("  GET  /hivecam/{camera_id}      - Camera config (EMQX broker)")
    print("  GET  /hivecam/cert/{camera_id} - EMQX certificates (shared)")
    print("  POST /fileservice/presignedUploadUrl - File upload URLs")
    print("  PUT  /fileservice/upload/*     - Direct file upload")
    print("  GET  /health                   - Health check")
    print()
    print(f"📡 EMQX Broker: {EMQX_BROKER_ENDPOINT}:{EMQX_BROKER_PORT}")
    print(f"📁 Upload Directory: {UPLOAD_BASE_DIR}/")
    print(f"📜 Certificates: {CERT_BASE_DIR}/")
    print()

    # Create SSL context using config server certificates
    config_ssl_cert = os.getenv('CONFIG_SSL_CERT_FILE', 'certificates/broker.crt')
    config_ssl_key = os.getenv('CONFIG_SSL_KEY_FILE', 'certificates/broker.key')

    # Convert to absolute path if relative
    if not os.path.isabs(config_ssl_cert):
        config_ssl_cert = os.path.join(os.path.dirname(os.path.dirname(__file__)), config_ssl_cert)
    if not os.path.isabs(config_ssl_key):
        config_ssl_key = os.path.join(os.path.dirname(os.path.dirname(__file__)), config_ssl_key)

    if not os.path.exists(config_ssl_cert) or not os.path.exists(config_ssl_key):
        print("❌ ERROR: SSL certificates not found!")
        print(f"   Cert: {config_ssl_cert}")
        print(f"   Key: {config_ssl_key}")
        print()
        print("💡 Run setup_platform.py to generate certificates")
        sys.exit(1)

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.load_cert_chain(str(config_ssl_cert), str(config_ssl_key))

    print(f"🔒 Using SSL certificate: {config_ssl_cert}")
    print()

    # Use ThreadingHTTPServer for concurrent request handling
    server = ThreadingHTTPServer((host, port), ConfigHandler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.socket.settimeout(60)

    print("✅ Server ready - cameras will connect to EMQX broker")
    print("=" * 70)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n⏹️  Server stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
