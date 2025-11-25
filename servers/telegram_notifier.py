#!/usr/bin/env python3
"""
Telegram Notification Service for Camera Activity Events
Sends notifications with thumbnail images and livestream links when motion/person detection occurs
"""

import json
import requests
import os
import sys
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from io import BytesIO

# Add config to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))
try:
    from settings import *
except ImportError as e:
    print(f"❌ Failed to import settings: {e}")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Handles sending Telegram notifications for camera events with photos and buttons"""

    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.dashboard_url = DASHBOARD_URL

        self.enabled = TELEGRAM_ENABLED and bool(self.bot_token) and bool(self.chat_id)
        self.notify_motion = TELEGRAM_NOTIFY_MOTION
        self.notify_person = TELEGRAM_NOTIFY_PERSON
        self.notify_sound = TELEGRAM_NOTIFY_SOUND

        # Telegram Bot API base URL
        self.api_base_url = f"https://api.telegram.org/bot{self.bot_token}"

        if self.enabled:
            logger.info("✅ Telegram notifications enabled")
            logger.info(f"   Motion: {self.notify_motion}, Person: {self.notify_person}, Sound: {self.notify_sound}")
            logger.info(f"   Dashboard URL: {self.dashboard_url}")
        else:
            logger.info("⚠️  Telegram notifications disabled (check TELEGRAM_ENABLED and credentials)")

    def should_notify(self, activity_type):
        """Check if we should notify for this activity type"""
        if not self.enabled:
            return False

        activity_map = {
            'MOTION': self.notify_motion,
            'MOTION_SMART': self.notify_person,  # MOTION_SMART = person detection
            'SOUND': self.notify_sound
        }

        return activity_map.get(activity_type, False)

    def extract_thumbnail_from_zip(self, thumbnail_zip_path):
        """
        Extract JPEG thumbnail from ZIP file
        Returns: bytes of JPEG image or None
        """
        try:
            if not os.path.exists(thumbnail_zip_path):
                logger.warning(f"Thumbnail ZIP not found: {thumbnail_zip_path}")
                return None

            with zipfile.ZipFile(thumbnail_zip_path, 'r') as zf:
                # Find first JPEG/JPG file in ZIP
                for filename in zf.namelist():
                    if filename.lower().endswith(('.jpg', '.jpeg')):
                        logger.info(f"📸 Extracting thumbnail: {filename}")
                        return zf.read(filename)

            logger.warning(f"No JPEG found in thumbnail ZIP: {thumbnail_zip_path}")
            return None

        except Exception as e:
            logger.error(f"Failed to extract thumbnail from ZIP: {e}")
            return None

    def format_activity_type(self, activity_type):
        """Format activity type for display"""
        type_map = {
            'MOTION': '🚶 Motion Detected',
            'MOTION_SMART': '👤 Person Detected',
            'SOUND': '🔊 Sound Detected'
        }
        return type_map.get(activity_type, f'📹 {activity_type}')

    def send_initial_notification(self, event_id, camera_id, camera_name, activity_type, timestamp):
        """
        Send initial Telegram notification with placeholder image
        This allows us to update it later with the real thumbnail using editMessageMedia
        Returns: message_id for future updates, or None if failed
        """
        if not self.should_notify(activity_type):
            logger.debug(f"Skipping notification for {activity_type}")
            return None

        try:
            # Format timestamp
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime('%H:%M:%S')  # Shorter format: just time

            # Caption with camera info
            caption = f"*{self.format_activity_type(activity_type)}*\n{camera_name or camera_id[:8]} • {time_str}"

            # Create livestream button
            livestream_url = f"{self.dashboard_url}/livestream/viewer?camera={camera_id}"
            keyboard = {
                'inline_keyboard': [[
                    {'text': '📺 View Livestream', 'url': livestream_url}
                ]]
            }

            # Send photo with placeholder
            placeholder_path = os.path.join(os.path.dirname(__file__), 'telegram_placeholder.png')
            url = f"{self.api_base_url}/sendPhoto"

            with open(placeholder_path, 'rb') as photo:
                files = {
                    'photo': ('placeholder.png', photo, 'image/png')
                }
                data = {
                    'chat_id': self.chat_id,
                    'caption': caption,
                    'parse_mode': 'Markdown',
                    'reply_markup': json.dumps(keyboard)
                }

                response = requests.post(url, files=files, data=data, timeout=10)
                result = response.json()

            if result.get('ok'):
                message_id = result['result']['message_id']
                logger.info(f"✅ Telegram initial photo notification sent for event {event_id} (message_id: {message_id})")
                return str(message_id)  # Return as string for consistency with Slack
            else:
                logger.error(f"❌ Telegram notification failed: {result}")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to send Telegram notification: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def update_notification_with_thumbnail(self, event_id, camera_id, camera_name, activity_type,
                                          timestamp, thumbnail_path, telegram_msg_id=None):
        """
        Update existing Telegram message by replacing placeholder with real thumbnail
        Uses editMessageMedia API to seamlessly update the photo in-place

        Args:
            telegram_msg_id: Required - Message ID from initial notification to update
        """
        logger.info(f"🔔 update_notification_with_thumbnail called:")
        logger.info(f"   event_id={event_id}")
        logger.info(f"   activity_type={activity_type}")
        logger.info(f"   thumbnail_path={thumbnail_path}")
        logger.info(f"   telegram_msg_id={telegram_msg_id}")

        if not self.should_notify(activity_type):
            logger.info(f"⏭️  Skipping notification for {activity_type}")
            return None

        try:
            # Extract thumbnail from ZIP
            thumbnail_bytes = None
            if thumbnail_path and os.path.exists(thumbnail_path):
                logger.info(f"📦 Attempting to extract thumbnail from: {thumbnail_path}")
                thumbnail_bytes = self.extract_thumbnail_from_zip(thumbnail_path)
                if thumbnail_bytes:
                    logger.info(f"📸 Thumbnail extracted: {len(thumbnail_bytes)} bytes")
                else:
                    logger.warning(f"⚠️  Thumbnail extraction returned None")
            else:
                logger.warning(f"⚠️  Thumbnail path invalid or doesn't exist: {thumbnail_path}")

            if not thumbnail_bytes:
                logger.warning("⚠️  No thumbnail bytes available - cannot send photo")
                return telegram_msg_id

            # Format timestamp
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')

            # Create caption with camera details
            caption = f"*{self.format_activity_type(activity_type)}*\n{camera_name or camera_id[:8]}\n{time_str}"

            # Create livestream button
            livestream_url = f"{self.dashboard_url}/livestream/viewer?camera={camera_id}"
            keyboard = {
                'inline_keyboard': [[
                    {'text': '📺 View Livestream', 'url': livestream_url}
                ]]
            }

            # Two modes: Update existing message OR send new photo message
            if telegram_msg_id:
                # Mode 1: Update existing placeholder message with real thumbnail
                logger.info(f"🔄 Updating existing Telegram message {telegram_msg_id} with real thumbnail")
                url = f"{self.api_base_url}/editMessageMedia"

                # Create media object with new photo
                media = {
                    'type': 'photo',
                    'media': 'attach://photo',
                    'caption': caption,
                    'parse_mode': 'Markdown'
                }

                files = {
                    'photo': ('thumbnail.jpg', BytesIO(thumbnail_bytes), 'image/jpeg')
                }
                data = {
                    'chat_id': self.chat_id,
                    'message_id': telegram_msg_id,
                    'media': json.dumps(media),
                    'reply_markup': json.dumps(keyboard)
                }

                response = requests.post(url, files=files, data=data, timeout=30)
                result = response.json()

                if result.get('ok'):
                    logger.info(f"✅ Telegram message updated with real thumbnail for event {event_id}")
                    return telegram_msg_id  # Return same message_id since we updated it
                else:
                    logger.error(f"❌ Telegram photo update failed: {result}")
                    return None

            else:
                # Mode 2: Send new photo message directly (thumbnail arrived within 2 seconds)
                logger.info(f"📸 Sending new photo message directly (thumbnail arrived quickly!)")
                url = f"{self.api_base_url}/sendPhoto"

                files = {
                    'photo': ('thumbnail.jpg', BytesIO(thumbnail_bytes), 'image/jpeg')
                }
                data = {
                    'chat_id': self.chat_id,
                    'caption': caption,
                    'parse_mode': 'Markdown',
                    'reply_markup': json.dumps(keyboard)
                }

                response = requests.post(url, files=files, data=data, timeout=30)
                result = response.json()

                if result.get('ok'):
                    new_message_id = result['result']['message_id']
                    logger.info(f"✅ Telegram photo sent directly for event {event_id} (message_id: {new_message_id})")
                    return str(new_message_id)
                else:
                    logger.error(f"❌ Telegram photo send failed: {result}")
                    return None

        except Exception as e:
            logger.error(f"❌ Failed to send Telegram photo notification: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def send_connection_notification(self, camera_id, camera_name, status, timestamp):
        """
        Send notification when camera connects or disconnects

        Args:
            camera_id: Camera ID
            camera_name: Human-readable camera name
            status: 'connected' or 'disconnected'
            timestamp: Unix timestamp of event
        """
        if not self.enabled:
            logger.debug(f"Telegram disabled, skipping connection notification")
            return None

        try:
            # Format timestamp
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')

            # Choose emoji and message based on status
            if status.lower() == 'connected':
                emoji = '✅'
                status_text = 'Online'
                message = f"{emoji} *Camera Online*\n{camera_name or camera_id[:8]}\n{time_str}"
            else:
                emoji = '🔴'
                status_text = 'Offline'
                message = f"{emoji} *Camera Offline*\n{camera_name or camera_id[:8]}\n{time_str}"

            # Create livestream button (only for online status)
            keyboard = None
            if status.lower() == 'connected':
                livestream_url = f"{self.dashboard_url}/livestream/viewer?camera={camera_id}"
                keyboard = {
                    'inline_keyboard': [[
                        {'text': '📺 View Livestream', 'url': livestream_url}
                    ]]
                }

            # Send text message
            url = f"{self.api_base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            if keyboard:
                data['reply_markup'] = json.dumps(keyboard)

            response = requests.post(url, data=data, timeout=10)
            result = response.json()

            if result.get('ok'):
                logger.info(f"✅ Telegram connection notification sent: {camera_name} - {status_text}")
                return str(result['result']['message_id'])
            else:
                logger.error(f"❌ Telegram connection notification failed: {result}")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to send Telegram connection notification: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def send_activity_end_notification(self, event_id, camera_id, camera_name, activity_type,
                                       start_timestamp, end_timestamp, duration_seconds):
        """
        Send notification when activity ends with final duration
        DISABLED: User doesn't want Activity Ended messages
        """
        # Activity end notifications disabled per user request
        return None


# Global instance
_telegram_notifier = None

def get_telegram_notifier():
    """Get or create the global TelegramNotifier instance"""
    global _telegram_notifier
    if _telegram_notifier is None:
        _telegram_notifier = TelegramNotifier()
    return _telegram_notifier


if __name__ == "__main__":
    # Test the Telegram notifier
    import time

    notifier = get_telegram_notifier()

    if notifier.enabled:
        print("🧪 Testing Telegram notifications...")

        # Test initial notification
        test_event_id = "test-12345678-1234-1234-1234-123456789012"
        test_camera_id = "TEST_CAMERA_ID"
        test_camera_name = "Test Camera"
        test_timestamp = int(time.time())

        message_id = notifier.send_initial_notification(
            event_id=test_event_id,
            camera_id=test_camera_id,
            camera_name=test_camera_name,
            activity_type='MOTION_SMART',
            timestamp=test_timestamp
        )

        if message_id:
            print(f"✅ Test notification sent successfully: message_id={message_id}")
        else:
            print("❌ Test notification failed")
    else:
        print("⚠️  Telegram notifications are disabled. Set TELEGRAM_ENABLED=true and configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
