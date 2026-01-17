#!/usr/bin/env python3
"""
Recording Cleanup Tool
----------------------
Deletes old camera recordings and thumbnails from filesystem and database.

Usage:
    python3 tools/cleanup_old_recordings.py --days 28
    python3 tools/cleanup_old_recordings.py --days 7 --dry-run
    python3 tools/cleanup_old_recordings.py --days 14 --skip-confirmation
"""

import os
import sys
import sqlite3
import argparse
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config.settings import UPLOAD_BASE_DIR, DATABASE_PATH
except ImportError as e:
    print(f"❌ Failed to import settings: {e}")
    print("Using default paths...")
    UPLOAD_BASE_DIR = Path('./data/uploads')
    DATABASE_PATH = Path('./data/camera_events.db')


def format_size(bytes_size):
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def cleanup_recordings(days_to_keep, dry_run=False, skip_confirmation=False):
    """
    Delete recordings older than specified days

    Args:
        days_to_keep: Keep recordings from last N days
        dry_run: If True, only show what would be deleted
        skip_confirmation: If True, don't ask for confirmation
    """

    print("🗑️  Recording Cleanup Tool")
    print("=" * 60)
    print(f"Upload directory: {UPLOAD_BASE_DIR}")
    print(f"Database: {DATABASE_PATH}")
    print(f"Days to keep: {days_to_keep}")
    if dry_run:
        print("⚠️  DRY RUN MODE - No files will be deleted")
    print("=" * 60)
    print()

    # Calculate cutoff timestamp
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    cutoff_timestamp = int(cutoff_date.timestamp())
    print(f"📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   (Deleting recordings older than this)")
    print()

    # Check if paths exist
    if not UPLOAD_BASE_DIR.exists():
        print(f"⚠️  Upload directory does not exist: {UPLOAD_BASE_DIR}")
        return

    if not DATABASE_PATH.exists():
        print(f"⚠️  Database does not exist: {DATABASE_PATH}")
        return

    # Connect to database
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Statistics
    stats = {
        'events_to_delete': 0,
        'events_deleted': 0,
        'files_deleted': 0,
        'orphaned_db_entries': 0,
        'orphaned_files': 0,
        'space_freed': 0,
        'errors': 0
    }

    try:
        # Step 1: Find old events in database
        print("🔍 Finding old events in database...")
        cursor.execute("""
            SELECT id, event_id, camera_id, camera_name, activity_type,
                   start_timestamp, recording_filename, recording_path,
                   thumbnail_path, recording_size
            FROM activity_events
            WHERE start_timestamp < ?
            ORDER BY start_timestamp ASC
        """, (cutoff_timestamp,))

        old_events = cursor.fetchall()
        stats['events_to_delete'] = len(old_events)
        print(f"   Found {len(old_events)} old events")
        print()

        if len(old_events) == 0:
            print("✅ No old recordings to delete")
            conn.close()
            return

        # Show sample of what will be deleted
        print("📋 Sample of events to delete (first 5):")
        for i, event in enumerate(old_events[:5]):
            event_date = datetime.fromtimestamp(event['start_timestamp'])
            print(f"   [{i+1}] {event_date.strftime('%Y-%m-%d')} - "
                  f"{event['camera_name'] or event['camera_id']} - "
                  f"{event['activity_type']} - "
                  f"{event['recording_filename'] or 'no file'}")
        if len(old_events) > 5:
            print(f"   ... and {len(old_events) - 5} more")
        print()

        # Step 2: Calculate total space to be freed
        print("💾 Calculating space to be freed...")
        total_db_size = 0
        dirs_to_delete = []  # Event directories to delete entirely
        files_to_delete = []  # Individual files (legacy format)

        def get_dir_size(path):
            """Calculate total size of directory"""
            total = 0
            for item in path.rglob('*'):
                if item.is_file():
                    total += item.stat().st_size
            return total

        for event in old_events:
            # Check recording path (can be file or directory)
            if event['recording_path']:
                path = Path(event['recording_path'])
                if path.exists():
                    # If it's a directory, calculate size and mark entire directory for deletion
                    if path.is_dir():
                        size = get_dir_size(path)
                        total_db_size += size
                        dirs_to_delete.append((path, size))
                    # If it's a file, add it directly (legacy format)
                    elif path.is_file():
                        size = path.stat().st_size
                        total_db_size += size
                        files_to_delete.append((path, size))
                else:
                    stats['orphaned_db_entries'] += 1

            # Check thumbnail path (can be file or directory)
            # Note: thumbnail_path is usually inside recording_path directory,
            # so it will be deleted when we delete recording_path directory
            # Only handle it separately if it's standalone
            if event['thumbnail_path']:
                path = Path(event['thumbnail_path'])
                # Check if thumbnail_path is already covered by recording_path
                recording_path = Path(event['recording_path']) if event['recording_path'] else None
                is_inside_recording = (recording_path and
                                      recording_path.is_dir() and
                                      path.resolve().is_relative_to(recording_path.resolve()))

                if not is_inside_recording and path.exists():
                    # Standalone thumbnail - handle separately
                    if path.is_dir():
                        size = get_dir_size(path)
                        total_db_size += size
                        dirs_to_delete.append((path, size))
                    elif path.is_file():
                        size = path.stat().st_size
                        total_db_size += size
                        files_to_delete.append((path, size))

        print(f"   Event directories to delete: {len(dirs_to_delete)}")
        print(f"   Individual files to delete: {len(files_to_delete)}")
        print(f"   Space to free: {format_size(total_db_size)}")
        print(f"   Orphaned DB entries (file missing): {stats['orphaned_db_entries']}")
        print()

        # Step 3: Find orphaned event directories (not in database)
        print("🔍 Scanning for orphaned event directories (not in database)...")

        # Get all event_ids that exist in database (including future events)
        cursor.execute("SELECT event_id, recording_path FROM activity_events")
        db_event_ids = set()
        for row in cursor.fetchall():
            if row[0]:  # event_id
                db_event_ids.add(row[0])

        orphaned_dirs = []
        orphaned_files = []
        orphaned_size = 0

        if UPLOAD_BASE_DIR.exists():
            for camera_dir in UPLOAD_BASE_DIR.iterdir():
                if not camera_dir.is_dir():
                    continue

                for category_dir in camera_dir.iterdir():
                    if not category_dir.is_dir():
                        continue

                    # Scan for event_id subdirectories
                    for item in category_dir.iterdir():
                        # Skip system files
                        if item.name.startswith('.') or item.name in ['upload_log.txt', 'Thumbs.db']:
                            continue

                        # If it's a directory (event_id directory)
                        if item.is_dir():
                            event_id = item.name  # Directory name is the event_id

                            # Check if directory is older than cutoff using mtime
                            dir_mtime = item.stat().st_mtime
                            if dir_mtime >= cutoff_timestamp:
                                continue  # Directory is recent, skip

                            # Check if this event_id exists in database
                            if event_id not in db_event_ids:
                                # Orphaned event directory - not in database and old
                                size = get_dir_size(item)
                                orphaned_dirs.append((item, size))
                                orphaned_size += size
                                stats['orphaned_files'] += 1

                        # If it's a file directly in category_dir (legacy format)
                        elif item.is_file():
                            # Check if file is older than cutoff
                            file_mtime = item.stat().st_mtime
                            if file_mtime >= cutoff_timestamp:
                                continue

                            # Standalone orphaned file
                            size = item.stat().st_size
                            orphaned_files.append((item, size))
                            orphaned_size += size
                            stats['orphaned_files'] += 1

        print(f"   Orphaned event directories: {len(orphaned_dirs)}")
        print(f"   Orphaned individual files: {len(orphaned_files)}")
        print(f"   Orphaned content size: {format_size(orphaned_size)}")
        print()

        # Step 4: Summary
        total_dirs = len(dirs_to_delete) + len(orphaned_dirs)
        total_files = len(files_to_delete) + len(orphaned_files)
        total_size = total_db_size + orphaned_size

        print("=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Events to delete from DB: {stats['events_to_delete']}")
        print(f"Directories to delete: {total_dirs}")
        print(f"  - With DB records: {len(dirs_to_delete)}")
        print(f"  - Orphaned (no DB): {len(orphaned_dirs)}")
        print(f"Individual files to delete: {total_files}")
        print(f"  - With DB records: {len(files_to_delete)}")
        print(f"  - Orphaned (no DB): {len(orphaned_files)}")
        print(f"Total space to free: {format_size(total_size)}")
        print("=" * 60)
        print()

        if dry_run:
            print("✅ DRY RUN COMPLETE - No files were deleted")
            conn.close()
            return

        # Step 5: Confirmation
        if not skip_confirmation:
            response = input("⚠️  Proceed with deletion? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("❌ Cleanup cancelled")
                conn.close()
                return
            print()

        # Step 6: Delete files and directories
        print("🗑️  Deleting event directories and files...")

        # Delete event directories with DB records
        dirs_deleted = 0
        for dir_path, size in dirs_to_delete:
            try:
                shutil.rmtree(dir_path)
                dirs_deleted += 1
                stats['space_freed'] += size
            except Exception as e:
                print(f"   ⚠️  Failed to delete directory {dir_path}: {e}")
                stats['errors'] += 1

        # Delete orphaned event directories
        for dir_path, size in orphaned_dirs:
            try:
                shutil.rmtree(dir_path)
                dirs_deleted += 1
                stats['space_freed'] += size
            except Exception as e:
                print(f"   ⚠️  Failed to delete orphaned directory {dir_path}: {e}")
                stats['errors'] += 1

        # Delete individual files with DB records (legacy format)
        for file_path, size in files_to_delete:
            try:
                file_path.unlink()
                stats['files_deleted'] += 1
                stats['space_freed'] += size
            except Exception as e:
                print(f"   ⚠️  Failed to delete {file_path}: {e}")
                stats['errors'] += 1

        # Delete orphaned individual files (legacy format)
        for file_path, size in orphaned_files:
            try:
                file_path.unlink()
                stats['files_deleted'] += 1
                stats['space_freed'] += size
            except Exception as e:
                print(f"   ⚠️  Failed to delete {file_path}: {e}")
                stats['errors'] += 1

        print(f"   Deleted {dirs_deleted} directories")
        print(f"   Deleted {stats['files_deleted']} individual files")
        print()

        # Step 7: Delete database records
        print("🗑️  Deleting database records...")
        cursor.execute("""
            DELETE FROM activity_events
            WHERE start_timestamp < ?
        """, (cutoff_timestamp,))
        stats['events_deleted'] = cursor.rowcount
        conn.commit()
        print(f"   Deleted {stats['events_deleted']} events")
        print()

        # Step 8: Vacuum database
        print("🔧 Optimizing database...")
        cursor.execute("VACUUM")
        print("   Database optimized")
        print()

        # Final summary
        print("=" * 60)
        print("✅ CLEANUP COMPLETE")
        print("=" * 60)
        print(f"Events processed: {stats['events_deleted']}")
        print(f"Directories deleted: {dirs_deleted}")
        print(f"Individual files deleted: {stats['files_deleted']}")
        print(f"Orphaned DB entries: {stats['orphaned_db_entries']}")
        print(f"Space freed: {format_size(stats['space_freed'])}")
        if stats['errors'] > 0:
            print(f"⚠️  Errors: {stats['errors']}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete old camera recordings and thumbnails",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 tools/cleanup_old_recordings.py --days 28                    # Delete recordings older than 28 days
  python3 tools/cleanup_old_recordings.py --days 7 --dry-run           # Preview what would be deleted
  python3 tools/cleanup_old_recordings.py --days 14 --skip-confirmation # Skip confirmation prompt
        """
    )

    parser.add_argument(
        '--days',
        type=int,
        required=True,
        help='Keep recordings from last N days (delete older)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )

    parser.add_argument(
        '--skip-confirmation',
        action='store_true',
        help='Skip confirmation prompt (use with caution)'
    )

    args = parser.parse_args()

    if args.days < 1:
        print("❌ Error: --days must be at least 1")
        sys.exit(1)

    cleanup_recordings(
        days_to_keep=args.days,
        dry_run=args.dry_run,
        skip_confirmation=args.skip_confirmation
    )
