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
        files_to_delete = []

        for event in old_events:
            # Check recording path (can be file or directory)
            if event['recording_path']:
                path = Path(event['recording_path'])
                if path.exists():
                    # If it's a directory, scan all files inside
                    if path.is_dir():
                        for file_path in path.rglob('*'):
                            if file_path.is_file():
                                # Skip system files
                                if file_path.name.startswith('.') or file_path.name in ['aes.key']:
                                    continue
                                size = file_path.stat().st_size
                                total_db_size += size
                                files_to_delete.append((file_path, size))
                    # If it's a file, add it directly
                    elif path.is_file():
                        size = path.stat().st_size
                        total_db_size += size
                        files_to_delete.append((path, size))
                else:
                    stats['orphaned_db_entries'] += 1

            # Check thumbnail path (can be file or directory)
            if event['thumbnail_path']:
                path = Path(event['thumbnail_path'])
                if path.exists():
                    # If it's a directory, scan all files inside
                    if path.is_dir():
                        for file_path in path.rglob('*'):
                            if file_path.is_file():
                                # Skip system files
                                if file_path.name.startswith('.'):
                                    continue
                                size = file_path.stat().st_size
                                total_db_size += size
                                files_to_delete.append((file_path, size))
                    # If it's a file, add it directly
                    elif path.is_file():
                        size = path.stat().st_size
                        total_db_size += size
                        files_to_delete.append((path, size))

        print(f"   Files to delete: {len(files_to_delete)}")
        print(f"   Space to free: {format_size(total_db_size)}")
        print(f"   Orphaned DB entries (file missing): {stats['orphaned_db_entries']}")
        print()

        # Step 3: Find orphaned files (files not in database)
        print("🔍 Scanning for orphaned files (not in database)...")
        db_files = set()
        db_dirs = set()
        cursor.execute("SELECT recording_path, thumbnail_path FROM activity_events")
        for row in cursor.fetchall():
            if row[0]:
                path = Path(row[0]).resolve()
                # If it's a directory in DB, track it so we don't mark its contents as orphaned
                if path.is_dir():
                    db_dirs.add(str(path))
                else:
                    db_files.add(str(path))
            if row[1]:
                path = Path(row[1]).resolve()
                if path.is_dir():
                    db_dirs.add(str(path))
                else:
                    db_files.add(str(path))

        orphaned_files = []
        orphaned_size = 0

        if UPLOAD_BASE_DIR.exists():
            for camera_dir in UPLOAD_BASE_DIR.iterdir():
                if not camera_dir.is_dir():
                    continue

                for category_dir in camera_dir.iterdir():
                    if not category_dir.is_dir():
                        continue

                    # Files can be directly in category_dir OR in event_id subdirectories
                    for item in category_dir.iterdir():
                        # Skip system files
                        if item.name.startswith('.') or item.name in ['upload_log.txt', 'Thumbs.db']:
                            continue

                        files_to_check = []

                        # If it's a directory (event_id), scan files inside it
                        if item.is_dir():
                            for file_path in item.iterdir():
                                if file_path.is_file():
                                    files_to_check.append(file_path)
                        # If it's a file directly in category_dir
                        elif item.is_file():
                            files_to_check.append(item)

                        # Check all collected files
                        for file_path in files_to_check:
                            # Skip system files
                            if file_path.name.startswith('.') or file_path.name in ['upload_log.txt', 'aes.key']:
                                continue

                            # Check if file is older than cutoff
                            file_mtime = file_path.stat().st_mtime
                            if file_mtime >= cutoff_timestamp:
                                continue

                            # Check if file is in database or under a DB directory
                            file_path_str = str(file_path.resolve())
                            is_in_db = file_path_str in db_files

                            # Check if file is under any directory tracked in DB
                            if not is_in_db:
                                for db_dir in db_dirs:
                                    if file_path_str.startswith(db_dir + '/') or file_path_str.startswith(db_dir + '\\'):
                                        is_in_db = True
                                        break

                            if not is_in_db:
                                size = file_path.stat().st_size
                                orphaned_files.append((file_path, size))
                                orphaned_size += size
                                stats['orphaned_files'] += 1

        print(f"   Orphaned files found: {len(orphaned_files)}")
        print(f"   Orphaned files size: {format_size(orphaned_size)}")
        print()

        # Step 4: Summary
        total_files = len(files_to_delete) + len(orphaned_files)
        total_size = total_db_size + orphaned_size

        print("=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Events to delete from DB: {stats['events_to_delete']}")
        print(f"Files to delete: {total_files}")
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

        # Step 6: Delete files
        print("🗑️  Deleting files...")

        # Delete files with DB records
        for file_path, size in files_to_delete:
            try:
                file_path.unlink()
                stats['files_deleted'] += 1
                stats['space_freed'] += size
            except Exception as e:
                print(f"   ⚠️  Failed to delete {file_path}: {e}")
                stats['errors'] += 1

        # Delete orphaned files
        for file_path, size in orphaned_files:
            try:
                file_path.unlink()
                stats['files_deleted'] += 1
                stats['space_freed'] += size
            except Exception as e:
                print(f"   ⚠️  Failed to delete {file_path}: {e}")
                stats['errors'] += 1

        print(f"   Deleted {stats['files_deleted']} files")
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
        print(f"Files deleted: {stats['files_deleted']}")
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
