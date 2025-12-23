"""
Livestreaming API Server

REST API for controlling camera streams from dashboard.
Provides endpoints for starting/stopping streams and monitoring status.

Integrates with:
- StreamManager: Controls camera streams
- KurentoClient: Media server communication
- SignalingServer: Viewer connections

Built with aiohttp for async operation.
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from pathlib import Path
from aiohttp import web
import aiohttp_cors

from ..core import (
    KurentoClient,
    StreamManager,
    StreamState,
    KurentoError
)
from .signaling_server import SignalingServer
from ..config.settings import KEEPALIVE_INTERVAL

logger = logging.getLogger(__name__)


class APIServer:
    """
    REST API server for livestreaming control.

    Endpoints:
        GET  /health                    - Health check
        GET  /streams                   - List active streams
        GET  /streams/{camera_id}       - Get stream info
        POST /streams/{camera_id}/start - Start stream
        POST /streams/{camera_id}/stop  - Stop stream
        GET  /viewers                   - List all viewers
        GET  /viewers/{camera_id}       - List viewers for camera

    Usage:
        api_server = APIServer(
            host="0.0.0.0",
            port=8080,
            kurento_client=kurento_client,
            external_ip="86.20.156.73"
        )
        await api_server.start()
    """

    def __init__(
        self,
        host: str,
        port: int,
        kurento_client: KurentoClient,
        external_ip: str,
        local_ip: str,
        local_network_prefix: str = "192.168.199",
        signaling_server: Optional[SignalingServer] = None,
        max_bandwidth: int = 5000,
        min_bandwidth: int = 500,
    ):
        """
        Initialize API server.

        Args:
            host: Server host
            port: Server port
            kurento_client: Connected Kurento client
            external_ip: External IP for remote camera connectivity
            local_ip: Local network IP for local camera connectivity
            local_network_prefix: Network prefix to detect local viewers (e.g., "192.168.199")
            signaling_server: Optional signaling server for viewer info
            max_bandwidth: Max video bandwidth in Kbps
            min_bandwidth: Min video bandwidth in Kbps
        """
        self.host = host
        self.port = port
        self.kurento_client = kurento_client
        self.external_ip = external_ip
        self.local_ip = local_ip
        self.local_network_prefix = local_network_prefix
        self.signaling_server = signaling_server
        self.max_bandwidth = max_bandwidth
        self.min_bandwidth = min_bandwidth

        # Active stream managers
        self.streams: Dict[str, StreamManager] = {}  # camera_id -> StreamManager

        # Web app
        self.app = web.Application()
        self.runner = None
        self.site = None

        # Setup routes
        self._setup_routes()

        logger.info(f"API server initialized on {host}:{port}")

    def _setup_routes(self) -> None:
        """Setup API routes"""
        # API endpoints
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/streams', self.list_streams)
        self.app.router.add_get('/streams/{camera_id}', self.get_stream)
        self.app.router.add_post('/streams/{camera_id}/start', self.start_stream)
        self.app.router.add_post('/streams/{camera_id}/stop', self.stop_stream)
        self.app.router.add_get('/viewers', self.list_all_viewers)
        self.app.router.add_get('/viewers/{camera_id}', self.list_camera_viewers)

        # Viewer UI endpoints (static files)
        self.app.router.add_get('/viewer', self.serve_viewer_html)
        self.app.router.add_get('/viewer.html', self.serve_viewer_html)
        self.app.router.add_get('/viewer.js', self.serve_viewer_js)

        # Setup CORS for dashboard access
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })

        # Add CORS to all routes
        for route in list(self.app.router.routes()):
            cors.add(route)

    async def start(self) -> None:
        """Start API server"""
        try:
            logger.info(f"Starting API server on http://{self.host}:{self.port}")

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

            logger.info(f"✅ API server running on http://{self.host}:{self.port}")

        except Exception as e:
            error_msg = f"Failed to start API server: {e}"
            logger.error(error_msg)
            raise

    async def stop(self) -> None:
        """Stop API server and cleanup"""
        logger.info("Stopping API server...")

        # Stop all active streams
        for camera_id in list(self.streams.keys()):
            try:
                await self._stop_stream_internal(camera_id)
            except Exception as e:
                logger.error(f"Error stopping stream {camera_id}: {e}")

        # Stop server
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        logger.info("✅ API server stopped")

    # ========================================================================
    # API endpoints
    # ========================================================================

    async def health_check(self, request: web.Request) -> web.Response:
        """
        Health check endpoint.

        Returns server status and Kurento connectivity.
        """
        kurento_connected = self.kurento_client.is_connected()

        health = {
            "status": "healthy" if kurento_connected else "degraded",
            "timestamp": datetime.now().isoformat(),
            "kurento_connected": kurento_connected,
            "active_streams": len(self.streams),
            "total_viewers": self.signaling_server.get_viewer_count() if self.signaling_server else 0,
        }

        return web.json_response(health)

    async def list_streams(self, request: web.Request) -> web.Response:
        """
        List all active streams.

        Returns array of stream information.
        """
        streams_info = []

        for camera_id, stream_manager in self.streams.items():
            stats = stream_manager.get_stats()
            viewer_count = 0

            if self.signaling_server:
                viewer_count = self.signaling_server.get_viewer_count(camera_id)

            streams_info.append({
                "camera_id": camera_id,
                "session_id": stats["session_id"],
                "stream_id": stats["stream_id"],
                "state": stats["state"],
                "started_at": stats["started_at"],
                "duration_seconds": stats["duration_seconds"],
                "viewer_count": viewer_count,
                "webrtc_endpoint_id": stats["webrtc_endpoint_id"],
            })

        return web.json_response({
            "streams": streams_info,
            "count": len(streams_info)
        })

    async def get_stream(self, request: web.Request) -> web.Response:
        """
        Get detailed stream information.

        Path params:
            camera_id: Camera ID
        """
        camera_id = request.match_info['camera_id']

        stream_manager = self.streams.get(camera_id)
        if not stream_manager:
            return web.json_response(
                {"error": f"No active stream for camera {camera_id}"},
                status=404
            )

        stats = stream_manager.get_stats()

        # Add viewer information
        viewers = []
        if self.signaling_server:
            viewers = self.signaling_server.get_viewers(camera_id)

        return web.json_response({
            "stream": stats,
            "viewers": viewers,
            "viewer_count": len(viewers)
        })

    async def start_stream(self, request: web.Request) -> web.Response:
        """
        Start camera stream.

        Path params:
            camera_id: Camera ID

        Request body (optional):
            {
                "max_bandwidth": 5000,
                "min_bandwidth": 500
            }
        """
        camera_id = request.match_info['camera_id']

        # Check if stream already active
        if camera_id in self.streams:
            existing = self.streams[camera_id]
            if existing.is_active():
                return web.json_response(
                    {
                        "error": f"Stream already active for camera {camera_id}",
                        "session_id": existing.get_session_id()
                    },
                    status=409
                )
            else:
                # Clean up old inactive stream properly (stop keepalives!)
                logger.info(f"Cleaning up old inactive stream for camera {camera_id[:8]}...")
                try:
                    await existing.stop_stream()
                except Exception as e:
                    logger.warning(f"Error stopping old stream: {e}")
                del self.streams[camera_id]

        # Parse request body for optional parameters
        try:
            body = await request.json()
            max_bw = body.get("max_bandwidth", self.max_bandwidth)
            min_bw = body.get("min_bandwidth", self.min_bandwidth)
        except:
            max_bw = self.max_bandwidth
            min_bw = self.min_bandwidth

        logger.info(f"Starting stream for camera {camera_id[:8]}...")

        # Determine which IP to use based on viewer location
        camera_ip = self._get_camera_ip_for_request(request)

        try:
            # Create stream manager
            stream_manager = StreamManager(
                camera_id=camera_id,
                kurento_client=self.kurento_client,
                external_ip=camera_ip,  # Use selected IP (local or external)
                max_bandwidth=max_bw,
                min_bandwidth=min_bw,
                keepalive_interval=KEEPALIVE_INTERVAL,
                on_error=lambda e: self._handle_stream_error(camera_id, e)
            )

            # Start stream
            result = await stream_manager.start_stream()

            # Store stream manager
            self.streams[camera_id] = stream_manager

            logger.info(f"✅ Stream started for camera {camera_id[:8]}... (session: {result['session_id']})")

            return web.json_response(result, status=201)

        except Exception as e:
            error_msg = f"Failed to start stream: {e}"
            logger.error(error_msg)
            return web.json_response(
                {"error": error_msg},
                status=500
            )

    async def stop_stream(self, request: web.Request) -> web.Response:
        """
        Stop camera stream.

        Path params:
            camera_id: Camera ID
        """
        camera_id = request.match_info['camera_id']

        if camera_id not in self.streams:
            return web.json_response(
                {"error": f"No active stream for camera {camera_id}"},
                status=404
            )

        logger.info(f"Stopping stream for camera {camera_id[:8]}...")

        try:
            result = await self._stop_stream_internal(camera_id)

            logger.info(f"✅ Stream stopped for camera {camera_id[:8]}...")

            return web.json_response(result)

        except Exception as e:
            error_msg = f"Failed to stop stream: {e}"
            logger.error(error_msg)
            return web.json_response(
                {"error": error_msg},
                status=500
            )

    async def list_all_viewers(self, request: web.Request) -> web.Response:
        """
        List all active viewers across all streams.
        """
        if not self.signaling_server:
            return web.json_response(
                {"error": "Signaling server not available"},
                status=503
            )

        viewers = self.signaling_server.get_viewers()

        return web.json_response({
            "viewers": viewers,
            "count": len(viewers)
        })

    async def list_camera_viewers(self, request: web.Request) -> web.Response:
        """
        List viewers for specific camera.

        Path params:
            camera_id: Camera ID
        """
        camera_id = request.match_info['camera_id']

        if not self.signaling_server:
            return web.json_response(
                {"error": "Signaling server not available"},
                status=503
            )

        viewers = self.signaling_server.get_viewers(camera_id)

        return web.json_response({
            "camera_id": camera_id,
            "viewers": viewers,
            "count": len(viewers)
        })

    # ========================================================================
    # Static file serving (Viewer UI)
    # ========================================================================

    async def serve_viewer_html(self, request: web.Request) -> web.Response:
        """
        Serve viewer.html for browser-based camera viewing.

        Usage:
            http://localhost:8080/viewer
            http://localhost:8080/viewer?camera=56C1CADCF1FA4C6CAEBA3E2FD85EFEBF
        """
        static_dir = Path(__file__).parent.parent / 'static'
        viewer_html = static_dir / 'viewer.html'

        if not viewer_html.exists():
            return web.json_response(
                {"error": "Viewer UI not found"},
                status=404
            )

        return web.FileResponse(viewer_html)

    async def serve_viewer_js(self, request: web.Request) -> web.Response:
        """Serve viewer.js JavaScript file"""
        static_dir = Path(__file__).parent.parent / 'static'
        viewer_js = static_dir / 'viewer.js'

        if not viewer_js.exists():
            return web.json_response(
                {"error": "Viewer JS not found"},
                status=404
            )

        return web.FileResponse(
            viewer_js,
            headers={'Content-Type': 'application/javascript'}
        )

    # ========================================================================
    # Internal helpers
    # ========================================================================

    async def _stop_stream_internal(self, camera_id: str) -> Dict[str, Any]:
        """
        Internal stream stop implementation.

        Args:
            camera_id: Camera ID

        Returns:
            Stop result dictionary
        """
        stream_manager = self.streams.get(camera_id)
        if not stream_manager:
            raise ValueError(f"No stream manager for camera {camera_id}")

        # Stop stream
        result = await stream_manager.stop_stream()

        # Remove from active streams
        del self.streams[camera_id]

        return result

    def _get_camera_ip_for_request(self, request: web.Request) -> str:
        """
        Determine which IP to use for camera RTP based on viewer location.

        If viewer is on local network, use local IP (avoids NAT hairpinning issues).
        If viewer is remote, use external IP (requires port forwarding).

        Args:
            request: HTTP request from viewer

        Returns:
            IP address to use in SDP (local or external)
        """
        # Get viewer's IP address
        # Try X-Forwarded-For first (if behind proxy), then peername
        viewer_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        if not viewer_ip:
            viewer_ip = request.remote or 'unknown'

        # Check if viewer is on local network
        is_local = viewer_ip.startswith(self.local_network_prefix) or viewer_ip in ('127.0.0.1', 'localhost')

        selected_ip = self.local_ip if is_local else self.external_ip

        logger.info(
            f"Viewer IP: {viewer_ip} → "
            f"{'Local' if is_local else 'Remote'} network → "
            f"Using camera IP: {selected_ip}"
        )

        return selected_ip

    def _handle_stream_error(self, camera_id: str, error: Exception) -> None:
        """
        Handle stream error callback.

        Args:
            camera_id: Camera ID
            error: Error that occurred
        """
        logger.error(f"Stream error for camera {camera_id}: {error}")

        # Could implement automatic retry logic here
        # For now, just log the error

    def get_stream_webrtc_endpoint(self, camera_id: str) -> Optional[str]:
        """
        Get WebRTC endpoint ID for active stream.

        Used by signaling server to connect viewers.

        Args:
            camera_id: Camera ID

        Returns:
            WebRTC endpoint ID or None
        """
        stream_manager = self.streams.get(camera_id)
        if not stream_manager or not stream_manager.is_active():
            return None

        return stream_manager.get_webrtc_endpoint_id()

    def get_stream_connection_info(self, camera_id: str) -> Optional[tuple]:
        """
        Get pipeline and RTP endpoint info for creating viewer connections.

        This is used by the signaling server to create separate WebRtcEndpoint
        instances for each viewer. Each viewer gets their own WebRtcEndpoint
        connected to the camera's RtpEndpoint.

        Architecture (matching POC2):
        - Camera → RtpEndpoint (receives plain RTP from camera)
        - Viewer → WebRtcEndpoint (WebRTC in browser)
        - Connection: RtpEndpoint.connect(Viewer WebRtcEndpoint)

        Args:
            camera_id: Camera ID

        Returns:
            Tuple of (pipeline_id, rtp_endpoint_id) or None if stream not active
        """
        stream_manager = self.streams.get(camera_id)
        if not stream_manager or not stream_manager.is_active():
            return None

        return (
            stream_manager.get_pipeline_id(),
            stream_manager.get_rtp_endpoint_id()
        )

    # ========================================================================
    # Status
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get API server statistics.

        Returns:
            Dictionary with server stats
        """
        return {
            "host": self.host,
            "port": self.port,
            "active_streams": len(self.streams),
            "streams_by_state": {
                state.value: len([
                    s for s in self.streams.values()
                    if s.get_state() == state
                ])
                for state in StreamState
            },
        }
