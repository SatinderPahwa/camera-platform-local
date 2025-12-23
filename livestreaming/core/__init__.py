"""
Livestreaming Core Modules

Core functionality for camera BCGH livestreaming.
"""

from .kurento_client import (
    KurentoClient,
    KurentoClientContext,
    KurentoError,
    KurentoConnectionError,
    KurentoRequestError
)

from .sdp_processor import (
    SDPProcessor,
    SDPMediaInfo,
    format_sdp_for_logging,
    escape_sdp_for_json,
    unescape_sdp_from_json,
)

from .keepalive import (
    KeepaliveSender,
    KeepaliveSenderContext,
    KeepaliveError,
)

from .stream_manager import (
    StreamManager,
    StreamManagerContext,
    StreamManagerError,
    StreamState,
)

__all__ = [
    # Kurento client
    "KurentoClient",
    "KurentoClientContext",
    "KurentoError",
    "KurentoConnectionError",
    "KurentoRequestError",
    # SDP processor
    "SDPProcessor",
    "SDPMediaInfo",
    "format_sdp_for_logging",
    "escape_sdp_for_json",
    "unescape_sdp_from_json",
    # Keepalive sender
    "KeepaliveSender",
    "KeepaliveSenderContext",
    "KeepaliveError",
    # Stream manager
    "StreamManager",
    "StreamManagerContext",
    "StreamManagerError",
    "StreamState",
]
