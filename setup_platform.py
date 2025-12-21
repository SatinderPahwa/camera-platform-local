#!/usr/bin/env python3
"""
VBC01 Camera Platform - Setup Wizard
Automated platform deployment with certificate generation and configuration
"""

import os
import sys
import subprocess
import secrets
import argparse
from pathlib import Path
from datetime import datetime
import json

class PlatformSetup:
    def __init__(self):
        self.project_root = Path(__file__).parent.absolute()
        self.config = {}

    def print_banner(self):
        """Print setup wizard banner"""
        print("=" * 70)
        print("🎯 VBC01 Camera Platform - Setup Wizard")
        print("   Local MQTT Edition (EMQX)")
        print("=" * 70)
        print()
        print("This wizard will:")
        print("  ✅ Generate all TLS certificates")
        print("  ✅ Configure EMQX broker")
        print("  ✅ Create camera deployment files")
        print("  ✅ Set up all services")
        print("  ✅ Generate personalized deployment guide")
        print()
        print("=" * 70)
        print()

    def collect_inputs(self):
        """Collect required configuration from user"""
        print("📋 CONFIGURATION")
        print("-" * 70)
        print()

        # Network Configuration
        print("🌐 Network Configuration")
        self.config['domain'] = input("  External domain name (e.g., camera.pahwa.net): ").strip()
        self.config['local_ip'] = input("  Local server IP (e.g., 192.168.199.173): ").strip()
        print()

        # Telegram Configuration
        print("📱 Telegram Notification Configuration")
        self.config['telegram_token'] = input("  Telegram bot token: ").strip()
        self.config['telegram_chat_id'] = input("  Telegram chat ID: ").strip()
        print()

        # TURN Server Configuration
        print("🌐 TURN Server Configuration (for remote livestreaming)")
        self.config['turn_url'] = input("  TURN server URL (e.g., turns:camera.pahwa.net:5349): ").strip()
        self.config['turn_username'] = input("  TURN username: ").strip()
        self.config['turn_password'] = input("  TURN password: ").strip()
        print()

        # Optional: Google OAuth
        print("🔐 Authentication Configuration")
        setup_oauth = input("  Configure Google OAuth? (y/n) [n]: ").strip().lower()
        if setup_oauth == 'y':
            self.config['google_client_id'] = input("    Google OAuth Client ID: ").strip()
            self.config['google_client_secret'] = input("    Google OAuth Client Secret: ").strip()
        else:
            self.config['google_client_id'] = ''
            self.config['google_client_secret'] = ''
        print()

        # Auto-generate secrets
        print("🔑 Generating secure keys...")
        self.config['flask_secret'] = secrets.token_hex(32)
        self.config['admin_username'] = 'admin'
        self.config['admin_password'] = secrets.token_urlsafe(16)
        print(f"  ✅ Flask secret key generated")
        print(f"  ✅ Admin username: {self.config['admin_username']}")
        print(f"  ✅ Admin password: {self.config['admin_password']}")
        print(f"     ⚠️  SAVE THIS PASSWORD!")
        print()

    def validate_inputs(self):
        """Validate configuration inputs"""
        print("✅ Validating configuration...")

        errors = []

        # Validate domain
        if not self.config['domain'] or '.' not in self.config['domain']:
            errors.append("Invalid domain name")

        # Validate IP
        parts = self.config['local_ip'].split('.')
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            errors.append("Invalid IP address")

        # Validate Telegram
        if not self.config['telegram_token']:
            errors.append("Telegram bot token required")
        if not self.config['telegram_chat_id']:
            errors.append("Telegram chat ID required")

        # Validate TURN
        if not self.config['turn_url']:
            errors.append("TURN server URL required")

        if errors:
            print("❌ Validation failed:")
            for error in errors:
                print(f"   - {error}")
            return False

        print("✅ Configuration valid")
        return True

    def create_directories(self):
        """Create required directory structure"""
        print("\n📁 Creating directory structure...")

        dirs = [
            'certificates',
            'camera_files',
            'config',
            'data/uploads',
            'data/mqtt',
            'logs',
            'pids',
            'deployment',
            'backup'
        ]

        for dir_path in dirs:
            full_path = self.project_root / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ {dir_path}/")

        print("✅ Directory structure created")

    def generate_certificates(self):
        """Generate all TLS certificates"""
        print("\n🔐 Generating TLS certificates...")

        cert_dir = self.project_root / 'certificates'
        os.chdir(cert_dir)

        try:
            # Generate CA certificate
            print("  📜 Generating CA certificate...")
            subprocess.run([
                'openssl', 'genrsa', '-out', 'ca.key', '4096'
            ], check=True, capture_output=True)

            subprocess.run([
                'openssl', 'req', '-x509', '-new', '-nodes',
                '-key', 'ca.key',
                '-sha256', '-days', '3650',
                '-out', 'ca.crt',
                '-subj', f'/C=UK/ST=London/L=London/O=Camera Platform/OU=Infrastructure/CN=Camera Platform Root CA'
            ], check=True, capture_output=True)
            print("  ✅ CA certificate generated")

            # Generate broker certificate
            print("  📜 Generating broker certificate...")
            subprocess.run([
                'openssl', 'genrsa', '-out', 'broker.key', '2048'
            ], check=True, capture_output=True)

            subprocess.run([
                'openssl', 'req', '-new',
                '-key', 'broker.key',
                '-out', 'broker.csr',
                '-subj', f'/C=UK/ST=London/L=London/O=Camera Platform/OU=MQTT Broker/CN={self.config["domain"]}'
            ], check=True, capture_output=True)

            # Create extensions file for SAN
            with open('broker_ext.cnf', 'w') as f:
                domain_parts = self.config['domain'].split('.')
                wildcard_domain = f"*.{'.'.join(domain_parts[1:])}" if len(domain_parts) > 1 else self.config['domain']

                f.write(f"""basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = {self.config['domain']}
DNS.2 = {wildcard_domain}
IP.1 = {self.config['local_ip']}
""")

            subprocess.run([
                'openssl', 'x509', '-req',
                '-in', 'broker.csr',
                '-CA', 'ca.crt',
                '-CAkey', 'ca.key',
                '-CAcreateserial',
                '-out', 'broker.crt',
                '-days', '3650',
                '-sha256',
                '-extfile', 'broker_ext.cnf'
            ], check=True, capture_output=True)

            os.remove('broker.csr')
            os.remove('broker_ext.cnf')
            print("  ✅ Broker certificate generated")

            # Generate client certificate (shared by all cameras)
            print("  📜 Generating client certificate...")
            subprocess.run([
                'openssl', 'genrsa', '-out', 'camera_client.key', '2048'
            ], check=True, capture_output=True)

            subprocess.run([
                'openssl', 'req', '-new',
                '-key', 'camera_client.key',
                '-out', 'camera_client.csr',
                '-subj', '/C=UK/ST=London/L=London/O=Camera Platform/OU=Camera Client/CN=camera_client'
            ], check=True, capture_output=True)

            with open('client_ext.cnf', 'w') as f:
                f.write("""basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
""")

            subprocess.run([
                'openssl', 'x509', '-req',
                '-in', 'camera_client.csr',
                '-CA', 'ca.crt',
                '-CAkey', 'ca.key',
                '-CAcreateserial',
                '-out', 'camera_client.crt',
                '-days', '3650',
                '-sha256',
                '-extfile', 'client_ext.cnf'
            ], check=True, capture_output=True)

            os.remove('camera_client.csr')
            os.remove('client_ext.cnf')
            print("  ✅ Client certificate generated")

            # Verify certificates
            print("  🔍 Verifying certificates...")
            subprocess.run([
                'openssl', 'verify', '-CAfile', 'ca.crt', 'broker.crt'
            ], check=True, capture_output=True)
            subprocess.run([
                'openssl', 'verify', '-CAfile', 'ca.crt', 'camera_client.crt'
            ], check=True, capture_output=True)
            print("  ✅ Certificates verified")

            os.chdir(self.project_root)
            print("✅ All certificates generated successfully")
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ Certificate generation failed: {e}")
            os.chdir(self.project_root)
            return False

    def create_camera_files(self):
        """Create camera certificate package"""
        print("\n📦 Creating camera certificate package...")

        cert_dir = self.project_root / 'certificates'
        camera_dir = self.project_root / 'camera_files'

        # Copy certificates with camera-specific names
        import shutil
        shutil.copy(cert_dir / 'ca.crt', camera_dir / 'mqttCA.crt')
        shutil.copy(cert_dir / 'camera_client.crt', camera_dir / 'mqtt.pem')
        shutil.copy(cert_dir / 'camera_client.key', camera_dir / 'mqtt.key')

        print("  ✅ mqttCA.crt")
        print("  ✅ mqtt.pem")
        print("  ✅ mqtt.key")

        # Generate checksums
        import hashlib
        checksums = {}
        for filename in ['mqttCA.crt', 'mqtt.pem', 'mqtt.key']:
            filepath = camera_dir / filename
            with open(filepath, 'rb') as f:
                checksums[filename] = hashlib.md5(f.read()).hexdigest()

        # Write checksums file
        with open(camera_dir / 'checksums.txt', 'w') as f:
            f.write("# Camera Certificate Checksums\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
            for filename, checksum in checksums.items():
                f.write(f"{checksum}  {filename}\n")

        print("  ✅ checksums.txt")
        print("\n✅ Camera certificate package created")

    def generate_env_file(self):
        """Generate .env configuration file"""
        print("\n⚙️  Generating .env configuration...")

        env_content = f"""# VBC01 Camera Platform Configuration
# Generated: {datetime.now().isoformat()}

# ============================================================================
# Network Configuration
# ============================================================================
EMQX_BROKER_ENDPOINT={self.config['domain']}
EMQX_BROKER_PORT=8883
CONFIG_SERVER_HOST={self.config['local_ip']}
CONFIG_SERVER_PORT=8443

# ============================================================================
# MQTT Configuration
# ============================================================================
# Local MQTT broker connection (processor connects to local EMQX)
# Port 1883 for non-TLS local connections (use 8883 only if MQTT_USE_TLS=true)
MQTT_BROKER_HOST=127.0.0.1
MQTT_BROKER_PORT=1883
MQTT_KEEPALIVE=60
MQTT_USE_TLS=false
PROCESSOR_CLIENT_ID=camera_event_processor

# ============================================================================
# Telegram Notifications
# ============================================================================
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN={self.config['telegram_token']}
TELEGRAM_CHAT_ID={self.config['telegram_chat_id']}
TELEGRAM_NOTIFY_MOTION=true
TELEGRAM_NOTIFY_PERSON=true
TELEGRAM_NOTIFY_SOUND=false

# ============================================================================
# Dashboard Configuration
# ============================================================================
DASHBOARD_SERVER_HOST=0.0.0.0
DASHBOARD_SERVER_PORT=5000
DASHBOARD_URL=https://{self.config['domain']}:5000

FLASK_SECRET_KEY={self.config['flask_secret']}
ADMIN_USERNAME={self.config['admin_username']}
ADMIN_PASSWORD={self.config['admin_password']}

# Google OAuth (Optional)
GOOGLE_CLIENT_ID={self.config.get('google_client_id', '')}
GOOGLE_CLIENT_SECRET={self.config.get('google_client_secret', '')}

# ============================================================================
# TURN Server Configuration (for remote livestreaming)
# ============================================================================
TURN_SERVER_URL={self.config['turn_url']}
TURN_SERVER_USERNAME={self.config['turn_username']}
TURN_SERVER_PASSWORD={self.config['turn_password']}

# ============================================================================
# Database Configuration
# ============================================================================
DATABASE_PATH=./data/camera_events.db

# ============================================================================
# File Upload Configuration
# ============================================================================
UPLOAD_BASE_DIR=./data/uploads

# ============================================================================
# Logging Configuration
# ============================================================================
LOG_LEVEL=INFO
LOG_DIR=./logs

# ============================================================================
# Environment
# ============================================================================
ENVIRONMENT=production
DEBUG=false
"""

        with open(self.project_root / '.env', 'w') as f:
            f.write(env_content)

        print("✅ .env file created")

    def generate_emqx_config(self):
        """Generate EMQX configuration file"""
        print("\n⚙️  Generating EMQX configuration...")

        config_content = f"""## EMQX Production Configuration for VBC01 Cameras
## Compatible with AWS IoT SDK v2.1.1
## Generated: {datetime.now().isoformat()}

node.name = emqx@127.0.0.1
node.cookie = {secrets.token_hex(32)}
node.data_dir = data

## Cluster Configuration
cluster.discovery_strategy = manual

## Logging
log.console.enable = true
log.console.level = warning
log.file_handlers.default {{
  enable = true
  level = info
  file = "log/emqx.log"
  rotation.enable = true
  rotation.count = 10
  max_size = 50MB
}}

## MQTT SSL/TLS Listener (Port 8883)
listeners.ssl.default {{
  bind = "0.0.0.0:8883"
  ssl_options {{
    # Certificate files (absolute paths)
    cacertfile = "/etc/emqx/certs/ca.crt"
    certfile = "/etc/emqx/certs/broker.crt"
    keyfile = "/etc/emqx/certs/broker.key"

    # Mutual TLS (mTLS) - Require client certificates
    verify = verify_peer
    fail_if_no_peer_cert = true

    # TLS settings
    secure_renegotiate = true
    reuse_sessions = true
    honor_cipher_order = true

    # Support TLS 1.1, 1.2, 1.3 (AWS IoT SDK v2.1.1 uses TLS 1.2)
    versions = ["tlsv1.1", "tlsv1.2", "tlsv1.3"]
  }}

  # Connection limits
  max_connections = 1024000
  max_conn_rate = 1000
}}

## Authentication
# Allow anonymous connections (cameras authenticate via mTLS certificates)
authentication = []

## Authorization
# Allow all operations for camera platform
authorization {{
  no_match = allow
  deny_action = ignore
  cache {{
    enable = true
  }}
}}

## Dashboard Configuration
dashboard {{
  listeners.http {{
    bind = "0.0.0.0:18083"
    enable = true
  }}
  default_username = admin
  default_password = {secrets.token_urlsafe(16)}
}}

## Retained Messages
retainer {{
  enable = true
  backend {{
    type = built_in_database
    storage_type = ram
    max_retained_messages = 10000
  }}
}}

## Session Persistence
durable_sessions {{
  enable = false
}}
"""

        config_dir = self.project_root / 'config'
        with open(config_dir / 'emqx.conf', 'w') as f:
            f.write(config_content)

        print("✅ EMQX configuration created")

    def generate_deployment_guide(self):
        """Generate personalized deployment guide"""
        print("\n📖 Generating deployment guide...")

        guide_content = f"""# Deployment Guide

**Generated for:** {self.config['domain']}
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Your Configuration

- **Domain:** {self.config['domain']}
- **Local IP:** {self.config['local_ip']}
- **EMQX Endpoint:** {self.config['domain']}:8883
- **Dashboard URL:** https://{self.config['domain']}:5000
- **Admin Username:** {self.config['admin_username']}
- **Admin Password:** {self.config['admin_password']}

⚠️  **SAVE THIS PASSWORD SECURELY!**

## Installation Steps

### 1. Install EMQX

```bash
# Download EMQX 5.8.8
wget https://www.emqx.io/downloads/broker/5.8.8/emqx-5.8.8-ubuntu22.04-amd64.tar.gz

# Extract
tar -xzf emqx-5.8.8-ubuntu22.04-amd64.tar.gz

# Move to /opt
sudo mv emqx /opt/emqx

# Create symlink
sudo ln -s /opt/emqx/bin/emqx /usr/local/bin/emqx
```

### 2. Copy Certificates to EMQX

```bash
# Find EMQX directory
EMQX_DIR=$(emqx root_dir)

# Copy certificates
sudo cp certificates/ca.crt $EMQX_DIR/etc/certs/
sudo cp certificates/broker.crt $EMQX_DIR/etc/certs/
sudo cp certificates/broker.key $EMQX_DIR/etc/certs/

# Set permissions
sudo chmod 600 $EMQX_DIR/etc/certs/broker.key
sudo chmod 644 $EMQX_DIR/etc/certs/ca.crt
sudo chmod 644 $EMQX_DIR/etc/certs/broker.crt
```

### 3. Configure EMQX

```bash
# Copy generated config
sudo cp config/emqx.conf $EMQX_DIR/etc/emqx.conf

# Validate configuration
emqx check_config
```

### 4. Start EMQX

```bash
# Start EMQX
emqx start

# Check status
emqx ctl status

# View dashboard
# URL: http://{self.config['local_ip']}:18083
# Default credentials: admin / <password from emqx.conf>
```

### 5. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 6. Start Platform Services

```bash
# Start all services
./scripts/managed_start.sh start

# Check status
./scripts/managed_start.sh status
```

## Camera Setup

### Files to Upload to Camera

Located in `camera_files/` directory:
- `mqttCA.crt` - Root CA certificate
- `mqtt.pem` - Client certificate
- `mqtt.key` - Client private key

### FTP Upload Instructions

```bash
# Using FTP client
ftp <CAMERA_IP>
# Username: root
# Password: admin123

# Upload to /root/certs/
cd /root/certs
put camera_files/mqttCA.crt
put camera_files/mqtt.pem
put camera_files/mqtt.key
```

### Verify Checksums

On camera (via telnet):
```bash
telnet <CAMERA_IP>
# Login: root / admin123

md5sum /root/certs/mqttCA.crt
md5sum /root/certs/mqtt.pem
md5sum /root/certs/mqtt.key
```

Compare with `camera_files/checksums.txt`

### Reboot Camera

Camera will auto-connect to your EMQX broker!

## Testing

### 1. Test EMQX Connection

```bash
# Check clients
emqx ctl clients list

# Should see camera connected after reboot
```

### 2. Test Dashboard

```bash
# Open browser
https://{self.config['domain']}:5000

# Login with admin credentials
```

### 3. Test Notifications

Trigger motion detection on camera - you should receive Telegram notification!

## Troubleshooting

### EMQX Not Starting

```bash
# Check logs
tail -f $(emqx root_dir)/log/emqx.log

# Verify config
emqx check_config
```

### Camera Not Connecting

```bash
# Verify certificates on camera
ls -lh /root/certs/

# Check EMQX is listening
lsof -i :8883

# View EMQX logs for connection attempts
tail -f $(emqx root_dir)/log/emqx.log | grep clientid
```

### No Telegram Notifications

```bash
# Test Telegram token
curl https://api.telegram.org/bot{self.config['telegram_token']}/getMe

# Check processor logs
tail -f logs/mqtt_processor.log
```

## Next Steps

1. ✅ Platform installed and running
2. ✅ First camera connected
3. ➡️  Add more cameras (use `tools/add_camera.py`)
4. ➡️  Configure livestreaming
5. ➡️  Set up external access (port forwarding, HTTPS)

---

**Platform successfully deployed!** 🎉
"""

        deployment_dir = self.project_root / 'deployment'
        with open(deployment_dir / 'DEPLOYMENT_GUIDE.md', 'w') as f:
            f.write(guide_content)

        print("✅ Deployment guide created")

    def create_backup(self):
        """Create backup of configuration"""
        print("\n💾 Creating configuration backup...")

        backup_dir = self.project_root / 'backup'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save configuration JSON
        config_backup = backup_dir / f'setup_config_{timestamp}.json'
        with open(config_backup, 'w') as f:
            # Don't save sensitive data in plain text
            safe_config = self.config.copy()
            safe_config['telegram_token'] = '***REDACTED***'
            safe_config['turn_password'] = '***REDACTED***'
            safe_config['flask_secret'] = '***REDACTED***'
            safe_config['admin_password'] = '***REDACTED***'
            json.dump(safe_config, f, indent=2)

        print(f"✅ Configuration backed up to: {config_backup.name}")

    def print_summary(self):
        """Print setup summary"""
        print("\n" + "=" * 70)
        print("✅ SETUP COMPLETE!")
        print("=" * 70)
        print()
        print("📦 Generated Files:")
        print("  ✅ Certificates → certificates/")
        print("  ✅ Camera files → camera_files/")
        print("  ✅ Configuration → .env")
        print("  ✅ EMQX config → config/emqx.conf")
        print("  ✅ Deployment guide → deployment/DEPLOYMENT_GUIDE.md")
        print()
        print("📋 Next Steps:")
        print("  1. Install EMQX on your server")
        print("  2. Copy certificates to EMQX")
        print("  3. Configure EMQX with generated config")
        print("  4. Start platform services")
        print("  5. Upload camera files to cameras")
        print()
        print("📖 See deployment/DEPLOYMENT_GUIDE.md for detailed instructions")
        print()
        print("🔑 Admin Credentials:")
        print(f"  Username: {self.config['admin_username']}")
        print(f"  Password: {self.config['admin_password']}")
        print()
        print("  ⚠️  SAVE THIS PASSWORD!")
        print()
        print("=" * 70)

    def run(self):
        """Run the complete setup wizard"""
        try:
            self.print_banner()
            self.collect_inputs()

            if not self.validate_inputs():
                sys.exit(1)

            self.create_directories()

            if not self.generate_certificates():
                print("\n❌ Setup failed during certificate generation")
                sys.exit(1)

            self.create_camera_files()
            self.generate_env_file()
            self.generate_emqx_config()
            self.generate_deployment_guide()
            self.create_backup()

            self.print_summary()

        except KeyboardInterrupt:
            print("\n\n⚠️  Setup interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='VBC01 Camera Platform Setup Wizard')
    parser.add_argument('--domain', help='External domain name')
    parser.add_argument('--local-ip', help='Local server IP address')
    parser.add_argument('--telegram-token', help='Telegram bot token')
    parser.add_argument('--telegram-chat-id', help='Telegram chat ID')
    parser.add_argument('--turn-url', help='TURN server URL')
    parser.add_argument('--turn-username', help='TURN server username')
    parser.add_argument('--turn-password', help='TURN server password')

    args = parser.parse_args()

    setup = PlatformSetup()

    # If arguments provided, use them (non-interactive mode)
    if args.domain:
        setup.config['domain'] = args.domain
        setup.config['local_ip'] = args.local_ip
        setup.config['telegram_token'] = args.telegram_token
        setup.config['telegram_chat_id'] = args.telegram_chat_id
        setup.config['turn_url'] = args.turn_url
        setup.config['turn_username'] = args.turn_username
        setup.config['turn_password'] = args.turn_password
        setup.config['google_client_id'] = ''
        setup.config['google_client_secret'] = ''
        setup.config['flask_secret'] = secrets.token_hex(32)
        setup.config['admin_username'] = 'admin'
        setup.config['admin_password'] = secrets.token_urlsafe(16)

        setup.print_banner()
        if not setup.validate_inputs():
            sys.exit(1)

        setup.create_directories()
        if not setup.generate_certificates():
            sys.exit(1)
        setup.create_camera_files()
        setup.generate_env_file()
        setup.generate_emqx_config()
        setup.generate_deployment_guide()
        setup.create_backup()
        setup.print_summary()
    else:
        # Interactive mode
        setup.run()

if __name__ == '__main__':
    main()
