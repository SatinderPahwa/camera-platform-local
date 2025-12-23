"""
Kurento Media Server Client

Production-grade WebSocket client for Kurento Media Server communication.
Handles JSON-RPC requests, responses, and events (like ICE candidates).

Based on POC2 proven implementation but refactored for production use.
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import aiohttp

# Configure logging
logger = logging.getLogger(__name__)


class KurentoError(Exception):
    """Base exception for Kurento-related errors"""
    pass


class KurentoConnectionError(KurentoError):
    """Raised when connection to Kurento fails"""
    pass


class KurentoRequestError(KurentoError):
    """Raised when a Kurento request fails"""
    pass


class KurentoClient:
    """
    Async WebSocket client for Kurento Media Server.

    Features:
    - Concurrent request/response handling
    - Event subscription (for ICE candidates, etc.)
    - Automatic reconnection support
    - Request timeout handling
    - Clean error propagation

    Usage:
        client = KurentoClient("ws://localhost:8888/kurento")
        await client.connect()

        # Create pipeline
        result = await client.send_request("create", {
            "type": "MediaPipeline"
        })

        # Subscribe to events
        client.add_event_handler(handle_ice_candidate)

        await client.close()
    """

    def __init__(self, ws_url: str, timeout: int = 30):
        """
        Initialize Kurento client.

        Args:
            ws_url: WebSocket URL (e.g., ws://localhost:8888/kurento)
            timeout: Request timeout in seconds
        """
        self.ws_url = ws_url
        self.timeout = timeout

        # Connection state
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.connected = False

        # Request management
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.lock = asyncio.Lock()

        # Event handling
        self.event_handlers: List[Callable] = []

        # Background tasks
        self._response_task: Optional[asyncio.Task] = None

        logger.info(f"Kurento client initialized for {ws_url}")

    async def connect(self) -> None:
        """
        Connect to Kurento Media Server.

        Raises:
            KurentoConnectionError: If connection fails
        """
        try:
            logger.info(f"Connecting to Kurento at {self.ws_url}")

            # Create aiohttp session
            self.session = aiohttp.ClientSession()

            # Connect WebSocket
            self.ws = await self.session.ws_connect(
                self.ws_url,
                timeout=self.timeout,
                heartbeat=30  # Send ping every 30 seconds
            )

            self.connected = True

            # Start background response handler
            self._response_task = asyncio.create_task(self._handle_responses())

            logger.info("✅ Connected to Kurento WebSocket")

        except Exception as e:
            await self._cleanup()
            error_msg = f"Failed to connect to Kurento: {e}"
            logger.error(error_msg)
            raise KurentoConnectionError(error_msg) from e

    async def close(self) -> None:
        """Close connection and cleanup resources"""
        logger.info("Closing Kurento connection")
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Internal cleanup of resources"""
        self.connected = False

        # Cancel response handler
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            try:
                await self._response_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()

        # Close session
        if self.session and not self.session.closed:
            await self.session.close()

        # Reject all pending requests
        for request_id, future in list(self.pending_requests.items()):
            if not future.done():
                future.set_exception(
                    KurentoConnectionError("Connection closed")
                )
        self.pending_requests.clear()

    async def _handle_responses(self) -> None:
        """
        Background task to handle incoming WebSocket messages.
        Processes both RPC responses and events (like OnIceCandidate).
        """
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        response = json.loads(msg.data)

                        # DEBUG: Log ALL WebSocket messages from Kurento
                        logger.info(f"🔍 RAW Kurento message: {json.dumps(response, indent=2)}")

                        # Check if this is an event (has method but no id)
                        if "method" in response and "id" not in response:
                            await self._handle_event(response)
                        else:
                            # This is an RPC response
                            await self._handle_rpc_response(response)

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse Kurento message: {e}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break

        except asyncio.CancelledError:
            logger.debug("Response handler cancelled")
        except Exception as e:
            logger.error(f"Error in response handler: {e}")
        finally:
            self.connected = False

    async def _handle_rpc_response(self, response: Dict[str, Any]) -> None:
        """Handle JSON-RPC response"""
        request_id = response.get("id")

        if request_id not in self.pending_requests:
            logger.warning(f"Received response for unknown request ID: {request_id}")
            return

        future = self.pending_requests.pop(request_id)

        if "error" in response:
            error = response["error"]
            error_msg = f"Kurento error: {error.get('message', 'Unknown error')}"
            logger.error(error_msg)
            future.set_exception(KurentoRequestError(error_msg))
        else:
            result = response.get("result", {})
            future.set_result(result)

    async def _handle_event(self, event: Dict[str, Any]) -> None:
        """
        Handle events from Kurento (e.g., OnIceCandidate).
        Calls all registered event handlers.
        """
        method = event.get("method")
        logger.info(f"📨 Received Kurento event: {method}")

        # Call all registered handlers
        for handler in self.event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")

    def add_event_handler(self, handler: Callable) -> None:
        """
        Add event handler for Kurento events.

        Args:
            handler: Async or sync function that receives event dict
        """
        self.event_handlers.append(handler)
        logger.debug(f"Added event handler: {handler.__name__}")

    def remove_event_handler(self, handler: Callable) -> None:
        """Remove event handler"""
        if handler in self.event_handlers:
            self.event_handlers.remove(handler)
            logger.debug(f"Removed event handler: {handler.__name__}")

    async def send_request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send JSON-RPC request to Kurento and wait for response.

        Args:
            method: JSON-RPC method (e.g., "create", "invoke")
            params: Method parameters
            timeout: Override default timeout

        Returns:
            Response result dictionary

        Raises:
            KurentoConnectionError: If not connected
            KurentoRequestError: If request fails
            asyncio.TimeoutError: If request times out
        """
        if not self.connected or not self.ws:
            raise KurentoConnectionError("Not connected to Kurento")

        # Generate request ID
        async with self.lock:
            self.request_id += 1
            request_id = self.request_id

        # Create JSON-RPC request
        request = {
            "id": request_id,
            "method": method,
            "params": params,
            "jsonrpc": "2.0"
        }

        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future

        try:
            # Send request
            await self.ws.send_json(request)
            logger.debug(f"Sent request {request_id}: {method}")

            # Wait for response with timeout
            request_timeout = timeout or self.timeout
            result = await asyncio.wait_for(future, timeout=request_timeout)

            logger.debug(f"Received response {request_id}")
            return result

        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            error_msg = f"Request {request_id} timed out after {request_timeout}s"
            logger.error(error_msg)
            raise
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            logger.error(f"Request {request_id} failed: {e}")
            raise

    # ========================================================================
    # High-level API methods for common operations
    # ========================================================================

    async def create_media_pipeline(self) -> str:
        """
        Create a MediaPipeline.

        Returns:
            Pipeline ID
        """
        result = await self.send_request("create", {
            "type": "MediaPipeline"
        })
        pipeline_id = result.get("value")
        logger.info(f"Created MediaPipeline: {pipeline_id}")
        return pipeline_id

    async def create_rtp_endpoint(self, pipeline_id: str) -> str:
        """
        Create an RtpEndpoint for receiving camera RTP stream.

        Args:
            pipeline_id: Parent MediaPipeline ID

        Returns:
            RtpEndpoint ID
        """
        result = await self.send_request("create", {
            "type": "RtpEndpoint",
            "constructorParams": {
                "mediaPipeline": pipeline_id
            }
        })
        endpoint_id = result.get("value")
        logger.info(f"Created RtpEndpoint: {endpoint_id}")
        return endpoint_id

    async def create_webrtc_endpoint(self, pipeline_id: str) -> str:
        """
        Create a WebRtcEndpoint for browser viewers.

        Args:
            pipeline_id: Parent MediaPipeline ID

        Returns:
            WebRtcEndpoint ID
        """
        result = await self.send_request("create", {
            "type": "WebRtcEndpoint",
            "constructorParams": {
                "mediaPipeline": pipeline_id
            }
        })
        endpoint_id = result.get("value")
        logger.info(f"Created WebRtcEndpoint: {endpoint_id}")
        return endpoint_id

    async def generate_sdp_offer(self, endpoint_id: str) -> str:
        """
        Generate SDP offer from endpoint.

        Args:
            endpoint_id: RtpEndpoint or WebRtcEndpoint ID

        Returns:
            SDP offer string
        """
        result = await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "generateOffer"
        })
        sdp = result.get("value")
        logger.debug(f"Generated SDP offer from {endpoint_id}")
        return sdp

    async def process_sdp_offer(self, endpoint_id: str, sdp_offer: str) -> str:
        """
        Process SDP offer and generate answer.

        Args:
            endpoint_id: WebRtcEndpoint ID
            sdp_offer: SDP offer string

        Returns:
            SDP answer string
        """
        result = await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "processOffer",
            "operationParams": {
                "offer": sdp_offer
            }
        })
        sdp_answer = result.get("value")
        logger.debug(f"Processed SDP offer for {endpoint_id}")
        return sdp_answer

    async def connect_endpoints(self, source_id: str, sink_id: str) -> None:
        """
        Connect two media endpoints.

        Args:
            source_id: Source endpoint ID
            sink_id: Sink endpoint ID
        """
        await self.send_request("invoke", {
            "object": source_id,
            "operation": "connect",
            "operationParams": {
                "sink": sink_id
            }
        })
        logger.info(f"Connected {source_id} → {sink_id}")

    async def set_max_video_recv_bandwidth(
        self,
        endpoint_id: str,
        bandwidth: int
    ) -> None:
        """
        Set maximum video receive bandwidth (triggers REMB).

        Args:
            endpoint_id: WebRtcEndpoint ID
            bandwidth: Bandwidth in Kbps
        """
        await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "setMaxVideoRecvBandwidth",
            "operationParams": {
                "maxVideoRecvBandwidth": bandwidth
            }
        })
        logger.info(f"Set maxVideoRecvBandwidth to {bandwidth} Kbps for {endpoint_id}")

    async def set_min_video_recv_bandwidth(
        self,
        endpoint_id: str,
        bandwidth: int
    ) -> None:
        """
        Set minimum video receive bandwidth.

        Args:
            endpoint_id: WebRtcEndpoint ID
            bandwidth: Bandwidth in Kbps
        """
        await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "setMinVideoRecvBandwidth",
            "operationParams": {
                "minVideoRecvBandwidth": bandwidth
            }
        })
        logger.info(f"Set minVideoRecvBandwidth to {bandwidth} Kbps for {endpoint_id}")

    async def set_max_video_send_bandwidth(
        self,
        endpoint_id: str,
        bandwidth: int
    ) -> None:
        """
        Set maximum video send bandwidth for WebRtcEndpoint.

        This is used when Kurento is sending video to a browser viewer.

        Args:
            endpoint_id: WebRtcEndpoint ID
            bandwidth: Bandwidth in Kbps
        """
        await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "setMaxVideoSendBandwidth",
            "operationParams": {
                "maxVideoSendBandwidth": bandwidth
            }
        })
        logger.info(f"Set maxVideoSendBandwidth to {bandwidth} Kbps for {endpoint_id}")

    async def set_min_video_send_bandwidth(
        self,
        endpoint_id: str,
        bandwidth: int
    ) -> None:
        """
        Set minimum video send bandwidth for WebRtcEndpoint.

        This is used when Kurento is sending video to a browser viewer.

        Args:
            endpoint_id: WebRtcEndpoint ID
            bandwidth: Bandwidth in Kbps
        """
        await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "setMinVideoSendBandwidth",
            "operationParams": {
                "minVideoSendBandwidth": bandwidth
            }
        })
        logger.info(f"Set minVideoSendBandwidth to {bandwidth} Kbps for {endpoint_id}")

    async def subscribe_to_event(
        self,
        object_id: str,
        event_type: str
    ) -> str:
        """
        Subscribe to events from a Kurento object.

        Must be called BEFORE the event can occur (e.g., before gatherCandidates).

        Args:
            object_id: ID of the Kurento object (e.g., WebRtcEndpoint ID)
            event_type: Type of event to subscribe to (e.g., "OnIceCandidate", "IceCandidateFound")

        Returns:
            Subscription ID from Kurento
        """
        result = await self.send_request("subscribe", {
            "object": object_id,
            "type": event_type
        })
        subscription_id = result.get("value", "")
        logger.info(f"📡 Subscribed to {event_type} for {object_id} (subscription: {subscription_id})")
        return subscription_id

    async def gather_candidates(self, endpoint_id: str) -> None:
        """
        Start ICE candidate gathering for WebRtcEndpoint.

        Args:
            endpoint_id: WebRtcEndpoint ID
        """
        await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "gatherCandidates"
        })
        logger.info(f"🔍 Called gatherCandidates for {endpoint_id}")

    async def add_ice_candidate(
        self,
        endpoint_id: str,
        candidate: Dict[str, Any]
    ) -> None:
        """
        Add ICE candidate to WebRtcEndpoint.

        Args:
            endpoint_id: WebRtcEndpoint ID
            candidate: ICE candidate dictionary
        """
        await self.send_request("invoke", {
            "object": endpoint_id,
            "operation": "addIceCandidate",
            "operationParams": {
                "candidate": candidate
            }
        })
        logger.debug(f"Added ICE candidate to {endpoint_id}")

    async def release_endpoint(self, endpoint_id: str) -> None:
        """
        Release (delete) a media endpoint.

        Args:
            endpoint_id: Endpoint ID to release
        """
        try:
            await self.send_request("release", {
                "object": endpoint_id
            })
            logger.info(f"Released endpoint: {endpoint_id}")
        except Exception as e:
            logger.warning(f"Failed to release endpoint {endpoint_id}: {e}")

    async def release_pipeline(self, pipeline_id: str) -> None:
        """
        Release (delete) a MediaPipeline and all its endpoints.

        Args:
            pipeline_id: Pipeline ID to release
        """
        try:
            await self.send_request("release", {
                "object": pipeline_id
            })
            logger.info(f"Released pipeline: {pipeline_id}")
        except Exception as e:
            logger.warning(f"Failed to release pipeline {pipeline_id}: {e}")

    # ========================================================================
    # Health check and status
    # ========================================================================

    def is_connected(self) -> bool:
        """Check if connected to Kurento"""
        return self.connected and self.ws and not self.ws.closed

    async def ping(self) -> bool:
        """
        Ping Kurento to check connectivity.

        Returns:
            True if ping successful, False otherwise
        """
        try:
            await self.send_request("ping", {}, timeout=5)
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics.

        Returns:
            Dictionary with connection stats
        """
        return {
            "connected": self.connected,
            "ws_url": self.ws_url,
            "pending_requests": len(self.pending_requests),
            "event_handlers": len(self.event_handlers),
            "ws_closed": self.ws.closed if self.ws else True,
        }


# ============================================================================
# Helper context manager
# ============================================================================

class KurentoClientContext:
    """
    Context manager for automatic Kurento client lifecycle.

    Usage:
        async with KurentoClientContext(ws_url) as client:
            pipeline = await client.create_media_pipeline()
            # ... use client ...
        # Automatically closed on exit
    """

    def __init__(self, ws_url: str, timeout: int = 30):
        self.client = KurentoClient(ws_url, timeout)

    async def __aenter__(self) -> KurentoClient:
        await self.client.connect()
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
        return False
