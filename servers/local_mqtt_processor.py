#!/usr/bin/env python3
"""
Local MQTT Event Processor - EMQX Edition
Subscribes to local EMQX broker and processes camera events into SQLite database
No AWS IoT dependencies - fully offline capable
"""

import json
import re
import signal
import sys
import os
import time
import logging
from datetime import datetime
from pathlib import Path
import paho.mqtt.client as mqtt

# Add config to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))

try:
    from settings import *
except ImportError as e:
    print(f"❌ Failed to import configuration: {e}")
    sys.exit(1)

from database_manager import CameraDatabaseManager
from telegram_notifier import get_telegram_notifier

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LocalMQTTProcessor:
    def __init__(self):
        self.broker_host = MQTT_BROKER_HOST
        self.broker_port = MQTT_BROKER_PORT
        self.client_id = PROCESSOR_CLIENT_ID
        self.keepalive = MQTT_KEEPALIVE

        self.client = None
        self.db = CameraDatabaseManager()
        self.telegram = get_telegram_notifier()  # Initialize Telegram notifier
        self.running = False

        # Define EMQX topics (direct topics, no bridge prefix)
        self.camera_topics = [
            'prod/device/message/hive-cam/+/activity/+',      # Activity events (motion/person)
            'prod/device/connection/hive-cam/+',              # Connection events
            'prod/device/status/hive-cam/+',                  # Status/heartbeat
            'prod/device/message/hive-cam/+/camera/state'     # Camera state changes
        ]

        # Load camera registry from database
        self.known_cameras = {}
        db_cameras = self.db.get_camera_status()
        for camera in db_cameras:
            self.known_cameras[camera['camera_id']] = {
                'name': camera['camera_name'],
                'ip': camera.get('ip_address'),
                'rtsp_url': f"rtsp://{camera.get('ip_address')}/stream0" if camera.get('ip_address') else None
            }

        logger.info(f"Local MQTT Event Processor initialized")
        logger.info(f"Broker: {self.broker_host}:{self.broker_port}")
        logger.info(f"Known cameras: {len(self.known_cameras)}")

    def on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            logger.info("Connected to local EMQX broker")

            # Subscribe to camera topics (direct EMQX topics, no bridge prefix)
            for topic in self.camera_topics:
                client.subscribe(topic, qos=1)
                logger.info(f"Subscribed to: {topic}")

        else:
            logger.error(f"Failed to connect to EMQX broker: {rc}")

    def on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        logger.warning("Disconnected from local MQTT broker")

    def on_message(self, client, userdata, msg):
        """Process incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')

            logger.debug(f"Received message on {topic}")

            # Extract camera ID from topic using protocol specification patterns
            # Handle both AWS IoT forwarded topics and direct local topics
            # Patterns: prod/device/message/hive-cam/{UUID}/... or camera/prod/device/message/hive-cam/{UUID}/...
            # Also handle honeycomb/{UUID} subscription topics
            camera_match = re.search(r'(?:hive-cam|honeycomb)/([A-F0-9]{32})(?:/|$)', topic)
            if not camera_match:
                logger.warning(f"Could not extract camera ID from topic: {topic}")
                return

            camera_id = camera_match.group(1)
            camera_info = self.known_cameras.get(camera_id, {})

            # Parse message payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON payload: {e}")
                return

            # Process different event types
            if '/activity/' in topic:
                self.process_activity_event(camera_id, camera_info, topic, data)
            elif '/connection/' in topic:
                self.process_connection_event(camera_id, camera_info, data)
            elif '/status/' in topic or '/camera/state' in topic:
                self.process_status_event(camera_id, camera_info, data)
            elif data.get('eventType') == 'DISCONNECT' or payload.upper() == 'DISCONNECT':
                self.process_disconnect_event(camera_id, camera_info, data)
            else:
                self.process_general_event(camera_id, camera_info, topic, data)

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def process_activity_event(self, camera_id, camera_info, topic, data):
        """Process activity/motion detection events"""
        try:
            # Protocol defines: eventId, activityType, timestamp, confidence, region
            event_id = data.get('eventId')
            activity_type = data.get('activityType', 'MOTION')
            timestamp = self._parse_timestamp(data.get('timestamp'))
            confidence = data.get('confidence')
            region = data.get('region')  # Object detection region information

            if not event_id:
                # Generate event ID if missing
                event_id = f"activity_{camera_id}_{int(timestamp)}"

            camera_name = camera_info.get('name') or f"Camera {camera_id[-8:]}"

            # Activity types from protocol: MOTION, AUDIO, PERSON, VEHICLE, etc.
            # Determine if this is start or stop based on topic structure
            if '/activity/start' in topic or data.get('eventType') == 'start':
                # Check if event already exists (thumbnail may have arrived first)
                existing_event = self.db.get_event_by_id(event_id)

                if existing_event:
                    # Event exists (thumbnail arrived first) - update it with start event details
                    logger.info(f"Activity START: Event {event_id[:8]}... already exists (thumbnail arrived first)")
                    self.db.update_activity_event(
                        event_id=event_id,
                        camera_name=camera_name,
                        activity_type=activity_type,
                        start_timestamp=timestamp,
                        confidence=confidence
                    )
                    logger.info(f"  ✅ Updated existing event with start details")

                    # Send initial Telegram notification
                    telegram_msg_id = self.telegram.send_initial_notification(
                        event_id=event_id,
                        camera_id=camera_id,
                        camera_name=camera_name,
                        activity_type=activity_type,
                        timestamp=timestamp
                    )

                    # Update with thumbnail if available (Telegram sends photo directly)
                    if telegram_msg_id and existing_event.get('thumbnail_path'):
                        logger.info(f"  📸 Thumbnail already available - sending Telegram photo")
                        self.telegram.update_notification_with_thumbnail(
                            event_id=event_id,
                            camera_id=camera_id,
                            camera_name=camera_name,
                            activity_type=activity_type,
                            timestamp=timestamp,
                            thumbnail_path=existing_event['thumbnail_path'],
                            telegram_msg_id=telegram_msg_id
                        )

                    # Store Telegram message ID
                    if telegram_msg_id:
                        self.db.update_activity_event(
                            event_id=event_id,
                            telegram_msg_id=telegram_msg_id,
                            telegram_notified=True
                        )
                else:
                    # Event doesn't exist - create it normally
                    self.db.add_activity_start_event(
                        event_id=event_id,
                        camera_id=camera_id,
                        camera_name=camera_name,
                        activity_type=activity_type,
                        timestamp=timestamp,
                        confidence=confidence
                    )
                    logger.info(f"Activity START: {activity_type} on {camera_name} (confidence: {confidence})")

                    # Send Telegram notification with 4-second wait for thumbnail
                    # This allows iOS notifications to show real thumbnails instead of placeholders
                    logger.info(f"⏱️  Waiting up to 4 seconds for thumbnail before sending Telegram notification...")

                    thumbnail_found = False
                    for i in range(8):  # Check 8 times over 4 seconds (0.5s intervals)
                        time.sleep(0.5)
                        updated_event = self.db.get_event_by_id(event_id)
                        if updated_event and updated_event.get('thumbnail_path'):
                            thumbnail_found = True
                            logger.info(f"📸 Thumbnail arrived during wait! Sending photo notification directly.")
                            break

                    if thumbnail_found:
                        # Thumbnail arrived within 4 seconds - send photo directly
                        telegram_msg_id = self.telegram.update_notification_with_thumbnail(
                            event_id=event_id,
                            camera_id=camera_id,
                            camera_name=camera_name,
                            activity_type=activity_type,
                            timestamp=timestamp,
                            thumbnail_path=updated_event['thumbnail_path'],
                            telegram_msg_id=None  # No existing message to update
                        )
                    else:
                        # No thumbnail yet - send text notification (will be updated later if thumbnail arrives)
                        logger.info(f"⏱️  No thumbnail after 4 seconds - sending text notification")
                        telegram_msg_id = self.telegram.send_initial_notification(
                            event_id=event_id,
                            camera_id=camera_id,
                            camera_name=camera_name,
                            activity_type=activity_type,
                            timestamp=timestamp
                        )

                    # Store Telegram message ID for future updates
                    if telegram_msg_id:
                        self.db.update_activity_event(
                            event_id=event_id,
                            telegram_msg_id=telegram_msg_id,
                            telegram_notified=True
                        )

            elif '/activity/stop' in topic or '/activity/end' in topic or data.get('eventType') in ['stop', 'end']:
                self.db.add_activity_end_event(
                    event_id=event_id,
                    timestamp=timestamp
                )
                logger.info(f"Activity END: {event_id}")

                # Activity ended - event details logged in database
                logger.debug(f"Activity ended: {event_id}")

            else:
                # Generic activity event - assume it's a start event
                self.db.add_activity_start_event(
                    event_id=event_id,
                    camera_id=camera_id,
                    camera_name=camera_name,
                    activity_type=activity_type,
                    timestamp=timestamp,
                    confidence=confidence
                )
                logger.info(f"Activity detected: {activity_type} on {camera_name} (confidence: {confidence})")

            # Update camera last_seen (but NOT status - status is for mode only)
            # NOTE: Do not update camera_name here - it's application data, not from camera
            self.db.update_camera_info(
                camera_id=camera_id,
                last_seen=timestamp
            )

        except Exception as e:
            logger.error(f"Error processing activity event: {e}")

    def process_connection_event(self, camera_id, camera_info, data):
        """Process camera connection events"""
        try:
            timestamp = self._parse_timestamp(data.get('timestamp'))
            status = data.get('status', 'unknown')
            camera_name = camera_info.get('name') or f"Camera {camera_id[-8:]}"

            # Extract device information from connection message according to protocol specs
            device_info = data.get('device', {})
            # Protocol defines: softwareVersion, hardwareVersion, serialNumber, deviceType
            firmware_version = device_info.get('softwareVersion')  # e.g., "V0_0_00_117RC_svn1356"
            hardware_version = device_info.get('hardwareVersion')
            serial_number = device_info.get('serialNumber')
            device_type = device_info.get('deviceType')

            self.db.add_status_event(
                camera_id=camera_id,
                event_type='connection',
                status=status,
                timestamp=timestamp,
                camera_name=camera_name,
                client_id=data.get('clientId'),
                ip_address=data.get('ipAddress') or camera_info.get('ip'),
                firmware_version=firmware_version,
                raw_payload=json.dumps(data)
            )

            # Update camera registry with firmware version from connection message
            # NOTE: Do not update camera_name (application data) or status (mode field)
            update_kwargs = {
                'camera_id': camera_id,
                'last_seen': timestamp
            }

            # Only update firmware version if present in the message
            if firmware_version:
                update_kwargs['firmware_version'] = firmware_version
                logger.info(f"  Firmware version: {firmware_version}")

            self.db.update_camera_info(**update_kwargs)

            # Get previous connection status before updating
            previous_status = None
            camera_data = self.db.get_camera_status(camera_id)
            if camera_data:
                previous_status = camera_data[0].get('connection_status') if camera_data else None

            # Update connection status (do NOT pass camera_name - it overwrites user-set names!)
            connection_status = 'connected' if status.lower() == 'connected' else 'disconnected'
            self.db.update_connection_status(camera_id, connection_status)

            # If camera just connected, restore its state
            if status.lower() == 'connected':
                self._restore_camera_state(camera_id, camera_name)

            logger.info(f"Connection event: {camera_name} - {status}")

            # Only send notifications if connection status actually changed
            if previous_status != connection_status:
                logger.info(f"📢 Connection status changed: {previous_status} → {connection_status}, sending notification")

                # Send Telegram notification
                self.telegram.send_connection_notification(
                    camera_id=camera_id,
                    camera_name=camera_name,
                    status=status,
                    timestamp=timestamp
                )
            else:
                logger.debug(f"Connection status unchanged ({connection_status}), skipping notification")

        except Exception as e:
            logger.error(f"Error processing connection event: {e}")

    def process_status_event(self, camera_id, camera_info, data):
        """Process camera status/heartbeat events"""
        try:
            timestamp = self._parse_timestamp(data.get('timestamp'))
            status = data.get('status', 'online')
            camera_name = camera_info.get('name') or f"Camera {camera_id[-8:]}"

            # Extract additional metadata from status message according to protocol specs
            battery_info = data.get('battery', {})
            radio_info = data.get('radio', {})
            ethernet_info = data.get('ethernet', {})

            # Battery information: level, voltage, chargingStatus, temperature
            battery_level = battery_info.get('level') if isinstance(battery_info, dict) else None
            battery_voltage = battery_info.get('voltage') if isinstance(battery_info, dict) else None
            charging_status = battery_info.get('chargingStatus') if isinstance(battery_info, dict) else None
            battery_temp = battery_info.get('temperature') if isinstance(battery_info, dict) else None

            # Radio information: signalStrength, networkType, carrier
            signal_strength = radio_info.get('signalStrength') if isinstance(radio_info, dict) else None
            network_type = radio_info.get('networkType') if isinstance(radio_info, dict) else None

            # Ethernet information: ipAddress, macAddress, linkStatus
            ip_address = ethernet_info.get('ipAddress') if isinstance(ethernet_info, dict) else None
            mac_address = ethernet_info.get('macAddress') if isinstance(ethernet_info, dict) else None

            kwargs = {
                'camera_name': camera_name,
                'battery_level': battery_level,
                'temperature': data.get('temperature'),
                'uptime': data.get('uptime'),
                'raw_payload': json.dumps(data)
            }

            self.db.add_status_event(
                camera_id=camera_id,
                event_type='status',
                status=status,
                timestamp=timestamp,
                **kwargs
            )

            # Extract IP address from ethernet info if available
            ethernet_info = data.get('ethernet', {})
            ip_address = ethernet_info.get('ipAddress') if isinstance(ethernet_info, dict) else None

            # Update camera registry (but NOT firmware version or status from heartbeat messages)
            # Status field is reserved for camera mode (ARMED/LIVESTREAMONLY/PRIVACY) only
            # NOTE: Do not update camera_name - it's application data, not from camera
            update_kwargs = {
                'camera_id': camera_id,
                'last_seen': timestamp
            }

            # Only update IP if we have a valid one from the message
            if ip_address:
                update_kwargs['ip_address'] = ip_address

            self.db.update_camera_info(**update_kwargs)

            # Update connection status based on status messages (heartbeats indicate connected)
            # Do NOT pass camera_name - it overwrites user-set names!
            if status.lower() in ['online', 'active']:
                self.db.update_connection_status(camera_id, 'connected')

            logger.debug(f"Status event: {camera_name} - {status}")

        except Exception as e:
            logger.error(f"Error processing status event: {e}")

    def process_disconnect_event(self, camera_id, camera_info, data):
        """Process camera disconnect/last will messages"""
        try:
            timestamp = self._parse_timestamp(data.get('timestamp'))
            camera_name = camera_info.get('name') or f"Camera {camera_id[-8:]}"

            # Log disconnect event
            self.db.add_status_event(
                camera_id=camera_id,
                event_type='disconnect',
                status='disconnected',
                timestamp=timestamp,
                camera_name=camera_name,
                raw_payload=json.dumps(data)
            )

            # Get previous connection status before updating
            previous_status = None
            camera_data = self.db.get_camera_status(camera_id)
            if camera_data:
                previous_status = camera_data[0].get('connection_status') if camera_data else None

            # Update connection status to disconnected (do NOT pass camera_name!)
            self.db.update_connection_status(camera_id, 'disconnected')

            # Update camera info
            # NOTE: Do not update camera_name or status here
            self.db.update_camera_info(
                camera_id=camera_id,
                last_seen=timestamp
            )

            logger.info(f"🔌 Camera disconnected: {camera_name}")

            # Only send notifications if connection status actually changed
            if previous_status != 'disconnected':
                logger.info(f"📢 Connection status changed: {previous_status} → disconnected, sending notification")

                # Send Telegram notification
                self.telegram.send_connection_notification(
                    camera_id=camera_id,
                    camera_name=camera_name,
                    status='disconnected',
                    timestamp=timestamp
                )
            else:
                logger.debug(f"Connection status unchanged (disconnected), skipping notification")

        except Exception as e:
            logger.error(f"Error processing disconnect event: {e}")

    def process_general_event(self, camera_id, camera_info, topic, data):
        """Process other general events"""
        try:
            timestamp = self._parse_timestamp(data.get('timestamp'))
            camera_name = camera_info.get('name') or f"Camera {camera_id[-8:]}"

            # Determine event type from data or topic
            event_type = 'message'
            if 'heartbeat' in str(data).lower():
                event_type = 'heartbeat'
            elif 'state' in topic:
                event_type = 'state'

            status = data.get('status', 'unknown')

            self.db.add_status_event(
                camera_id=camera_id,
                event_type=event_type,
                status=status,
                timestamp=timestamp,
                camera_name=camera_name,
                raw_payload=json.dumps(data)
            )

            # Update camera last seen
            # NOTE: Do not update camera_name - it's application data, not from camera
            self.db.update_camera_info(
                camera_id=camera_id,
                last_seen=timestamp
            )

            logger.debug(f"General event: {camera_name} - {event_type}")

        except Exception as e:
            logger.error(f"Error processing general event: {e}")

    def _parse_timestamp(self, timestamp_str):
        """Parse timestamp from various formats to Unix timestamp"""
        if not timestamp_str:
            return int(datetime.now().timestamp())

        try:
            # Try Unix timestamp first
            if isinstance(timestamp_str, (int, float)):
                return int(timestamp_str)

            # Try ISO format
            if isinstance(timestamp_str, str):
                if 'T' in timestamp_str:
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    return int(dt.timestamp())

            return int(datetime.now().timestamp())

        except Exception:
            return int(datetime.now().timestamp())

    def _restore_camera_state(self, camera_id, camera_name):
        """Restore camera state by sending stored settings"""
        try:
            # Get stored camera state
            stored_state = self.db.get_camera_state(camera_id)

            if not stored_state:
                logger.info(f"📤 No stored state to restore for {camera_name}")
                return

            # Send each stored setting back to the camera
            for setting_name, setting_info in stored_state.items():
                self._send_camera_setting(camera_id, setting_name, setting_info['value'])
                logger.info(f"📤 Restored {setting_name} = {setting_info['value']} for {camera_name}")

        except Exception as e:
            logger.error(f"Error restoring camera state for {camera_id}: {e}")

    def _send_camera_setting(self, camera_id, setting_name, setting_value):
        """Send a setting command to the camera via MQTT"""
        try:
            # Map setting names to MQTT topics according to protocol
            topic_mapping = {
                'mode': f'prod/honeycomb/{camera_id}/system/setmode',
                'detection_sensitivity': f'prod/honeycomb/{camera_id}/settings/detection',
                'recording_duration': f'prod/honeycomb/{camera_id}/settings/recording',
                'night_vision': f'prod/honeycomb/{camera_id}/settings/nightvision',
                'motion_zones': f'prod/honeycomb/{camera_id}/settings/motionzones'
            }

            topic = topic_mapping.get(setting_name)
            if not topic:
                logger.warning(f"Unknown setting type: {setting_name}")
                return

            # Create message payload according to protocol spec
            if setting_name == 'mode':
                message = {
                    "requestId": f"restore_{camera_id}_{int(datetime.now().timestamp())}",
                    "creationTimestamp": datetime.now().isoformat() + "Z",
                    "sourceId": camera_id,
                    "sourceType": "hive-cam",
                    "mode": setting_value
                }
            else:
                message = {
                    "requestId": f"restore_{camera_id}_{int(datetime.now().timestamp())}",
                    "creationTimestamp": datetime.now().isoformat() + "Z",
                    "sourceId": camera_id,
                    "sourceType": "hive-cam",
                    "settings": {setting_name: setting_value}
                }

            # Publish directly to EMQX broker
            if self.client:
                payload = json.dumps(message)
                self.client.publish(topic, payload, qos=1)
                logger.info(f"📤 Sent {setting_name} setting to {camera_id}")

        except Exception as e:
            logger.error(f"Error sending setting {setting_name} to camera {camera_id}: {e}")

    def start_processor(self):
        """Start the MQTT event processor"""
        logger.info("Starting Local MQTT Event Processor...")

        try:
            self.client = mqtt.Client(client_id=self.client_id)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message

            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port, self.keepalive)

            self.running = True
            self.client.loop_forever()

        except Exception as e:
            logger.error(f"Failed to start MQTT processor: {e}")
            return False

    def stop_processor(self):
        """Stop the MQTT event processor"""
        logger.info("Stopping Local MQTT Event Processor...")

        self.running = False

        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        logger.info("MQTT Event Processor stopped")

    def get_status(self):
        """Get processor status and statistics"""
        stats = self.db.get_database_stats()
        cameras = self.db.get_camera_status()

        return {
            'running': self.running,
            'broker': f"{self.broker_host}:{self.broker_port}",
            'client_id': self.client_id,
            'known_cameras': len(self.known_cameras),
            'database_stats': stats,
            'cameras': cameras
        }

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info('Received shutdown signal')
    if 'processor' in globals():
        processor.stop_processor()
    sys.exit(0)

def main():
    """Main function"""
    global processor

    print("🎯 Local MQTT Event Processor for Camera System")
    print("=" * 60)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create processor
    processor = LocalMQTTProcessor()

    # Show initial status
    status = processor.get_status()
    print(f"\n📊 Initial Status:")
    print(f"   Known Cameras: {status['known_cameras']}")
    print(f"   Database Events: {status['database_stats']['activity_events']}")

    print(f"\n📷 Camera Registry:")
    for camera in status['cameras']:
        print(f"   {camera['camera_name']}: {camera['status']} ({camera['last_seen_str']})")

    print(f"\n🚀 Starting processor...")
    processor.start_processor()

if __name__ == "__main__":
    main()