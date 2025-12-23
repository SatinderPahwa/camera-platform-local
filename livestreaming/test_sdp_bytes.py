#!/usr/bin/env python3
"""
Test SDP byte encoding to diagnose \r\n vs \\r\\n issue
"""

import json

# Simulate the SDP answer from Kurento (with actual \r\n bytes)
sdp_with_real_crlf = "v=0\r\no=- 123 456 IN IP4 192.168.199.173\r\ns=Test\r\n"

print("="*80)
print("TEST 1: SDP with REAL \\r\\n bytes")
print("="*80)
print(f"SDP string (repr): {repr(sdp_with_real_crlf)}")
print(f"SDP length: {len(sdp_with_real_crlf)} bytes")
print(f"SDP hex (first 30): {sdp_with_real_crlf[:30].encode('utf-8').hex()}")
print()

# When we put it in a dict and call json.dumps()
message = {
    "sdpOffer": sdp_with_real_crlf
}

json_payload = json.dumps(message)
print("After json.dumps():")
print(f"JSON payload (repr): {repr(json_payload)}")
print(f"JSON payload length: {len(json_payload)} bytes")
print(f"Contains literal backslash-r: {'\\\\r' in json_payload}")
print()

# When camera receives and does json.loads()
received = json.loads(json_payload)
received_sdp = received["sdpOffer"]
print("After camera does json.loads():")
print(f"Received SDP (repr): {repr(received_sdp)}")
print(f"Received SDP length: {len(received_sdp)} bytes")
print(f"Has real CRLF bytes: {received_sdp == sdp_with_real_crlf}")
print()

print("="*80)
print("TEST 2: SDP with LITERAL '\\r\\n' text (WRONG!)")
print("="*80)
# What if we accidentally had the literal string?
sdp_with_literal_text = "v=0\\r\\no=- 123 456 IN IP4 192.168.199.173\\r\\ns=Test\\r\\n"
print(f"SDP string (repr): {repr(sdp_with_literal_text)}")
print(f"SDP length: {len(sdp_with_literal_text)} bytes")
print(f"SDP hex (first 30): {sdp_with_literal_text[:30].encode('utf-8').hex()}")
print()

message2 = {
    "sdpOffer": sdp_with_literal_text
}

json_payload2 = json.dumps(message2)
print("After json.dumps():")
print(f"JSON payload (repr): {repr(json_payload2)}")
print(f"JSON payload length: {len(json_payload2)} bytes")
print()

received2 = json.loads(json_payload2)
received_sdp2 = received2["sdpOffer"]
print("After camera does json.loads():")
print(f"Received SDP (repr): {repr(received_sdp2)}")
print(f"Received SDP length: {len(received_sdp2)} bytes")
print(f"Has literal backslash-r-backslash-n text: {'\\\\r\\\\n' in repr(received_sdp2)}")
print()

print("="*80)
print("DIAGNOSIS")
print("="*80)
print(f"Camera sees literal '\\r\\n' text when: SDP has {'backslash-r-backslash-n' if '\\\\r\\\\n' in repr(sdp_with_literal_text) else 'WRONG'}")
print(f"Camera sees ^M (actual CRLF) when: SDP has {' real CRLF bytes' if '\\r\\n' == '\\x0d\\x0a' else 'WRONG'}")
