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
import sqlite3
import socket
from pathlib import Path

# Add config to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))

try:
    from settings import PROJECT_ROOT, CERT_BASE_DIR
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent
    CERT_BASE_DIR = PROJECT_ROOT / 'certificates'

def get_local_ip():
    """Auto-detect server IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def create_camera_database(template_path, output_path, server_ip, server_port=80):
    """Create camera database from template with server configuration"""
    shutil.copy(template_path, output_path)

    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()

    config_srv_host = f"{server_ip}:{server_port}"
    cursor.execute("UPDATE serverConf SET configSrvHost = ? WHERE ID = 1", (config_srv_host,))

    cursor.execute("SELECT configSrvHost FROM serverConf WHERE ID = 1")
    result = cursor.fetchone()

    conn.commit()
    conn.close()

    return result[0] if result else None

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

    # Get server IP
    detected_ip = get_local_ip()
    if detected_ip:
        server_ip = input(f"Server IP [{detected_ip}]: ").strip() or detected_ip
    else:
        server_ip = input("Server IP: ").strip()

    if not server_ip:
        print("❌ Server IP is required")
        sys.exit(1)

    print()

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

    print(f"✅ Found EMQX certificates")

    # Check if database template exists
    db_template = PROJECT_ROOT / 'templates' / 'master_ctrl.db.template'
    if not db_template.exists():
        print(f"❌ Database template not found: {db_template}")
        sys.exit(1)

    print(f"✅ Found database template")
    print()

    # Create camera_files directory
    camera_files_dir = PROJECT_ROOT / 'camera_files' / camera_id
    camera_files_dir.mkdir(parents=True, exist_ok=True)

    # Define the templates directory
    template_dir = CERT_BASE_DIR / 'templates'

    # Copy and rename certificates for camera
    print("📦 Creating camera certificate package...")

    # Copy template MQTT CA certificate (which is our root CA)
    shutil.copy(ca_cert, camera_files_dir / 'mqttCA.crt')
    print(f"   ✓ mqttCA.crt (Our Root CA)")

    # Copy Config Server CA for /root/certs/mqttCA.crt (camera checks this FIRST for SSL)
    shutil.copy(ca_cert, camera_files_dir / 'root-mqttCA.crt')
    print(f"   ✓ root-mqttCA.crt (Config Server CA for /root/certs)")

    # Create complete CA bundle by appending our root CA to the template
    template_ca_bundle = template_dir / 'ca-bundle.trust.template.crt'
    output_ca_bundle = camera_files_dir / 'ca-bundle.trust.crt'
    if template_ca_bundle.exists():
        shutil.copy(template_ca_bundle, output_ca_bundle)
        with open(output_ca_bundle, 'a') as bundle_file:
            with open(ca_cert, 'r') as ca_file:
                bundle_file.write('\n# Platform Root CA\n')
                bundle_file.write(ca_file.read())
        print(f"   ✓ ca-bundle.trust.crt (template + platform root CA)")
    else:
        print(f"   ⚠️  ca-bundle.trust.template.crt not found, bundle not created.")

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

    print()

    # Create camera database from template
    print("📝 Creating camera database...")
    try:
        output_db = camera_files_dir / 'master_ctrl.db'
        config_value = create_camera_database(db_template, output_db, server_ip, 80)
        print(f"   ✓ master_ctrl.db (configSrvHost: {config_value})")
    except Exception as e:
        print(f"   ❌ Failed to create database: {e}")
        sys.exit(1)

    print()

    # Generate checksums
    print("🔐 Generating checksums...")
    checksums_file = camera_files_dir / 'checksums.txt'
    with open(checksums_file, 'w') as f:
        for filename in ['mqttCA.crt', 'root-mqttCA.crt', 'ca-bundle.trust.crt', 'mqtt.pem', 'mqtt.key', 'master_ctrl.db']:
            file_path = camera_files_dir / filename
            if file_path.exists():
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
    print("1. Install lftp on server (if not already installed):")
    print(f"   sudo apt install lftp")
    print()
    print("2. Connect to camera via FTP and upload files:")
    print(f"   cd {camera_files_dir}")
    print(f"   lftp -u root,<camera_password> <camera_ip>")
    print()
    print("3. Inside lftp session:")
    print(f"   # Upload CA bundle to system trust store (OVERWRITES a system file)")
    print(f"   cd /etc/ssl/certs")
    print(f"   put ca-bundle.trust.crt")
    print(f"   ")
    print(f"   # Upload certificates to /root/certs")
    print(f"   cd /root/certs")
    print(f"   put mqtt.pem")
    print(f"   put mqtt.key")
    print(f"   put -O mqttCA.crt root-mqttCA.crt")
    print(f"   ")
    print(f"   # Upload database to /cali")
    print(f"   cd /cali")
    print(f"   put master_ctrl.db")
    print(f"   quit")
    print()
    print("4. Reboot camera (via telnet/ssh):")
    print(f"   reboot")
    print()
    print("5. Verify connection:")
    print(f"   - Check EMQX dashboard: http://{server_ip}:18083")
    print(f"   - Check processor logs: tail -f logs/mqtt_processor.log")
    print(f"   - Check dashboard: https://{server_ip}")
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
