#!/usr/bin/env python3
"""
Livestreaming Server Launcher

Starts both API and signaling servers for camera livestreaming.

Usage:
    python3 main.py

    Or with custom settings:
    python3 main.py --api-port 8080 --signaling-port 8765

Environment variables:
    KURENTO_WS_URL - Kurento WebSocket URL
    EXTERNAL_IP - External IP address
    API_PORT - API server port
    SIGNALING_PORT - Signaling server port
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from livestreaming.config import settings
from livestreaming.core import KurentoClient, KurentoClientContext
from livestreaming.server import APIServer, SignalingServer


# Configure logging
log_file = settings.LOG_DIR / 'livestreaming.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)

logger = logging.getLogger(__name__)


class LivestreamingService:
    """
    Main service orchestrator.

    Manages lifecycle of:
    - Kurento client connection
    - API server
    - Signaling server
    """

    def __init__(self):
        self.kurento_client: KurentoClient = None
        self.api_server: APIServer = None
        self.signaling_server: SignalingServer = None
        self.running = False

    async def start(self):
        """Start all services"""
        try:
            logger.info("=" * 70)
            logger.info("Starting Camera Livestreaming Service")
            logger.info("=" * 70)

            # Validate configuration
            logger.info("Validating configuration...")
            settings.validate_config()

            # Connect to Kurento
            logger.info(f"Connecting to Kurento at {settings.KURENTO_WS_URL}...")
            self.kurento_client = KurentoClient(settings.KURENTO_WS_URL)
            await self.kurento_client.connect()

            # Test Kurento connection
            if await self.kurento_client.ping():
                logger.info("✅ Kurento connection healthy")
            else:
                logger.warning("⚠️ Kurento ping failed")

            # Create signaling server
            logger.info("Creating signaling server...")
            self.signaling_server = SignalingServer(
                host=settings.SIGNALING_SERVER_HOST,
                port=settings.SIGNALING_SERVER_PORT,
                kurento_client=self.kurento_client,
                get_stream_connection_info=self._get_stream_connection_info,
                max_viewers_per_stream=settings.MAX_VIEWERS_PER_STREAM
            )

            # Setup ICE candidate relay
            self.signaling_server.setup_ice_candidate_relay()

            # Start signaling server
            await self.signaling_server.start()

            # Create API server
            logger.info("Creating API server...")
            self.api_server = APIServer(
                host=settings.API_SERVER_HOST,
                port=settings.API_SERVER_PORT,
                kurento_client=self.kurento_client,
                external_ip=settings.EXTERNAL_IP,
                local_ip=settings.LOCAL_IP,
                local_network_prefix=settings.LOCAL_NETWORK_PREFIX,
                signaling_server=self.signaling_server,
                max_bandwidth=settings.MAX_VIDEO_RECV_BANDWIDTH,
                min_bandwidth=settings.MIN_VIDEO_RECV_BANDWIDTH
            )

            # Start API server
            await self.api_server.start()

            self.running = True

            logger.info("=" * 70)
            logger.info("🚀 Livestreaming Service Started")
            logger.info("=" * 70)
            logger.info(f"API Server:       http://{settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}")
            logger.info(f"Signaling Server: ws://{settings.SIGNALING_SERVER_HOST}:{settings.SIGNALING_SERVER_PORT}")
            logger.info(f"Kurento:          {settings.KURENTO_WS_URL}")
            logger.info(f"External IP:      {settings.EXTERNAL_IP}")
            logger.info("=" * 70)
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"Failed to start service: {e}", exc_info=True)
            await self.stop()
            raise

    async def stop(self):
        """Stop all services"""
        if not self.running:
            return

        logger.info("=" * 70)
        logger.info("Stopping Livestreaming Service")
        logger.info("=" * 70)

        self.running = False

        # Stop API server
        if self.api_server:
            try:
                logger.info("Stopping API server...")
                await self.api_server.stop()
            except Exception as e:
                logger.error(f"Error stopping API server: {e}")

        # Stop signaling server
        if self.signaling_server:
            try:
                logger.info("Stopping signaling server...")
                await self.signaling_server.stop()
            except Exception as e:
                logger.error(f"Error stopping signaling server: {e}")

        # Close Kurento connection
        if self.kurento_client:
            try:
                logger.info("Closing Kurento connection...")
                await self.kurento_client.close()
            except Exception as e:
                logger.error(f"Error closing Kurento: {e}")

        logger.info("✅ Service stopped")

    def _get_stream_connection_info(self, camera_id: str) -> tuple:
        """
        Get pipeline and RTP endpoint info for stream.

        Called by signaling server to create viewer WebRTC endpoints.

        Returns:
            Tuple of (pipeline_id, rtp_endpoint_id) or None
        """
        if not self.api_server:
            return None

        return self.api_server.get_stream_connection_info(camera_id)

    async def run_forever(self):
        """Run until interrupted"""
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop()


async def main():
    """Main entry point"""
    service = LivestreamingService()

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig}")
        asyncio.create_task(service.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        await service.start()
        await service.run_forever()
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
