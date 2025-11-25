#!/usr/bin/env python3
"""
Add Camera Tool - EMQX Edition
Helper script to prepare certificates for a new camera

Usage:
    python3 tools/add_camera.py <CAMERA_ID>

This script:
1. Verifies EMQX certificates exist
2. Creates camera_files/ package with certificates
3. Generates checksums for verification
4. Provides instructions for FTP deployment
"""

import sys
import hashlib
import shutil
from pathlib import Path

# Add config to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))

try:
    from settings import PROJECT_ROOT, CERT_BASE_DIR
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent
    CERT_BASE_DIR = PROJECT_ROOT / 'certificates'

def calculate_checksum(file_path):
    """Calculate MD5 checksum of a file"""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            md5.update(chunk)
    return md5.hexdigest()

def add_camera(camera_id=None):
    """Prepare certificates for a new camera"""

    print("=" * 60)
    print("VBC01 Camera Setup Tool - EMQX Edition")
    print("=" * 60)
    print()

    # Get camera ID if not provided
    if not camera_id:
        camera_id = input("Enter Camera ID (32-character hex): ").strip().upper()

    # Validate camera ID format
    if len(camera_id) != 32 or not all(c in '0123456789ABCDEF' for c in camera_id):
        print("❌ Invalid camera ID format. Must be 32 hexadecimal characters.")
        sys.exit(1)

    # Check if certificates exist
    ca_cert = CERT_BASE_DIR / 'ca.crt'
    client_cert = CERT_BASE_DIR / 'camera_client.crt'
    client_key = CERT_BASE_DIR / 'camera_client.key'

    if not all(f.exists() for f in [ca_cert, client_cert, client_key]):
        print("❌ Certificates not found!")
        print(f"   Expected location: {CERT_BASE_DIR}")
        print()
        print("Run setup_platform.py first to generate certificates:")
        print("   python3 setup_platform.py")
        sys.exit(1)

    print(f"✅ Found EMQX certificates at {CERT_BASE_DIR}")
    print()

    # Create camera_files directory
    camera_files_dir = PROJECT_ROOT / 'camera_files' / camera_id
    camera_files_dir.mkdir(parents=True, exist_ok=True)

    # Copy and rename certificates for camera
    print("📦 Creating camera certificate package...")

    # Copy CA certificate
    shutil.copy(ca_cert, camera_files_dir / 'mqttCA.crt')
    print(f"   ✓ mqttCA.crt")

    # Combine client cert and key into mqtt.pem (camera expects PEM format)
    with open(camera_files_dir / 'mqtt.pem', 'w') as outfile:
        with open(client_cert, 'r') as certfile:
            outfile.write(certfile.read())
        with open(client_key, 'r') as keyfile:
            outfile.write(keyfile.read())
    print(f"   ✓ mqtt.pem (combined cert + key)")

    # Copy private key separately (camera may need it)
    shutil.copy(client_key, camera_files_dir / 'mqtt.key')
    print(f"   ✓ mqtt.key")

    # Generate checksums
    checksums_file = camera_files_dir / 'checksums.txt'
    with open(checksums_file, 'w') as f:
        for filename in ['mqttCA.crt', 'mqtt.pem', 'mqtt.key']:
            file_path = camera_files_dir / filename
            checksum = calculate_checksum(file_path)
            f.write(f"{checksum}  {filename}\n")
            print(f"   ✓ {filename}: {checksum}")

    print()
    print("=" * 60)
    print("✅ Camera certificate package created successfully!")
    print("=" * 60)
    print()
    print(f"📁 Package location: {camera_files_dir}")
    print()
    print("📤 Deployment Instructions:")
    print("=" * 60)
    print()
    print("1. Connect to camera via FTP:")
    print(f"   ftp <camera_ip>")
    print(f"   Username: root")
    print(f"   Password: <your_camera_password>")
    print()
    print("2. Upload certificates to /root/certs/ on camera:")
    print(f"   cd {camera_files_dir}")
    print(f"   put mqttCA.crt /root/certs/mqttCA.crt")
    print(f"   put mqtt.pem /root/certs/mqtt.pem")
    print(f"   put mqtt.key /root/certs/mqtt.key")
    print()
    print("3. Update camera configuration database:")
    print(f"   Set configSrvHost to your server IP/domain")
    print()
    print("4. Reboot camera to apply changes")
    print()
    print("5. Verify connection:")
    print(f"   - Check EMQX dashboard: http://localhost:18083")
    print(f"   - Check processor logs: tail -f logs/mqtt_processor.log")
    print(f"   - Check dashboard: http://localhost:5000")
    print()

def main():
    """Main function"""
    camera_id = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        add_camera(camera_id)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
