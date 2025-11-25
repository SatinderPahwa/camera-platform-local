#!/usr/bin/env python3
"""
EMQX Connection Test Tool
Tests connection to local EMQX broker and verifies configuration

Usage:
    python3 tools/test_emqx.py
"""

import sys
import time
import json
from pathlib import Path
import paho.mqtt.client as mqtt

# Add config to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))

try:
    from settings import *
except ImportError as e:
    print(f"❌ Failed to import configuration: {e}")
    print("Make sure .env file exists and setup_platform.py has been run")
    sys.exit(1)

class EMQXTester:
    def __init__(self):
        self.connected = False
        self.messages_received = []

    def on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            self.connected = True
            print("✅ Connected to EMQX broker")

            # Subscribe to test topic
            test_topic = "test/emqx/connection"
            client.subscribe(test_topic, qos=1)
            print(f"✅ Subscribed to {test_topic}")
        else:
            print(f"❌ Failed to connect: {rc}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.connected = False
        print("⚠️  Disconnected from EMQX broker")

    def on_message(self, client, userdata, msg):
        """Callback for received messages"""
        payload = msg.payload.decode('utf-8')
        self.messages_received.append({
            'topic': msg.topic,
            'payload': payload,
            'qos': msg.qos
        })
        print(f"📨 Received: {msg.topic} -> {payload}")

    def test_connection(self):
        """Test EMQX connection"""
        print("=" * 60)
        print("EMQX Connection Test")
        print("=" * 60)
        print()

        # Display configuration
        print("Configuration:")
        print(f"  Broker Host: {MQTT_BROKER_HOST}")
        print(f"  Broker Port: {MQTT_BROKER_PORT}")
        print(f"  Keep Alive: {MQTT_KEEPALIVE}s")
        print()

        # Create MQTT client
        client = mqtt.Client(client_id="emqx_test_tool")
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message

        # Connect to broker
        print("Connecting to EMQX broker...")
        try:
            client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE)
            client.loop_start()

            # Wait for connection
            timeout = 10
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.5)

            if not self.connected:
                print("❌ Connection timeout")
                return False

            # Publish test message
            print()
            print("Publishing test message...")
            test_topic = "test/emqx/connection"
            test_payload = json.dumps({
                "test": "EMQX connection test",
                "timestamp": int(time.time())
            })

            result = client.publish(test_topic, test_payload, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print("✅ Test message published")
            else:
                print(f"❌ Failed to publish: {result.rc}")
                return False

            # Wait for message
            print("Waiting for test message...")
            time.sleep(2)

            if len(self.messages_received) > 0:
                print("✅ Test message received successfully")
                print()
                print("Message Details:")
                for msg in self.messages_received:
                    print(f"  Topic: {msg['topic']}")
                    print(f"  Payload: {msg['payload']}")
                    print(f"  QoS: {msg['qos']}")
            else:
                print("⚠️  No messages received")

            # Cleanup
            client.loop_stop()
            client.disconnect()

            print()
            print("=" * 60)
            print("✅ EMQX connection test completed successfully!")
            print("=" * 60)
            print()
            print("Next Steps:")
            print("  - Start all services: ./scripts/managed_start.sh start")
            print("  - Add cameras: python3 tools/add_camera.py <CAMERA_ID>")
            print("  - View dashboard: http://localhost:5000")
            print()

            return True

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            print()
            print("Troubleshooting:")
            print("  1. Check if EMQX is running:")
            print("     emqx ctl status")
            print()
            print("  2. Start EMQX if not running:")
            print("     sudo emqx start")
            print()
            print("  3. Check EMQX dashboard:")
            print("     http://localhost:18083 (admin/public)")
            print()
            return False

def main():
    """Main function"""
    tester = EMQXTester()

    try:
        success = tester.test_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
