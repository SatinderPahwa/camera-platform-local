"""
WebSocket Signaling Server

Handles WebRTC signaling between browser viewers and Kurento Media Server.
Provides real-time bidirectional communication for:
- SDP offer/answer exchange
- ICE candidate relay
- Viewer session management

Based on WebSocket protocol for low-latency signaling.
"""

import asyncio
import logging
import json
import uuid
import os
import ssl
from typing import Dict, Set, Optional, Any
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from ..core import KurentoClient

logger = logging.getLogger(__name__)


class SignalingError(Exception):
    """Base exception for signaling errors"""
    pass


class ViewerSession:
    """
    Represents a single viewer's WebRTC session.

    Tracks viewer connection state and Kurento endpoint.
    """

    def __init__(
        self,
        viewer_id: str,
        websocket: WebSocketServerProtocol,
        camera_id: str,
        stream_id: str
    ):
        self.viewer_id = viewer_id
        self.websocket = websocket
        self.camera_id = camera_id
        self.stream_id = stream_id
        self.created_at = datetime.now()
        self.webrtc_endpoint_id: Optional[str] = None
        self.connected = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "viewer_id": self.viewer_id,
            "camera_id": self.camera_id,
            "stream_id": self.stream_id,
            "created_at": self.created_at.isoformat(),
            "webrtc_endpoint_id": self.webrtc_endpoint_id,
            "connected": self.connected,
        }


class SignalingServer:
    """
    WebSocket signaling server for WebRTC viewer connections.

    Handles WebRTC signaling protocol:
    - Viewer connects via WebSocket
    - Viewer sends SDP offer
    - Server processes offer with Kurento and returns SDP answer
    - ICE candidates are relayed bidirectionally
    - Server monitors connection state

    Protocol:
        Client → Server messages:
        - {"type": "viewer", "sdpOffer": "...", "cameraId": "...", "streamId": "..."}
        - {"type": "onIceCandidate", "candidate": {...}}
        - {"type": "stop"}

        Server → Client messages:
        - {"type": "viewerResponse", "sdpAnswer": "...", "viewerId": "..."}
        - {"type": "iceCandidate", "candidate": {...}}
        - {"type": "error", "message": "..."}

    Usage:
        server = SignalingServer(
            host="0.0.0.0",
            port=8765,
            kurento_client=kurento_client,
            get_stream_webrtc_endpoint=lambda camera_id: endpoint_id
        )
        await server.start()
    """

    def __init__(
        self,
        host: str,
        port: int,
        kurento_client: KurentoClient,
        get_stream_connection_info: callable,
        max_viewers_per_stream: int = 10
    ):
        """
        Initialize signaling server.

        Args:
            host: Server host (0.0.0.0 for all interfaces)
            port: Server port (e.g., 8765)
            kurento_client: Connected Kurento client
            get_stream_connection_info: Function returning (pipeline_id, webrtc_endpoint_id) tuple
                The WebRtcEndpoint receives raw RTP from camera, viewers connect via separate WebRtcEndpoints
            max_viewers_per_stream: Maximum viewers per camera stream
        """
        self.host = host
        self.port = port
        self.kurento_client = kurento_client
        self.get_stream_connection_info = get_stream_connection_info
        self.max_viewers_per_stream = max_viewers_per_stream

        # Viewer sessions
        self.viewers: Dict[str, ViewerSession] = {}  # viewer_id -> ViewerSession
        self.websockets: Dict[WebSocketServerProtocol, str] = {}  # websocket -> viewer_id

        # WebSocket server
        self.server = None
        self.running = False

        logger.info(f"Signaling server initialized on {host}:{port}")

    async def start(self) -> None:
        """
        Start WebSocket signaling server.

        Raises:
            SignalingError: If server fails to start
        """
        try:
            # Check for SSL certificates (optional - for WSS support with HTTPS dashboard)
            ssl_context = None
            ssl_cert = os.getenv('DASHBOARD_SSL_CERT_FILE')
            ssl_key = os.getenv('DASHBOARD_SSL_KEY_FILE')

            if ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(ssl_cert, ssl_key)
                protocol = "wss"
                logger.info(f"🔒 Signaling server SSL enabled with certificate: {ssl_cert}")
            else:
                protocol = "ws"
                logger.info(f"⚠️  Signaling server running without SSL (WS only)")

            logger.info(f"Starting signaling server on {protocol}://{self.host}:{self.port}")

            # Configure WebSocket server with permissive settings for remote access
            self.server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                ssl=ssl_context,
                ping_interval=20,
                ping_timeout=10,
                # Allow connections from any origin (needed for remote access)
                origins=None,
                # Increase max message size for large SDP offers
                max_size=10 * 1024 * 1024,  # 10 MB
                # Don't require specific subprotocol
                subprotocols=None
            )

            self.running = True
            logger.info(f"✅ Signaling server running on {protocol}://{self.host}:{self.port}")

        except Exception as e:
            error_msg = f"Failed to start signaling server: {e}"
            logger.error(error_msg)
            raise SignalingError(error_msg) from e

    async def stop(self) -> None:
        """Stop signaling server and cleanup all viewers"""
        logger.info("Stopping signaling server...")
        self.running = False

        # Close all viewer connections
        for viewer_id in list(self.viewers.keys()):
            await self._cleanup_viewer(viewer_id)

        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        logger.info("✅ Signaling server stopped")

    # ========================================================================
    # WebSocket connection handling
    # ========================================================================

    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """
        Handle WebSocket client connection.

        Args:
            websocket: WebSocket connection
            path: Request path
        """
        viewer_id = None

        try:
            logger.info(f"New WebSocket connection from {websocket.remote_address}")

            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get("type")

                    logger.debug(f"Received message: {message_type}")

                    if message_type == "viewer":
                        # New viewer requesting to watch stream
                        viewer_id = await self._handle_viewer_request(websocket, data)

                    elif message_type == "onIceCandidate":
                        # ICE candidate from viewer
                        await self._handle_ice_candidate_from_viewer(websocket, data)

                    elif message_type == "stop":
                        # Viewer stopping
                        await self._handle_stop_request(websocket)

                    else:
                        logger.warning(f"Unknown message type: {message_type}")
                        await self._send_error(websocket, f"Unknown message type: {message_type}")

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    await self._send_error(websocket, "Invalid JSON")

                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await self._send_error(websocket, str(e))

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket connection closed: {websocket.remote_address}")

        except Exception as e:
            logger.error(f"WebSocket error: {e}")

        finally:
            # Cleanup on disconnect
            if viewer_id:
                await self._cleanup_viewer(viewer_id)
            elif websocket in self.websockets:
                viewer_id = self.websockets[websocket]
                await self._cleanup_viewer(viewer_id)

    # ========================================================================
    # Message handlers
    # ========================================================================

    async def _handle_viewer_request(
        self,
        websocket: WebSocketServerProtocol,
        data: Dict[str, Any]
    ) -> str:
        """
        Handle viewer request to watch stream.

        Creates dedicated WebRtcEndpoint for viewer and connects it to camera's RTP endpoint.
        This is the production architecture matching POC2: each viewer gets their own WebRtcEndpoint
        connected to the shared RtpEndpoint receiving the camera's plain RTP stream.

        Architecture: Camera → RtpEndpoint → WebRtcEndpoint (viewer)

        Args:
            websocket: Viewer WebSocket
            data: Message data with sdpOffer, cameraId, streamId

        Returns:
            Viewer ID

        Raises:
            SignalingError: If request fails
        """
        camera_id = data.get("cameraId")
        stream_id = data.get("streamId")
        sdp_offer = data.get("sdpOffer")

        if not camera_id or not stream_id or not sdp_offer:
            raise SignalingError("Missing required fields: cameraId, streamId, sdpOffer")

        # Check viewer limit
        stream_viewers = [
            v for v in self.viewers.values()
            if v.camera_id == camera_id and v.stream_id == stream_id
        ]
        if len(stream_viewers) >= self.max_viewers_per_stream:
            raise SignalingError(
                f"Maximum viewers ({self.max_viewers_per_stream}) reached for stream"
            )

        # Get stream's pipeline and RTP endpoint info
        # The camera's RtpEndpoint receives the plain RTP stream from camera
        connection_info = self.get_stream_connection_info(camera_id)
        if not connection_info:
            raise SignalingError(f"No active stream found for camera {camera_id}")

        pipeline_id, camera_rtp_endpoint_id = connection_info

        # Generate viewer ID
        viewer_id = str(uuid.uuid4())

        logger.info(f"Processing viewer request for camera {camera_id[:8]}... (viewer: {viewer_id[:8]}...)")

        try:
            # Create dedicated WebRtcEndpoint for this viewer
            viewer_webrtc_id = await self.kurento_client.create_webrtc_endpoint(pipeline_id)
            logger.debug(f"Created WebRtcEndpoint {viewer_webrtc_id} for viewer {viewer_id[:8]}...")

            # Subscribe to ICE candidate events BEFORE gathering candidates
            # Try "OnIceCandidate" first (POC2 used this), may also be "IceCandidateFound" in newer versions
            await self.kurento_client.subscribe_to_event(viewer_webrtc_id, "OnIceCandidate")

            # Configure send bandwidth for viewer (Kurento → Browser)
            # This matches POC2 which sets setMaxVideoSendBandwidth/setMinVideoSendBandwidth
            await self.kurento_client.set_max_video_send_bandwidth(viewer_webrtc_id, 5000)  # 5 Mbps
            await self.kurento_client.set_min_video_send_bandwidth(viewer_webrtc_id, 500)   # 500 Kbps
            logger.debug(f"Configured send bandwidth for viewer WebRtcEndpoint (500-5000 Kbps)")

            # Connect camera's RtpEndpoint to viewer's WebRtcEndpoint
            # Architecture matching POC2: RtpEndpoint (camera) → WebRtcEndpoint (viewer)
            await self.kurento_client.connect_endpoints(camera_rtp_endpoint_id, viewer_webrtc_id)
            logger.debug(f"Connected camera's RTP endpoint to viewer's WebRTC endpoint")

            # Create viewer session BEFORE gathering candidates
            # (ICE events fire immediately and need to find the viewer)
            viewer = ViewerSession(
                viewer_id=viewer_id,
                websocket=websocket,
                camera_id=camera_id,
                stream_id=stream_id
            )
            viewer.webrtc_endpoint_id = viewer_webrtc_id
            viewer.connected = True

            self.viewers[viewer_id] = viewer
            self.websockets[websocket] = viewer_id

            # Process viewer's SDP offer with their WebRtcEndpoint
            sdp_answer = await self.kurento_client.process_sdp_offer(
                viewer_webrtc_id,
                sdp_offer
            )

            # Start ICE candidate gathering for viewer's endpoint
            # Candidates will be relayed via _handle_ice_candidate_from_kurento()
            await self.kurento_client.gather_candidates(viewer_webrtc_id)

            # Send response to viewer
            await self._send_message(websocket, {
                "type": "viewerResponse",
                "sdpAnswer": sdp_answer,
                "viewerId": viewer_id
            })

            logger.info(f"✅ Viewer {viewer_id[:8]}... connected to camera {camera_id[:8]}... (RtpEndpoint → WebRtcEndpoint)")

            return viewer_id

        except Exception as e:
            error_msg = f"Failed to process viewer request: {e}"
            logger.error(error_msg)
            await self._send_error(websocket, error_msg)
            raise SignalingError(error_msg) from e

    async def _handle_ice_candidate_from_viewer(
        self,
        websocket: WebSocketServerProtocol,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle ICE candidate from viewer.

        Relays candidate to Kurento endpoint.

        Args:
            websocket: Viewer WebSocket
            data: Message data with candidate
        """
        viewer_id = self.websockets.get(websocket)
        if not viewer_id:
            logger.warning("ICE candidate from unknown viewer")
            return

        viewer = self.viewers.get(viewer_id)
        if not viewer:
            logger.warning(f"ICE candidate for unknown viewer: {viewer_id}")
            return

        candidate = data.get("candidate")
        if not candidate:
            logger.warning("ICE candidate message missing candidate field")
            return

        try:
            # Add ICE candidate to Kurento endpoint
            await self.kurento_client.add_ice_candidate(
                viewer.webrtc_endpoint_id,
                candidate
            )

            logger.debug(f"Added ICE candidate for viewer {viewer_id[:8]}...")

        except Exception as e:
            logger.error(f"Failed to add ICE candidate: {e}")
            await self._send_error(websocket, f"Failed to add ICE candidate: {e}")

    async def _handle_stop_request(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle stop request from viewer.

        Args:
            websocket: Viewer WebSocket
        """
        viewer_id = self.websockets.get(websocket)
        if not viewer_id:
            logger.warning("Stop request from unknown viewer")
            return

        logger.info(f"Viewer {viewer_id[:8]}... requested stop")
        await self._cleanup_viewer(viewer_id)

    # ========================================================================
    # ICE candidate relay (Kurento → Viewer)
    # ========================================================================

    def setup_ice_candidate_relay(self) -> None:
        """
        Setup ICE candidate relay from Kurento to viewers.

        Subscribes to Kurento OnIceCandidate events and relays to viewers.
        """
        self.kurento_client.add_event_handler(self._handle_ice_candidate_from_kurento)
        logger.info("ICE candidate relay setup complete")

    async def _handle_ice_candidate_from_kurento(self, event: Dict[str, Any]) -> None:
        """
        Handle ICE candidate event from Kurento.

        Relays candidate to appropriate viewer.

        Args:
            event: Kurento event with candidate
        """
        # Kurento wraps events in "onEvent" with type nested inside
        if event.get("method") != "onEvent":
            return

        # Extract the actual event type from params.value.type
        params = event.get("params", {})
        value = params.get("value", {})
        event_type = value.get("type")

        if event_type != "OnIceCandidate":
            return

        # Extract endpoint ID and candidate from nested structure
        endpoint_id = value.get("object")
        data = value.get("data", {})
        candidate = data.get("candidate")

        if not endpoint_id or not candidate:
            logger.warning(f"ICE candidate event missing required fields: endpoint={endpoint_id}, candidate={candidate}")
            return

        # Find viewer with this endpoint
        logger.info(f"🔍 Looking for viewer with endpoint {endpoint_id[:20]}... (have {len(self.viewers)} viewers)")

        viewer_found = False
        for viewer in self.viewers.values():
            if viewer.webrtc_endpoint_id == endpoint_id:
                viewer_found = True
                try:
                    await self._send_message(viewer.websocket, {
                        "type": "iceCandidate",
                        "candidate": candidate
                    })
                    logger.info(f"✅ Relayed ICE candidate to viewer {viewer.viewer_id[:8]}...")
                except Exception as e:
                    logger.error(f"Failed to relay ICE candidate: {e}")
                break

        if not viewer_found:
            logger.warning(f"❌ No viewer found for endpoint {endpoint_id[:40]}...")

    # ========================================================================
    # Viewer cleanup
    # ========================================================================

    async def _cleanup_viewer(self, viewer_id: str) -> None:
        """
        Cleanup viewer session and resources.

        Releases the viewer's dedicated WebRtcEndpoint from Kurento.

        Args:
            viewer_id: Viewer ID to cleanup
        """
        viewer = self.viewers.pop(viewer_id, None)
        if not viewer:
            return

        logger.info(f"Cleaning up viewer {viewer_id[:8]}...")

        # Remove from websockets mapping
        if viewer.websocket in self.websockets:
            del self.websockets[viewer.websocket]

        # Release viewer's WebRtcEndpoint from Kurento
        if viewer.webrtc_endpoint_id:
            try:
                await self.kurento_client.release_endpoint(viewer.webrtc_endpoint_id)
                logger.debug(f"Released WebRtcEndpoint {viewer.webrtc_endpoint_id} for viewer {viewer_id[:8]}...")
            except Exception as e:
                logger.warning(f"Error releasing WebRTC endpoint: {e}")

        # Close WebSocket if still open
        if not viewer.websocket.closed:
            try:
                await viewer.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing websocket: {e}")

        logger.info(f"✅ Viewer {viewer_id[:8]}... cleaned up")

    # ========================================================================
    # WebSocket utilities
    # ========================================================================

    async def _send_message(
        self,
        websocket: WebSocketServerProtocol,
        message: Dict[str, Any]
    ) -> None:
        """
        Send JSON message to WebSocket.

        Args:
            websocket: WebSocket connection
            message: Message dictionary
        """
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def _send_error(
        self,
        websocket: WebSocketServerProtocol,
        error_message: str
    ) -> None:
        """
        Send error message to WebSocket.

        Args:
            websocket: WebSocket connection
            error_message: Error message
        """
        try:
            await self._send_message(websocket, {
                "type": "error",
                "message": error_message
            })
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

    # ========================================================================
    # Status and monitoring
    # ========================================================================

    def get_viewer_count(self, camera_id: Optional[str] = None) -> int:
        """
        Get number of active viewers.

        Args:
            camera_id: Optional camera ID to filter by

        Returns:
            Number of viewers
        """
        if camera_id:
            return len([v for v in self.viewers.values() if v.camera_id == camera_id])
        return len(self.viewers)

    def get_viewers(self, camera_id: Optional[str] = None) -> list:
        """
        Get list of active viewers.

        Args:
            camera_id: Optional camera ID to filter by

        Returns:
            List of viewer info dictionaries
        """
        viewers = self.viewers.values()
        if camera_id:
            viewers = [v for v in viewers if v.camera_id == camera_id]

        return [v.to_dict() for v in viewers]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get server statistics.

        Returns:
            Dictionary with server stats
        """
        return {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "total_viewers": len(self.viewers),
            "viewers_by_camera": {
                camera_id: len([v for v in self.viewers.values() if v.camera_id == camera_id])
                for camera_id in set(v.camera_id for v in self.viewers.values())
            },
        }
