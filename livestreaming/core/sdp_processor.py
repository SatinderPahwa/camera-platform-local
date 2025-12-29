"""
SDP Processor for Camera BCGH Streaming

Handles SDP offer/answer generation and enhancement for Hive cameras.
Based on proven POC2 implementation with production improvements.

Key responsibilities:
- Build custom SDP offers with Hive-specific attributes
- Enhance Kurento SDP answers with camera requirements
- Manage SSRC values and CNAME generation
- Inject external IP addresses for camera connectivity
"""

import random
import uuid
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SDPMediaInfo:
    """Information about SDP media streams"""
    audio_ssrc: int
    video_ssrc: int
    cname: str
    audio_port: int
    video_port: int
    rtcp_port: int


class SDPProcessor:
    """
    Process and enhance SDP offers/answers for camera streaming.

    Handles the complex SDP manipulation required for Hive cameras,
    including custom x-skl attributes and proper SSRC management.
    """

    def __init__(self, external_ip: str):
        """
        Initialize SDP processor.

        Args:
            external_ip: External IP address for camera connectivity
        """
        self.external_ip = external_ip
        logger.info(f"SDP Processor initialized with external IP: {external_ip}")

    def build_custom_sdp_offer(
        self,
        audio_port: int = 9,
        video_port: int = 9,
        rtcp_port: int = 9
    ) -> Tuple[str, SDPMediaInfo]:
        """
        Build custom SDP offer for camera (Hive method).

        This creates an SDP offer that matches what Hive's implementation
        expects, with all required custom attributes.

        Args:
            audio_port: RTP port for audio
            video_port: RTP port for video
            rtcp_port: RTCP port for feedback

        Returns:
            Tuple of (SDP offer string, media info)
        """
        # Generate SSRC values and CNAME
        media_info = self._generate_media_info(audio_port, video_port, rtcp_port)

        # Build SDP offer
        # CRITICAL: Use 0.0.0.0 in camera-facing SDP offer (not external_ip)
        # This prevents Kurento from making incorrect routing assumptions about RTCP
        # Kurento will route RTCP based on where RTP packets actually arrive from
        # Reference: deharo-kcs-develop SessionDescription.java uses 0.0.0.0
        # The answer sent to camera will still contain external_ip (handled by enhance_answer)
        sdp_lines = [
            "v=0",
            f"o=- {random.randint(1000000000, 9999999999)} "
            f"{random.randint(1000000000, 9999999999)} IN IP4 0.0.0.0",
            "s=Camera Livestream",
            f"c=IN IP4 0.0.0.0",
            "t=0 0",
            # Audio media
            f"m=audio {media_info.audio_port} RTP/AVPF 96 0",
            f"a=rtcp:{media_info.audio_port + 1}",  # Explicitly specify camera's audio RTCP port
            "a=rtpmap:96 opus/48000/2",
            "a=rtpmap:0 PCMU/8000",
            "a=sendrecv",  # Audio is bidirectional (matches original Hive)
            "a=direction:active",  # CRITICAL for REMB: offer must be active, answer passive
            f"a=ssrc:{media_info.audio_ssrc} cname:{media_info.cname}",
            # Video media
            f"m=video {media_info.video_port} RTP/AVPF 103",
            f"a=rtcp:{media_info.video_port + 1}",  # Explicitly specify camera's video RTCP port
            "a=rtpmap:103 H264/90000",
            "a=fmtp:103 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f",
            "a=rtcp-fb:103 nack",
            "a=rtcp-fb:103 nack pli",
            "a=rtcp-fb:103 goog-remb",
            "a=rtcp-fb:103 ccm fir",
            "a=sendonly",  # Camera only sends video, doesn't receive (Kurento will respond with recvonly)
            "a=direction:active",  # CRITICAL for REMB: offer must be active, answer passive
            f"a=ssrc:{media_info.video_ssrc} cname:{media_info.cname}",
            # NOTE: x-skl attributes are NOT in the offer, only in the answer!
            # POC2 adds them via enhance_answer() after Kurento processes the offer
        ]

        sdp_offer = "\r\n".join(sdp_lines) + "\r\n"

        logger.info("Built custom SDP offer with Hive attributes and explicit RTCP ports")
        logger.debug(f"Media info: audio_ssrc={media_info.audio_ssrc}, "
                    f"video_ssrc={media_info.video_ssrc}, cname={media_info.cname}, "
                    f"audio_rtcp={media_info.audio_port + 1}, video_rtcp={media_info.video_port + 1}")

        return sdp_offer, media_info

    def enhance_answer(
        self,
        sdp_answer: str,
        external_ip: str,
        media_info: SDPMediaInfo
    ) -> str:
        """
        Enhance Kurento's SDP answer with Hive-specific attributes (matching POC2).

        This follows the exact approach from POC2's enhance_kurento_sdp():
        1. Replace session name (avoid spaces that might cause hostname parsing issues)
        2. Append x-skl attributes to the end
        3. Replace all IP addresses with external IP

        NOTE: Direction attributes (a=recvonly) are NOT flipped! POC2 keeps them as-is.

        Args:
            sdp_answer: Original SDP answer from Kurento RtpEndpoint.processOffer()
            external_ip: External IP address for camera connectivity
            media_info: Media info with SSRC and CNAME values

        Returns:
            Enhanced SDP answer string ready to send to camera
        """
        import re

        # Step 0: CRITICAL VALIDATION - Check for REMB support (matching AWS implementation)
        # If Kurento's answer doesn't contain "a=direction:passive", REMB won't work
        if "a=direction:passive" not in sdp_answer:
            logger.warning("⚠️ Answer from RtpEndpoint does NOT contain 'a=direction:passive' - REMB may not work!")
            logger.warning("This indicates Kurento may not be configured to send RTCP/REMB feedback")
        else:
            logger.info("✅ Answer contains 'a=direction:passive' - REMB should be supported")

        # Step 1: DO NOT change session name! POC2 keeps "s=Kurento Media Server" as-is
        enhanced = sdp_answer

        # Step 2: CRITICAL - Replace Kurento's generated SSRCs with our fixed Hive SSRCs
        # (matching POC2 lines 272-290)
        # Find and replace audio SSRC
        enhanced = re.sub(
            r'(m=audio.*?)a=ssrc:(\d+)',
            f'\\1a=ssrc:{media_info.audio_ssrc}',
            enhanced,
            count=1,
            flags=re.DOTALL
        )
        # Find and replace video SSRC
        enhanced = re.sub(
            r'(m=video.*?)a=ssrc:(\d+)',
            f'\\1a=ssrc:{media_info.video_ssrc}',
            enhanced,
            count=1,
            flags=re.DOTALL
        )
        # Replace cname in all ssrc lines
        enhanced = re.sub(r'cname:[^\s\r\n]+', f'cname:{media_info.cname}', enhanced)

        # Step 3: Append x-skl attributes (matching POC2's enhance_kurento_sdp line 293-296)
        enhanced = enhanced + \
            f"a=x-skl-ssrca:{media_info.audio_ssrc}\r\n" + \
            f"a=x-skl-ssrcv:{media_info.video_ssrc}\r\n" + \
            f"a=x-skl-cname:{media_info.cname}"

        # Step 4: Replace all IP addresses with external IP (matching POC2 line 299-300)
        ip_regex = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        enhanced = re.sub(ip_regex, external_ip, enhanced)

        # Step 5: Add a=direction:passive to video media (matching original Hive implementation)
        # This tells the camera that Kurento is passive and camera should initiate media
        lines = enhanced.split('\r\n')
        result_lines = []
        in_video = False
        direction_added = False

        for line in lines:
            if line.startswith('m=video'):
                in_video = True
                direction_added = False
            elif line.startswith('m='):
                in_video = False

            result_lines.append(line)

            # Add a=direction:passive after a=recvonly in video section
            if in_video and line == 'a=recvonly' and not direction_added:
                result_lines.append('a=direction:passive')
                direction_added = True

        enhanced = '\r\n'.join(result_lines)

        logger.info(f"Enhanced SDP answer: replaced SSRCs with fixed Hive values ({media_info.audio_ssrc}, {media_info.video_ssrc}), added x-skl attributes, replaced IPs with {external_ip}, added a=direction:passive to video")
        return enhanced

    def enhance_kurento_sdp_answer(
        self,
        sdp_answer: str,
        media_info: SDPMediaInfo
    ) -> str:
        """
        Enhance Kurento's SDP answer with Hive-specific attributes (alternative method).

        Kurento generates a valid SDP answer, but cameras expect additional
        custom attributes. This method injects those attributes.

        Args:
            sdp_answer: Original SDP answer from Kurento
            media_info: Media info with SSRC and CNAME values

        Returns:
            Enhanced SDP answer string
        """
        lines = sdp_answer.split('\r\n')
        enhanced_lines = []
        audio_section = False
        video_section = False

        for line in lines:
            enhanced_lines.append(line)

            # Replace connection IP with external IP
            if line.startswith('c=IN IP4'):
                enhanced_lines[-1] = f"c=IN IP4 {self.external_ip}"

            # Track which media section we're in
            if line.startswith('m=audio'):
                audio_section = True
                video_section = False
            elif line.startswith('m=video'):
                audio_section = False
                video_section = True

            # After audio SSRC line, ensure x-skl attribute
            if audio_section and line.startswith('a=ssrc:'):
                # Check if x-skl-ssrca already exists
                if not any(l.startswith('a=x-skl-ssrca:') for l in enhanced_lines):
                    enhanced_lines.append(f"a=x-skl-ssrca:{media_info.audio_ssrc}")

            # After video SSRC line, ensure x-skl attributes
            if video_section and line.startswith('a=ssrc:'):
                # Check if x-skl attributes already exist
                if not any(l.startswith('a=x-skl-ssrcv:') for l in enhanced_lines):
                    enhanced_lines.append(f"a=x-skl-ssrcv:{media_info.video_ssrc}")
                if not any(l.startswith('a=x-skl-cname:') for l in enhanced_lines):
                    enhanced_lines.append(f"a=x-skl-cname:{media_info.cname}")

        # Ensure x-skl attributes are at the end if not already added
        has_ssrca = any(l.startswith('a=x-skl-ssrca:') for l in enhanced_lines)
        has_ssrcv = any(l.startswith('a=x-skl-ssrcv:') for l in enhanced_lines)
        has_cname = any(l.startswith('a=x-skl-cname:') for l in enhanced_lines)

        if not has_ssrca:
            enhanced_lines.append(f"a=x-skl-ssrca:{media_info.audio_ssrc}")
        if not has_ssrcv:
            enhanced_lines.append(f"a=x-skl-ssrcv:{media_info.video_ssrc}")
        if not has_cname:
            enhanced_lines.append(f"a=x-skl-cname:{media_info.cname}")

        enhanced_sdp = "\r\n".join(enhanced_lines)

        logger.info("Enhanced Kurento SDP answer with Hive attributes")
        return enhanced_sdp

    def replace_ssrcs_in_answer(
        self,
        sdp_answer: str,
        media_info: SDPMediaInfo
    ) -> str:
        """
        Replace Kurento's generated SSRCs with fixed Hive SSRCs.

        Kurento generates its own SSRC values, but cameras expect
        the values from our original offer. This replaces them.

        Args:
            sdp_answer: SDP answer from Kurento
            media_info: Media info with our fixed SSRC values

        Returns:
            SDP answer with replaced SSRCs
        """
        lines = sdp_answer.split('\r\n')
        modified_lines = []
        audio_section = False

        for line in lines:
            # Track section
            if line.startswith('m=audio'):
                audio_section = True
            elif line.startswith('m=video'):
                audio_section = False

            # Replace SSRC lines
            if line.startswith('a=ssrc:'):
                if audio_section:
                    # Replace with audio SSRC
                    parts = line.split(' ', 1)
                    if len(parts) > 1:
                        modified_lines.append(f"a=ssrc:{media_info.audio_ssrc} {parts[1]}")
                    else:
                        modified_lines.append(f"a=ssrc:{media_info.audio_ssrc} cname:{media_info.cname}")
                else:
                    # Replace with video SSRC
                    parts = line.split(' ', 1)
                    if len(parts) > 1:
                        modified_lines.append(f"a=ssrc:{media_info.video_ssrc} {parts[1]}")
                    else:
                        modified_lines.append(f"a=ssrc:{media_info.video_ssrc} cname:{media_info.cname}")
            else:
                modified_lines.append(line)

        logger.debug("Replaced Kurento SSRCs with fixed Hive SSRCs")
        return "\r\n".join(modified_lines)

    def validate_sdp_answer(self, sdp_answer: str) -> Dict[str, bool]:
        """
        Validate that SDP answer contains required attributes.

        Args:
            sdp_answer: SDP answer to validate

        Returns:
            Dictionary with validation results
        """
        checks = {
            "has_goog_remb": "goog-remb" in sdp_answer,
            "has_x_skl_ssrca": "x-skl-ssrca:" in sdp_answer,
            "has_x_skl_ssrcv": "x-skl-ssrcv:" in sdp_answer,
            "has_x_skl_cname": "x-skl-cname:" in sdp_answer,
            "has_audio_media": "m=audio" in sdp_answer,
            "has_video_media": "m=video" in sdp_answer,
            "has_h264": "H264" in sdp_answer,
        }

        all_valid = all(checks.values())
        if all_valid:
            logger.info("✅ SDP answer validation passed")
        else:
            failed = [k for k, v in checks.items() if not v]
            logger.warning(f"⚠️ SDP answer validation failed: {failed}")

        return checks

    def extract_sdp_info(self, sdp: str) -> Dict[str, any]:
        """
        Extract useful information from SDP.

        Args:
            sdp: SDP string

        Returns:
            Dictionary with extracted info
        """
        info = {
            "audio_ssrc": None,
            "video_ssrc": None,
            "cname": None,
            "audio_port": None,
            "video_port": None,
            "connection_ip": None,
        }

        lines = sdp.split('\r\n')
        audio_section = False

        for line in lines:
            # Connection IP
            if line.startswith('c=IN IP4'):
                parts = line.split()
                if len(parts) >= 3:
                    info["connection_ip"] = parts[2]

            # Track sections
            if line.startswith('m=audio'):
                audio_section = True
                parts = line.split()
                if len(parts) >= 2:
                    info["audio_port"] = int(parts[1])
            elif line.startswith('m=video'):
                audio_section = False
                parts = line.split()
                if len(parts) >= 2:
                    info["video_port"] = int(parts[1])

            # SSRC
            if line.startswith('a=ssrc:'):
                parts = line.split()
                ssrc = int(parts[0].split(':')[1])
                if audio_section:
                    info["audio_ssrc"] = ssrc
                else:
                    info["video_ssrc"] = ssrc

                # CNAME
                if 'cname:' in line:
                    cname_part = [p for p in parts if p.startswith('cname:')]
                    if cname_part:
                        info["cname"] = cname_part[0].split(':')[1]

        return info

    # ========================================================================
    # Private helper methods
    # ========================================================================

    def _generate_media_info(
        self,
        audio_port: int,
        video_port: int,
        rtcp_port: int
    ) -> SDPMediaInfo:
        """
        Generate media information for SDP.

        Returns:
            SDPMediaInfo with generated values
        """
        # Use Hive's FIXED SSRC values (matching POC2 and Hive Camera.java)
        # These must match what the camera expects!
        audio_ssrc = 229236353
        video_ssrc = 1607797317

        # Generate CNAME (unique identifier)
        # Format: user{random}@host-{uuid}
        user_id = random.randint(1000000000, 9999999999)
        host_id = uuid.uuid4().hex[:8]
        cname = f"user{user_id}@host-{host_id}"

        return SDPMediaInfo(
            audio_ssrc=audio_ssrc,
            video_ssrc=video_ssrc,
            cname=cname,
            audio_port=audio_port,
            video_port=video_port,
            rtcp_port=rtcp_port
        )

    def _inject_external_ip(self, sdp: str) -> str:
        """
        Replace IP addresses in SDP with external IP.

        Args:
            sdp: Original SDP

        Returns:
            SDP with external IP
        """
        lines = []
        for line in sdp.split('\r\n'):
            if line.startswith('c=IN IP4'):
                lines.append(f"c=IN IP4 {self.external_ip}")
            elif line.startswith('o='):
                # Replace IP in origin line
                parts = line.split()
                if len(parts) >= 6:
                    parts[5] = self.external_ip
                    lines.append(' '.join(parts))
                else:
                    lines.append(line)
            else:
                lines.append(line)

        return '\r\n'.join(lines)


# ============================================================================
# Utility functions
# ============================================================================

def format_sdp_for_logging(sdp: str, max_lines: int = 20) -> str:
    """
    Format SDP for logging (truncate if too long).

    Args:
        sdp: SDP string
        max_lines: Maximum lines to show

    Returns:
        Formatted SDP string
    """
    lines = sdp.split('\r\n')
    if len(lines) <= max_lines:
        return sdp

    truncated = lines[:max_lines]
    truncated.append(f"... ({len(lines) - max_lines} more lines)")
    return '\r\n'.join(truncated)


def escape_sdp_for_json(sdp: str) -> str:
    """
    Escape SDP for JSON transmission (MQTT payload).

    Converts line endings to escaped format.

    Args:
        sdp: SDP string with \r\n line endings

    Returns:
        SDP string with \\r\\n for JSON
    """
    return sdp.replace('\r\n', '\\r\\n')


def unescape_sdp_from_json(sdp: str) -> str:
    """
    Unescape SDP from JSON format.

    Args:
        sdp: SDP string with \\r\\n

    Returns:
        SDP string with \r\n line endings
    """
    return sdp.replace('\\r\\n', '\r\n')


def compare_sdp_attributes(sdp1: str, sdp2: str) -> Dict[str, bool]:
    """
    Compare two SDP strings for key attributes.

    Useful for debugging SDP differences.

    Args:
        sdp1: First SDP
        sdp2: Second SDP

    Returns:
        Dictionary with comparison results
    """
    def extract_attributes(sdp):
        return {
            "has_audio": "m=audio" in sdp,
            "has_video": "m=video" in sdp,
            "has_h264": "H264" in sdp,
            "has_remb": "goog-remb" in sdp,
            "has_x_skl_ssrca": "x-skl-ssrca" in sdp,
            "has_x_skl_ssrcv": "x-skl-ssrcv" in sdp,
            "has_x_skl_cname": "x-skl-cname" in sdp,
            "audio_ssrc": None,
            "video_ssrc": None,
        }

    attrs1 = extract_attributes(sdp1)
    attrs2 = extract_attributes(sdp2)

    return {
        "match_audio": attrs1["has_audio"] == attrs2["has_audio"],
        "match_video": attrs1["has_video"] == attrs2["has_video"],
        "match_h264": attrs1["has_h264"] == attrs2["has_h264"],
        "match_remb": attrs1["has_remb"] == attrs2["has_remb"],
        "match_x_skl": (
            attrs1["has_x_skl_ssrca"] == attrs2["has_x_skl_ssrca"] and
            attrs1["has_x_skl_ssrcv"] == attrs2["has_x_skl_ssrcv"] and
            attrs1["has_x_skl_cname"] == attrs2["has_x_skl_cname"]
        ),
    }
