#!/usr/bin/env python3
"""
Database Manager for Camera Activity Events and Status
Handles SQLite database creation and management for the hybrid camera system
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

# Add config to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))
try:
    from settings import DATABASE_PATH
except ImportError as e:
    print(f"❌ Failed to import settings: {e}")
    # Fallback to default path if settings not available
    DATABASE_PATH = Path(os.path.dirname(os.path.dirname(__file__))) / 'data' / 'camera_events.db'

class CameraDatabaseManager:
    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_PATH

        # Directory creation removed - managed_start.sh creates directories before starting services
        # This prevents root ownership issues when config server runs with sudo

        print(f"🗃️ Database: {self.db_path}")
        self.init_database()

    def init_database(self):
        """Initialize database with required tables"""

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Activity Events Table - for motion detection events with recordings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    camera_id TEXT NOT NULL,
                    camera_name TEXT,
                    activity_type TEXT NOT NULL,
                    start_timestamp INTEGER NOT NULL,
                    end_timestamp INTEGER,
                    duration_seconds INTEGER,
                    confidence REAL,
                    recording_filename TEXT,
                    recording_path TEXT,
                    recording_size INTEGER,
                    thumbnail_path TEXT,
                    upload_status TEXT DEFAULT 'pending',
                    processed BOOLEAN DEFAULT FALSE,
                    slack_ts TEXT,
                    slack_channel TEXT,
                    slack_notified BOOLEAN DEFAULT FALSE,
                    telegram_msg_id TEXT,
                    telegram_notified BOOLEAN DEFAULT FALSE,
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    updated_at INTEGER DEFAULT (strftime('%s','now'))
                )
            ''')

            # Camera Status Events Table - for connection, status, heartbeat events
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS camera_status_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    camera_name TEXT,
                    event_type TEXT NOT NULL,
                    status TEXT,
                    timestamp INTEGER NOT NULL,
                    client_id TEXT,
                    ip_address TEXT,
                    firmware_version TEXT,
                    battery_level INTEGER,
                    temperature REAL,
                    uptime INTEGER,
                    raw_payload TEXT,
                    created_at INTEGER DEFAULT (strftime('%s','now'))
                )
            ''')

            # Camera Registry Table - for tracking known cameras
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cameras (
                    camera_id TEXT PRIMARY KEY,
                    camera_name TEXT,
                    ip_address TEXT,
                    location TEXT,
                    last_seen INTEGER,
                    firmware_version TEXT,
                    status TEXT DEFAULT 'unknown',
                    connection_status TEXT DEFAULT 'disconnected',
                    connection_timestamp INTEGER,
                    rtsp_url TEXT,
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    updated_at INTEGER DEFAULT (strftime('%s','now'))
                )
            ''')

            # Camera State Table - for storing camera settings that need to be restored
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS camera_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    setting_name TEXT NOT NULL,
                    setting_value TEXT,
                    setting_type TEXT DEFAULT 'string',
                    timestamp INTEGER DEFAULT (strftime('%s','now')),
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    updated_at INTEGER DEFAULT (strftime('%s','now')),
                    UNIQUE(camera_id, setting_name)
                )
            ''')

            # File Uploads Table - for tracking uploaded recordings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    event_id TEXT,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    file_type TEXT,
                    upload_timestamp INTEGER,
                    s3_url TEXT,
                    local_path TEXT,
                    created_at INTEGER DEFAULT (strftime('%s','now'))
                )
            ''')

            # Create indexes for better query performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_camera_id ON activity_events(camera_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_events(start_timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_event_id ON activity_events(event_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_events(activity_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_camera_id ON camera_status_events(camera_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_timestamp ON camera_status_events(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_event_type ON camera_status_events(event_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_state_camera_id ON camera_state(camera_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_state_setting_name ON camera_state(setting_name)')

            conn.commit()
            print("✅ Database initialized with all required tables")

    def add_activity_start_event(self, event_id, camera_id, activity_type, timestamp, confidence=None, camera_name=None):
        """Add activity start event"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO activity_events
                (event_id, camera_id, camera_name, activity_type, start_timestamp, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))
            ''', (event_id, camera_id, camera_name, activity_type, timestamp, confidence))
            conn.commit()
            print(f"📍 Activity START: {activity_type} on camera {camera_id} (event {event_id})")

    def add_activity_end_event(self, event_id, timestamp):
        """Complete activity event with end time and duration"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get the start event
            cursor.execute('SELECT start_timestamp FROM activity_events WHERE event_id = ?', (event_id,))
            result = cursor.fetchone()

            if result:
                start_timestamp = result[0]
                duration = timestamp - start_timestamp

                cursor.execute('''
                    UPDATE activity_events
                    SET end_timestamp = ?, duration_seconds = ?, updated_at = strftime('%s','now')
                    WHERE event_id = ?
                ''', (timestamp, duration, event_id))
                conn.commit()
                print(f"📍 Activity END: Event {event_id} duration: {duration} seconds")
            else:
                print(f"⚠️ No start event found for event_id: {event_id}")

    def add_status_event(self, camera_id, event_type, status, timestamp, **kwargs):
        """Add camera status event (connection, heartbeat, etc.)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO camera_status_events
                (camera_id, camera_name, event_type, status, timestamp, client_id, ip_address,
                 firmware_version, battery_level, temperature, uptime, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                camera_id,
                kwargs.get('camera_name'),
                event_type,
                status,
                timestamp,
                kwargs.get('client_id'),
                kwargs.get('ip_address'),
                kwargs.get('firmware_version'),
                kwargs.get('battery_level'),
                kwargs.get('temperature'),
                kwargs.get('uptime'),
                kwargs.get('raw_payload')
            ))
            conn.commit()
            print(f"📡 Status Event: {event_type} - {status} for camera {camera_id}")

    def update_camera_info(self, camera_id, **kwargs):
        """Update or insert camera information - only updates provided fields"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Build UPDATE clause dynamically from kwargs
            update_fields = []
            values = []

            for key, value in kwargs.items():
                update_fields.append(f"{key} = ?")
                values.append(value)

            # Always update updated_at timestamp
            update_fields.append("updated_at = strftime('%s','now')")

            if update_fields:
                values.append(camera_id)  # For WHERE clause

                # Try UPDATE first
                update_sql = f"UPDATE cameras SET {', '.join(update_fields)} WHERE camera_id = ?"
                cursor.execute(update_sql, values)

                # If no rows updated, INSERT new camera with defaults
                if cursor.rowcount == 0:
                    cursor.execute('''
                        INSERT INTO cameras
                        (camera_id, camera_name, ip_address, location, last_seen, firmware_version,
                         status, connection_status, connection_timestamp, rtsp_url, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
                    ''', (
                        camera_id,
                        kwargs.get('camera_name'),
                        kwargs.get('ip_address'),
                        kwargs.get('location'),
                        kwargs.get('last_seen'),
                        kwargs.get('firmware_version'),
                        kwargs.get('status', 'unknown'),
                        kwargs.get('connection_status', 'disconnected'),
                        kwargs.get('connection_timestamp'),
                        kwargs.get('rtsp_url')
                    ))

            conn.commit()

    def get_recent_activity_events(self, camera_id=None, activity_types=None, limit=50, require_end_timestamp=True):
        """Get recent activity events with recordings

        Args:
            camera_id: Filter by camera ID (optional)
            activity_types: List of activity types to filter (optional)
            limit: Maximum number of events to return
            require_end_timestamp: Only return events with end_timestamp (default: True)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Build WHERE clause dynamically
            where_clauses = []
            if require_end_timestamp:
                where_clauses.append("end_timestamp IS NOT NULL")
            params = []

            # Camera filter
            if camera_id:
                where_clauses.append("camera_id = ?")
                params.append(camera_id)

            # Activity type filter (using IN clause for efficiency)
            if activity_types:
                placeholders = ','.join('?' * len(activity_types))
                where_clauses.append(f"activity_type IN ({placeholders})")
                params.extend(activity_types)

            where_clause = " AND ".join(where_clauses) if where_clauses else ""
            params.append(limit)

            query = f'''
                SELECT event_id, camera_id, camera_name, activity_type,
                       start_timestamp, end_timestamp, duration_seconds, confidence,
                       recording_filename, recording_path, thumbnail_path, upload_status
                FROM activity_events
                {"WHERE " + where_clause if where_clause else ""}
                ORDER BY start_timestamp DESC
                LIMIT ?
            '''
            cursor.execute(query, params)

            events = []
            for row in cursor.fetchall():
                events.append({
                    'event_id': row[0],
                    'camera_id': row[1],
                    'camera_name': row[2],
                    'activity_type': row[3],
                    'start_timestamp': row[4],
                    'end_timestamp': row[5],
                    'duration_seconds': row[6],
                    'confidence': row[7],
                    'recording_filename': row[8],
                    'recording_path': row[9],
                    'thumbnail_path': row[10],
                    'upload_status': row[11],
                    'start_time': datetime.fromtimestamp(row[4]).strftime('%Y-%m-%d %H:%M:%S'),
                    'end_time': datetime.fromtimestamp(row[5]).strftime('%Y-%m-%d %H:%M:%S') if row[5] else None
                })
            return events

    def get_camera_status(self, camera_id=None):
        """Get current status of cameras"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if camera_id:
                cursor.execute('''
                    SELECT camera_id, camera_name, ip_address, status, rtsp_url, last_seen, firmware_version,
                           connection_status, connection_timestamp
                    FROM cameras WHERE camera_id = ?
                ''', (camera_id,))
            else:
                cursor.execute('''
                    SELECT camera_id, camera_name, ip_address, status, rtsp_url, last_seen, firmware_version,
                           connection_status, connection_timestamp
                    FROM cameras ORDER BY camera_name
                ''')

            cameras = []
            for row in cursor.fetchall():
                cameras.append({
                    'camera_id': row[0],
                    'camera_name': row[1] or f"Camera {row[0][-8:]}",
                    'ip_address': row[2],
                    'status': row[3],
                    'rtsp_url': row[4],
                    'last_seen': row[5],
                    'firmware_version': row[6],
                    'connection_status': row[7],
                    'connection_timestamp': row[8],
                    'last_seen_str': datetime.fromtimestamp(row[5]).strftime('%Y-%m-%d %H:%M:%S') if row[5] else 'Never',
                    'connection_status_str': datetime.fromtimestamp(row[8]).strftime('%Y-%m-%d %H:%M:%S') if row[8] else 'Never'
                })
            return cameras

    def add_file_upload(self, camera_id, filename, file_path, event_id=None, **kwargs):
        """Track uploaded file"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO file_uploads
                (camera_id, event_id, filename, file_path, file_size, file_type, upload_timestamp, s3_url, local_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                camera_id, event_id, filename, file_path,
                kwargs.get('file_size'),
                kwargs.get('file_type'),
                kwargs.get('upload_timestamp', int(datetime.now().timestamp())),
                kwargs.get('s3_url'),
                kwargs.get('local_path')
            ))

            # Update activity event with recording info if event_id provided
            if event_id:
                cursor.execute('''
                    UPDATE activity_events
                    SET recording_filename = ?, recording_path = ?, recording_size = ?
                    WHERE event_id = ?
                ''', (filename, file_path, kwargs.get('file_size'), event_id))

            conn.commit()
            print(f"📁 File upload tracked: {filename} for camera {camera_id}")

    def set_camera_state(self, camera_id, setting_name, setting_value, setting_type='string'):
        """Store or update camera state setting"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO camera_state
                (camera_id, setting_name, setting_value, setting_type, timestamp, updated_at)
                VALUES (?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ''', (camera_id, setting_name, setting_value, setting_type))
            conn.commit()
            print(f"💾 Camera state updated: {camera_id} - {setting_name} = {setting_value}")

    def get_camera_state(self, camera_id, setting_name=None):
        """Get camera state settings"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if setting_name:
                cursor.execute('''
                    SELECT setting_name, setting_value, setting_type, timestamp
                    FROM camera_state WHERE camera_id = ? AND setting_name = ?
                    ORDER BY timestamp DESC LIMIT 1
                ''', (camera_id, setting_name))
                result = cursor.fetchone()
                if result:
                    return {
                        'setting_name': result[0],
                        'setting_value': result[1],
                        'setting_type': result[2],
                        'timestamp': result[3]
                    }
                return None
            else:
                cursor.execute('''
                    SELECT setting_name, setting_value, setting_type, timestamp
                    FROM camera_state WHERE camera_id = ?
                    ORDER BY setting_name
                ''', (camera_id,))

                states = {}
                for row in cursor.fetchall():
                    states[row[0]] = {
                        'value': row[1],
                        'type': row[2],
                        'timestamp': row[3]
                    }
                return states

    def update_connection_status(self, camera_id, connection_status, camera_name=None):
        """Update camera connection status"""
        timestamp = int(datetime.now().timestamp())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get current camera data to preserve existing values
            cursor.execute('''
                SELECT camera_name, ip_address, location, last_seen, firmware_version, status, rtsp_url
                FROM cameras WHERE camera_id = ?
            ''', (camera_id,))

            result = cursor.fetchone()
            if result:
                # Update existing camera
                cursor.execute('''
                    UPDATE cameras SET
                    camera_name = COALESCE(?, camera_name),
                    connection_status = ?,
                    connection_timestamp = ?,
                    updated_at = strftime('%s','now')
                    WHERE camera_id = ?
                ''', (camera_name, connection_status, timestamp, camera_id))
            else:
                # Insert new camera
                cursor.execute('''
                    INSERT INTO cameras
                    (camera_id, camera_name, connection_status, connection_timestamp, created_at, updated_at)
                    VALUES (?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
                ''', (camera_id, camera_name or f"Camera {camera_id[-8:]}", connection_status, timestamp))

            conn.commit()
            print(f"🔌 Connection status updated: {camera_id} - {connection_status}")

    def get_event_by_id(self, event_id):
        """Get activity event by event_id"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT event_id, camera_id, camera_name, activity_type,
                       start_timestamp, end_timestamp, duration_seconds, confidence,
                       recording_filename, recording_path, recording_size, thumbnail_path, upload_status,
                       slack_ts, slack_notified
                FROM activity_events
                WHERE event_id = ?
            ''', (event_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'event_id': row[0],
                    'camera_id': row[1],
                    'camera_name': row[2],
                    'activity_type': row[3],
                    'start_timestamp': row[4],
                    'end_timestamp': row[5],
                    'duration_seconds': row[6],
                    'confidence': row[7],
                    'recording_filename': row[8],
                    'recording_path': row[9],
                    'recording_size': row[10],
                    'thumbnail_path': row[11],
                    'upload_status': row[12],
                    'slack_ts': row[13],
                    'slack_notified': row[14]
                }
            return None

    def update_activity_event(self, event_id, **kwargs):
        """Update activity event with additional fields (recording path, thumbnail, etc.)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Build dynamic UPDATE query based on provided kwargs
            valid_fields = [
                'camera_name', 'activity_type', 'start_timestamp', 'confidence',
                'end_timestamp', 'duration_seconds',
                'recording_filename', 'recording_path', 'recording_size',
                'thumbnail_path', 'upload_status', 'processed',
                'slack_ts', 'slack_channel', 'slack_notified',
                'telegram_msg_id', 'telegram_notified'
            ]

            update_fields = []
            values = []

            for field in valid_fields:
                if field in kwargs:
                    update_fields.append(f"{field} = ?")
                    values.append(kwargs[field])

            if not update_fields:
                print(f"⚠️ No valid fields to update for event {event_id}")
                return

            # Add updated_at timestamp
            update_fields.append("updated_at = strftime('%s','now')")

            # Build and execute query
            query = f"UPDATE activity_events SET {', '.join(update_fields)} WHERE event_id = ?"
            values.append(event_id)

            cursor.execute(query, values)
            conn.commit()

            if cursor.rowcount > 0:
                print(f"📝 Updated activity event {event_id}: {', '.join(kwargs.keys())}")
            else:
                print(f"⚠️ No event found with event_id: {event_id}")

    def get_database_stats(self):
        """Get database statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            stats = {}

            # Count activity events
            cursor.execute('SELECT COUNT(*) FROM activity_events')
            stats['activity_events'] = cursor.fetchone()[0]

            # Count status events
            cursor.execute('SELECT COUNT(*) FROM camera_status_events')
            stats['status_events'] = cursor.fetchone()[0]

            # Count cameras
            cursor.execute('SELECT COUNT(*) FROM cameras')
            stats['cameras'] = cursor.fetchone()[0]

            # Count uploads
            cursor.execute('SELECT COUNT(*) FROM file_uploads')
            stats['file_uploads'] = cursor.fetchone()[0]

            # Recent activity
            cursor.execute('SELECT COUNT(*) FROM activity_events WHERE start_timestamp > ?',
                         (int(datetime.now().timestamp()) - 86400,))
            stats['activity_events_24h'] = cursor.fetchone()[0]

            return stats

def main():
    """Initialize database for testing"""
    print("🗃️ Camera Database Manager")
    print("=" * 50)

    db = CameraDatabaseManager()
    stats = db.get_database_stats()

    print(f"\n📊 Database Statistics:")
    print(f"   Activity Events: {stats['activity_events']}")
    print(f"   Status Events: {stats['status_events']}")
    print(f"   Cameras: {stats['cameras']}")
    print(f"   File Uploads: {stats['file_uploads']}")
    print(f"   Activity (24h): {stats['activity_events_24h']}")

    print(f"\n✅ Database ready for camera event processing")

if __name__ == "__main__":
    main()