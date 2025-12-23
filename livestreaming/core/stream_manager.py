import asyncio
import logging
import json
import uuid
import ssl
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from enum import Enum
import paho.mqtt.client as mqtt

from .kurento_client import KurentoClient, KurentoError
from .sdp_processor import SDPProcessor, SDPMediaInfo
from .keepalive import KeepaliveSender
from ..config.settings import (
    EMQX_BROKER_HOST,
    EMQX_BROKER_PORT,
    EMQX_CLIENT_ID,
    EMQX_CA_CERT,
    EMQX_CLIENT_CERT,
    EMQX_CLIENT_KEY,
    MQTT_STREAM_PLAY_TOPIC,
    MQTT_STREAM_STOP_TOPIC
)

logger = logging.getLogger(__name__)


class StreamState(Enum):
    """Stream session states"""
    IDLE = "idle"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    ERROR = "error"
    STOPPED = "stopped"


class StreamManagerError(Exception):
    """Base exception for stream manager errors"""
    pass


class StreamManager:
    """
    Manages a single camera streaming session.

    Responsibilities:
    - Create and manage Kurento pipeline and endpoints
    - Generate and send SDP offer to camera
    - Process camera's SDP answer
    - Start keepalive messages
    - Handle errors and cleanup
    - Track session state and statistics
    """

    def __init__(
        self,
        camera_id: str,
        kurento_client: KurentoClient,
        external_ip: str,
        max_bandwidth: int = 5000,
        min_bandwidth: int = 500,
        keepalive_interval: int = 4,
        on_state_change: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Initialize stream manager.

        Args:
            camera_id: Camera ID to stream from
            kurento_client: Connected Kurento client instance
            external_ip: External IP address for camera connectivity
            max_bandwidth: Maximum video bandwidth in Kbps (for REMB)
            min_bandwidth: Minimum video bandwidth in Kbps
            keepalive_interval: Keepalive interval in seconds
            on_state_change: Optional callback for state changes
            on_error: Optional callback for errors
        """
        self.camera_id = camera_id
        self.kurento_client = kurento_client
        self.external_ip = external_ip
        self.max_bandwidth = max_bandwidth
        self.min_bandwidth = min_bandwidth
        self.keepalive_interval = keepalive_interval
        self.on_state_change = on_state_change
        self.on_error = on_error

        # Stream identification
        self.stream_id = str(uuid.uuid4())
        self.session_id = f"stream-{camera_id[:8]}-{self.stream_id[:8]}"

        # State
        self.state = StreamState.IDLE
        self.started_at: Optional[datetime] = None
        self.stopped_at: Optional[datetime] = None
        self.error_message: Optional[str] = None

        # Kurento resources
        self.pipeline_id: Optional[str] = None
        self.rtp_endpoint_id: Optional[str] = None
        self.webrtc_endpoint_id: Optional[str] = None

        # SDP information
        self.sdp_processor = SDPProcessor(external_ip)
        self.media_info: Optional[SDPMediaInfo] = None
        self.sdp_offer: Optional[str] = None
        self.sdp_answer: Optional[str] = None

        # Keepalive
        self.keepalive_sender: Optional[KeepaliveSender] = None

        # Initialize MQTT client
        self.mqtt_client = None
        self._init_mqtt_client()

        # Statistics
        self.stats = {
            "start_attempts": 0,
            "stop_attempts": 0,
            "errors": 0,
            "last_error": None
        }

        logger.info(f"Stream manager initialized for camera {camera_id[:8]}... (session: {self.session_id})")

    def _init_mqtt_client(self):
        """Initialize and connect MQTT client"""
        try:
            # Create client with unique ID
            client_id = f"{EMQX_CLIENT_ID}_stream_{self.session_id}"
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
            self.mqtt_client.tls_insecure_set(True)

            # Connect callback
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    logger.info(f"Stream manager MQTT connected (rc={rc})")
                else:
                    logger.error(f"Stream manager MQTT connection failed: {rc}")

            self.mqtt_client.on_connect = on_connect

            # Connect
            logger.info(f"Connecting to EMQX at {EMQX_BROKER_HOST}:{EMQX_BROKER_PORT}...")
            self.mqtt_client.connect(EMQX_BROKER_HOST, EMQX_BROKER_PORT, 60)
            self.mqtt_client.loop_start()

        except Exception as e:
            logger.error(f"Failed to initialize MQTT client: {e}")
            self.mqtt_client = None

    async def start_stream(self) -> Dict[str, Any]:
        """
        Start camera streaming session.

        This orchestrates the complete stream setup:
        1. Create Kurento pipeline and endpoints
        2. Generate SDP offer
        3. Send offer to camera via MQTT
        4. Configure bandwidth (triggers REMB)
        5. Start keepalive messages

        Returns:
            Dictionary with stream information

        Raises:
            StreamManagerError: If stream start fails
        """
        if self.state != StreamState.IDLE:
            raise StreamManagerError(f"Cannot start stream in state: {self.state.value}")

        logger.info(f"Starting stream for camera {self.camera_id[:8]}...")
        self.stats["start_attempts"] += 1
        await self._set_state(StreamState.STARTING)

        try:
            # Step 1: Create Kurento pipeline
            logger.info("Creating Kurento MediaPipeline...")
            self.pipeline_id = await self.kurento_client.create_media_pipeline()

            # Step 2: Create RtpEndpoint (receives plain RTP from camera - like POC2!)
            logger.info("Creating RtpEndpoint for camera stream...")
            self.rtp_endpoint_id = await self.kurento_client.create_rtp_endpoint(
                self.pipeline_id
            )
            logger.info(f"✅ Created RtpEndpoint: {self.rtp_endpoint_id}")

            # Step 3: Generate minimal SDP offer with port 9 for dynamic allocation
            logger.info("Generating minimal SDP offer...")
            minimal_offer, self.media_info = self.sdp_processor.build_custom_sdp_offer()

            # Step 4: Process offer with RtpEndpoint to get SDP answer with Kurento's actual ports
            logger.info("Processing SDP offer with RtpEndpoint to get actual ports...")
            sdp_answer = await self.kurento_client.process_sdp_offer(
                self.rtp_endpoint_id,
                minimal_offer
            )

            # Step 5: CRITICAL - Set maxVideoRecvBandwidth on RtpEndpoint (triggers REMB to camera!)
            logger.info(f"Setting maxVideoRecvBandwidth on RtpEndpoint: {self.max_bandwidth} Kbps...")
            await self.kurento_client.set_max_video_recv_bandwidth(
                self.rtp_endpoint_id,
                self.max_bandwidth
            )
            await self.kurento_client.set_min_video_recv_bandwidth(
                self.rtp_endpoint_id,
                self.min_bandwidth
            )
            logger.info(f"✅ Bandwidth configured - KMS will send REMB packets to camera")

            # Step 6: Enhance the SDP answer with external IP and Hive-specific attributes
            logger.info("Enhancing SDP answer with external IP and x-skl attributes...")
            self.sdp_offer = self.sdp_processor.enhance_answer(
                sdp_answer,
                self.external_ip,
                self.media_info
            )

            # Step 7: Send enhanced SDP answer to camera via MQTT
            logger.info("Sending enhanced SDP answer to camera via MQTT...")
            await self._send_play_command_to_camera()

            # Step 8: Start keepalive sender
            logger.info(f"Starting keepalive sender (interval: {self.keepalive_interval}s)...")
            self.keepalive_sender = KeepaliveSender(
                camera_id=self.camera_id,
                stream_id=self.stream_id,
                interval=self.keepalive_interval,
                on_error=self._handle_keepalive_error
            )
            await self.keepalive_sender.start()

            # Success!
            self.started_at = datetime.now()
            await self._set_state(StreamState.ACTIVE)

            logger.info(f"✅ Stream started successfully for camera {self.camera_id[:8]}...")

            return {
                "session_id": self.session_id,
                "stream_id": self.stream_id,
                "camera_id": self.camera_id,
                "state": self.state.value,
                "pipeline_id": self.pipeline_id,
                "rtp_endpoint_id": self.rtp_endpoint_id,
                "started_at": self.started_at.isoformat(),
            }

        except Exception as e:
            error_msg = f"Failed to start stream: {e}"
            logger.error(error_msg)
            self.error_message = error_msg
            self.stats["errors"] += 1
            self.stats["last_error"] = error_msg
            await self._set_state(StreamState.ERROR)

            # Cleanup on error
            await self._cleanup_resources()

            if self.on_error:
                try:
                    if asyncio.iscoroutinefunction(self.on_error):
                        await self.on_error(e)
                    else:
                        self.on_error(e)
                except Exception as callback_error:
                    logger.error(f"Error in error callback: {callback_error}")

            raise StreamManagerError(error_msg) from e

    async def stop_stream(self) -> Dict[str, Any]:
        """
        Stop camera streaming session.

        This cleanly shuts down the stream:
        1. Stop keepalive messages
        2. Send stop command to camera
        3. Release Kurento resources
        4. Update state
        5. Stop MQTT client

        Returns:
            Dictionary with final statistics
        """
        if self.state not in [StreamState.ACTIVE, StreamState.ERROR]:
            logger.warning(f"Attempting to stop stream in state: {self.state.value}")

        logger.info(f"Stopping stream for camera {self.camera_id[:8]}...")
        self.stats["stop_attempts"] += 1
        await self._set_state(StreamState.STOPPING)

        try:
            # Stop keepalive sender FIRST
            if self.keepalive_sender and self.keepalive_sender.is_running():
                logger.info("Stopping keepalive sender...")
                await self.keepalive_sender.stop()
                await asyncio.sleep(0.5)
                logger.info("✅ Keepalive sender stopped")

            # Send stop command to camera
            logger.info("Sending stop command to camera...")
            await self._send_stop_command_to_camera()

            # Cleanup Kurento resources
            await self._cleanup_resources()
            
            # Cleanup MQTT client
            if self.mqtt_client:
                logger.info("Disconnecting stream manager MQTT client...")
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
                self.mqtt_client = None

            # Update state
            self.stopped_at = datetime.now()
            await self._set_state(StreamState.STOPPED)

            # Calculate statistics
            duration = None
            if self.started_at and self.stopped_at:
                duration = (self.stopped_at - self.started_at).total_seconds()

            keepalive_stats = self.keepalive_sender.get_stats() if self.keepalive_sender else {}

            logger.info(f"✅ Stream stopped for camera {self.camera_id[:8]}... (duration: {duration}s)")

            return {
                "session_id": self.session_id,
                "stream_id": self.stream_id,
                "camera_id": self.camera_id,
                "state": self.state.value,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
                "duration_seconds": duration,
                "keepalive_stats": keepalive_stats,
                "stats": self.stats,
            }

        except Exception as e:
            error_msg = f"Error during stream stop: {e}"
            logger.error(error_msg)
            self.error_message = error_msg
            await self._set_state(StreamState.ERROR)
            raise StreamManagerError(error_msg) from e

    # ========================================================================
    # Camera communication (EMQX MQTT)
    # ========================================================================

    async def _send_play_command_to_camera(self) -> None:
        """
        Send play command with SDP offer to camera via MQTT.

        Raises:
            StreamManagerError: If MQTT publish fails
        """
        if not self.mqtt_client:
            raise StreamManagerError("MQTT client not available")

        topic = MQTT_STREAM_PLAY_TOPIC.format(camera_id=self.camera_id)

        # NOTE: Do NOT pre-escape SDP! json.dumps() will handle the escaping.
        message = {
            "requestId": str(uuid.uuid4()),
            "creationTimestamp": datetime.utcnow().isoformat() + "Z",
            "sourceId": self.camera_id,
            "sourceType": "hive-cam",
            "streamId": self.stream_id,
            "sdpOffer": self.sdp_offer,
            "messageType": "play"
        }

        try:
            # Run blocking MQTT call in executor
            loop = asyncio.get_event_loop()
            
            def publish():
                info = self.mqtt_client.publish(
                    topic,
                    json.dumps(message),
                    qos=1
                )
                info.wait_for_publish(timeout=2.0)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise Exception(f"Publish failed: {info.rc}")

            await loop.run_in_executor(None, publish)
            logger.info(f"Sent play command to camera via MQTT: {topic}")

        except Exception as e:
            error_msg = f"MQTT publish error: {e}"
            logger.error(error_msg)
            raise StreamManagerError(error_msg) from e

    async def _send_stop_command_to_camera(self) -> None:
        """
        Send stop command to camera via MQTT.

        Raises:
            StreamManagerError: If MQTT publish fails
        """
        if not self.mqtt_client:
            logger.warning("MQTT client not available, skipping stop command")
            return

        topic = MQTT_STREAM_STOP_TOPIC.format(camera_id=self.camera_id)

        message = {
            "requestId": str(uuid.uuid4()),
            "creationTimestamp": datetime.utcnow().isoformat() + "Z",
            "sourceId": self.camera_id,
            "sourceType": "hive-cam",
            "streamId": self.stream_id,
            "messageType": "stop"
        }

        try:
            # Run blocking MQTT call in executor
            loop = asyncio.get_event_loop()
            
            def publish():
                info = self.mqtt_client.publish(
                    topic,
                    json.dumps(message),
                    qos=1
                )
                info.wait_for_publish(timeout=2.0)

            await loop.run_in_executor(None, publish)
            logger.info(f"Sent stop command to camera via MQTT: {topic}")

        except Exception as e:
            logger.error(f"MQTT publish error during stop: {e}")
            # Don't raise, this is cleanup

    # ========================================================================
    # Resource management
    # ========================================================================

    async def _cleanup_resources(self) -> None:
        """Cleanup all Kurento resources"""
        logger.info("Cleaning up Kurento resources...")

        # Release pipeline (also releases all endpoints)
        if self.pipeline_id:
            try:
                await self.kurento_client.release_pipeline(self.pipeline_id)
                logger.info(f"Released pipeline: {self.pipeline_id}")
            except Exception as e:
                logger.warning(f"Failed to release pipeline: {e}")

        # Clear resource IDs
        self.pipeline_id = None
        self.rtp_endpoint_id = None
        self.webrtc_endpoint_id = None

    # ========================================================================
    # State management
    # ========================================================================

    async def _set_state(self, new_state: StreamState) -> None:
        """
        Set stream state and trigger callback.

        Args:
            new_state: New state
        """
        old_state = self.state
        self.state = new_state

        logger.debug(f"State transition: {old_state.value} → {new_state.value}")

        if self.on_state_change:
            try:
                if asyncio.iscoroutinefunction(self.on_state_change):
                    await self.on_state_change(old_state, new_state)
                else:
                    self.on_state_change(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    # ========================================================================
    # Error handling
    # ========================================================================

    async def _handle_keepalive_error(self, error: Exception) -> None:
        """
        Handle keepalive sender errors.

        Args:
            error: Error from keepalive sender
        """
        error_msg = f"Keepalive error: {error}"
        logger.error(error_msg)
        self.error_message = error_msg
        self.stats["errors"] += 1
        self.stats["last_error"] = error_msg
        await self._set_state(StreamState.ERROR)

        # Stop stream on keepalive failure
        try:
            await self.stop_stream()
        except Exception as e:
            logger.error(f"Error stopping stream after keepalive failure: {e}")

    # ========================================================================
    # Status and monitoring
    # ========================================================================

    def get_state(self) -> StreamState:
        """Get current stream state"""
        return self.state

    def is_active(self) -> bool:
        """Check if stream is active"""
        return self.state == StreamState.ACTIVE

    def get_session_id(self) -> str:
        """Get session ID"""
        return self.session_id

    def get_stream_id(self) -> str:
        """Get stream ID"""
        return self.stream_id

    def get_webrtc_endpoint_id(self) -> Optional[str]:
        """Get WebRTC endpoint ID for viewer connections"""
        return self.webrtc_endpoint_id

    def get_pipeline_id(self) -> Optional[str]:
        """Get Kurento pipeline ID"""
        return self.pipeline_id

    def get_rtp_endpoint_id(self) -> Optional[str]:
        """Get RTP endpoint ID for viewer connections"""
        return self.rtp_endpoint_id

    def get_stats(self) -> Dict[str, Any]:
        """
        Get detailed stream statistics.

        Returns:
            Dictionary with stream stats
        """
        duration = None
        if self.started_at:
            end_time = self.stopped_at or datetime.now()
            duration = (end_time - self.started_at).total_seconds()

        keepalive_stats = {}
        if self.keepalive_sender:
            keepalive_stats = self.keepalive_sender.get_stats()

        return {
            "session_id": self.session_id,
            "stream_id": self.stream_id,
            "camera_id": self.camera_id,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "duration_seconds": duration,
            "error_message": self.error_message,
            "pipeline_id": self.pipeline_id,
            "rtp_endpoint_id": self.rtp_endpoint_id,
            "webrtc_endpoint_id": self.webrtc_endpoint_id,
            "keepalive_stats": keepalive_stats,
            "manager_stats": self.stats,
        }


# ============================================================================
# Helper context manager
# ============================================================================

class StreamManagerContext:
    """
    Context manager for automatic stream lifecycle.

    Usage:
        async with StreamManagerContext(camera_id, kurento_client, external_ip) as manager:
            # Stream automatically started
            webrtc_id = manager.get_webrtc_endpoint_id()
            # ... use stream ...
        # Stream automatically stopped on exit
    """

    def __init__(
        self,
        camera_id: str,
        kurento_client: KurentoClient,
        external_ip: str,
        **kwargs
    ):
        self.manager = StreamManager(
            camera_id=camera_id,
            kurento_client=kurento_client,
            external_ip=external_ip,
            **kwargs
        )

    async def __aenter__(self) -> StreamManager:
        await self.manager.start_stream()
        return self.manager

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.manager.stop_stream()
        return False
