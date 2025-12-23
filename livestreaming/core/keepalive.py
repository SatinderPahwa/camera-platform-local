import asyncio
import logging
import json
import ssl
from datetime import datetime
from typing import Optional, Callable
import paho.mqtt.client as mqtt

from ..config.settings import (
    EMQX_BROKER_HOST,
    EMQX_BROKER_PORT,
    EMQX_CLIENT_ID,
    EMQX_CA_CERT,
    EMQX_CLIENT_CERT,
    EMQX_CLIENT_KEY,
    MQTT_KEEPALIVE_TOPIC
)

logger = logging.getLogger(__name__)


class KeepaliveError(Exception):
    """Base exception for keepalive-related errors"""
    pass


class KeepaliveSender:
    """
    Sends periodic keepalive messages to cameras via local EMQX MQTT.

    Prevents cameras from timing out during livestreaming by sending
    regular heartbeat messages to the keepalive topic.
    """

    def __init__(
        self,
        camera_id: str,
        stream_id: str,
        interval: int = 4,
        on_error: Optional[Callable] = None
    ):
        """
        Initialize keepalive sender.

        Args:
            camera_id: Camera ID to send keepalives to
            stream_id: Current stream session ID
            interval: Interval between keepalives in seconds (default: 4)
            on_error: Optional callback for error handling
        """
        self.camera_id = camera_id
        self.stream_id = stream_id
        self.interval = interval
        self.on_error = on_error

        # Initialize MQTT client
        self.mqtt_client = None
        self._init_mqtt_client()

        # State
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.keepalive_count = 0
        self.error_count = 0
        self.last_success: Optional[datetime] = None
        self.last_error: Optional[str] = None

        # Topic
        self.topic = MQTT_KEEPALIVE_TOPIC.format(camera_id=camera_id)

        logger.info(f"Keepalive sender initialized for camera {camera_id[:8]}...")

    def _init_mqtt_client(self):
        """Initialize and connect MQTT client"""
        try:
            # Create client with unique ID
            client_id = f"{EMQX_CLIENT_ID}_keepalive_{self.camera_id[:8]}"
            self.mqtt_client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

            # Configure TLS
            self.mqtt_client.tls_set(
                ca_certs=EMQX_CA_CERT,
                certfile=EMQX_CLIENT_CERT,
                keyfile=EMQX_CLIENT_KEY,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2,
                ciphers=None
            )

            # Disable host verification for local setup if needed
            self.mqtt_client.tls_insecure_set(True)

            # Connect callback
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    logger.info("Keepalive MQTT connected")
                else:
                    logger.error(f"Keepalive MQTT connection failed: {rc}")

            self.mqtt_client.on_connect = on_connect

            # Connect
            self.mqtt_client.connect(EMQX_BROKER_HOST, EMQX_BROKER_PORT, 60)
            self.mqtt_client.loop_start()

        except Exception as e:
            logger.error(f"Failed to initialize MQTT client: {e}")
            self.mqtt_client = None
            raise KeepaliveError(f"MQTT init failed: {e}")

    async def start(self) -> None:
        """Start sending keepalive messages"""
        if self.running:
            logger.warning("Keepalive sender already running")
            return

        if not self.mqtt_client:
            self._init_mqtt_client()

        logger.info(f"Starting keepalive sender (interval: {self.interval}s)")
        self.running = True
        self.task = asyncio.create_task(self._keepalive_loop())

    async def stop(self) -> None:
        """Stop sending keepalive messages"""
        if not self.running:
            return

        logger.info("Stopping keepalive sender")
        self.running = False

        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        # Cleanup MQTT
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.mqtt_client = None

        logger.info(f"Keepalive sender stopped (sent {self.keepalive_count} keepalives)")

    async def _keepalive_loop(self) -> None:
        """Background loop that sends keepalives"""
        try:
            while self.running:
                await self._send_keepalive()
                await asyncio.sleep(self.interval)

        except asyncio.CancelledError:
            logger.debug("Keepalive loop cancelled")
        except Exception as e:
            logger.error(f"Keepalive loop error: {e}")
            self.running = False
            if self.on_error:
                try:
                    if asyncio.iscoroutinefunction(self.on_error):
                        await self.on_error(e)
                    else:
                        self.on_error(e)
                except Exception as callback_error:
                    logger.error(f"Error in keepalive error callback: {callback_error}")

    async def _send_keepalive(self) -> None:
        """Send a single keepalive message"""
        try:
            message = self._build_keepalive_message()

            # Send via MQTT (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._publish_keepalive,
                message
            )

            self.keepalive_count += 1
            self.last_success = datetime.now()
            self.last_error = None

            # Log periodically (every 4 keepalives = ~1 minute at 15s interval)
            if self.keepalive_count % 4 == 0:
                elapsed = self.keepalive_count * self.interval
                logger.info(f"💓 Keepalive: {self.keepalive_count} sent ({elapsed}s elapsed)")

        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            logger.error(f"Failed to send keepalive: {e}")

            # Stop if too many consecutive errors
            if self.error_count >= 5:
                logger.error("Too many keepalive errors, stopping sender")
                self.running = False

    def _build_keepalive_message(self) -> dict:
        """
        Build keepalive message payload.

        Returns:
            Keepalive message dictionary
        """
        import uuid

        return {
            "requestId": str(uuid.uuid4()),
            "creationTimestamp": datetime.utcnow().isoformat() + "Z",
            "sourceId": self.camera_id,
            "sourceType": "hive-cam",
            "streamId": self.stream_id,
            "keepaliveCount": self.keepalive_count,
            "messageType": "keepalive"
        }

    def _publish_keepalive(self, message: dict) -> None:
        """
        Publish keepalive to MQTT (blocking).

        Args:
            message: Message to publish

        Raises:
            Exception if publish fails
        """
        try:
            info = self.mqtt_client.publish(
                self.topic,
                json.dumps(message),
                qos=1
            )
            
            # Wait for publish to complete
            info.wait_for_publish(timeout=2.0)
            
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise KeepaliveError(f"Publish failed with code {info.rc}")

            logger.debug(f"Keepalive sent: #{self.keepalive_count}")

        except Exception as e:
            logger.error(f"Keepalive publish error: {e}")
            raise

    # ========================================================================
    # Status and monitoring
    # ========================================================================

    def is_running(self) -> bool:
        """Check if keepalive sender is running"""
        return self.running

    def get_stats(self) -> dict:
        """
        Get keepalive statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "running": self.running,
            "camera_id": self.camera_id,
            "stream_id": self.stream_id,
            "interval": self.interval,
            "keepalive_count": self.keepalive_count,
            "error_count": self.error_count,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "elapsed_seconds": self.keepalive_count * self.interval,
        }

    def reset_error_count(self) -> None:
        """Reset error counter (useful for recovery)"""
        self.error_count = 0
        logger.debug("Keepalive error count reset")


# ============================================================================
# Helper context manager
# ============================================================================

class KeepaliveSenderContext:
    """
    Context manager for automatic keepalive lifecycle.

    Usage:
        async with KeepaliveSenderContext(camera_id, stream_id) as sender:
            # Keepalives sent automatically
            await do_streaming()
        # Automatically stopped on exit
    """

    def __init__(
        self,
        camera_id: str,
        stream_id: str,
        interval: int = 4
    ):
        self.sender = KeepaliveSender(
            camera_id=camera_id,
            stream_id=stream_id,
            interval=interval
        )

    async def __aenter__(self) -> KeepaliveSender:
        await self.sender.start()
        return self.sender

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.sender.stop()
        return False


# ============================================================================
# Utility functions
# ============================================================================

async def send_single_keepalive(
    camera_id: str,
    stream_id: str
) -> bool:
    """
    Send a single keepalive message (one-off).

    Useful for testing or manual keepalive sending.

    Args:
        camera_id: Camera ID
        stream_id: Stream ID

    Returns:
        True if successful, False otherwise
    """
    sender = KeepaliveSender(camera_id, stream_id)

    try:
        await sender._send_keepalive()
        # Cleanup
        if sender.mqtt_client:
            sender.mqtt_client.loop_stop()
            sender.mqtt_client.disconnect()
        return True
    except Exception as e:
        logger.error(f"Single keepalive failed: {e}")
        if sender.mqtt_client:
            sender.mqtt_client.loop_stop()
            sender.mqtt_client.disconnect()
        return False
