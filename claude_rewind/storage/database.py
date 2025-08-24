"""SQLite database operations for snapshot metadata storage."""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from contextlib import contextmanager

from ..core.models import SnapshotMetadata, FileChange, ChangeType


logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class DatabaseManager:
    """Manages SQLite database operations for snapshot metadata."""
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Path):
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_database_exists()
    
    def _ensure_database_exists(self) -> None:
        """Create database and tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            self._create_tables(conn)
            self._set_schema_version(conn)
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise DatabaseError(f"Database operation failed: {e}")
        finally:
            if conn:
                conn.close()
    
    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create database tables with proper schema."""
        cursor = conn.cursor()
        
        # Create snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                prompt_context TEXT,
                files_affected INTEGER NOT NULL DEFAULT 0,
                total_size INTEGER NOT NULL DEFAULT 0,
                compression_ratio REAL DEFAULT 1.0,
                parent_snapshot TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (parent_snapshot) REFERENCES snapshots(id)
            )
        """)
        
        # Create file_changes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                content_hash TEXT,
                size_bytes INTEGER DEFAULT 0,
                before_hash TEXT,
                after_hash TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp 
            ON snapshots(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_changes_snapshot 
            ON file_changes(snapshot_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_changes_path 
            ON file_changes(file_path)
        """)
        
        # Create bookmarks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
                UNIQUE(snapshot_id)
            )
        """)
        
        # Create index for bookmark lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookmarks_snapshot 
            ON bookmarks(snapshot_id)
        """)
        
        # Create schema_info table for migrations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_info (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL
            )
        """)
        
        conn.commit()
    
    def _set_schema_version(self, conn: sqlite3.Connection) -> None:
        """Set current schema version."""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO schema_info (version, applied_at)
            VALUES (?, ?)
        """, (self.SCHEMA_VERSION, int(datetime.now().timestamp())))
        conn.commit()
    
    def get_schema_version(self) -> int:
        """Get current schema version."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM schema_info ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else 0
    
    def create_snapshot(self, metadata: SnapshotMetadata) -> None:
        """Create a new snapshot record.
        
        Args:
            metadata: Snapshot metadata to store
            
        Raises:
            DatabaseError: If snapshot creation fails
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            now = int(datetime.now().timestamp())
            cursor.execute("""
                INSERT INTO snapshots (
                    id, timestamp, action_type, prompt_context,
                    files_affected, total_size, compression_ratio,
                    parent_snapshot, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.id,
                int(metadata.timestamp.timestamp()),
                metadata.action_type,
                metadata.prompt_context,
                len(metadata.files_affected),
                metadata.total_size,
                metadata.compression_ratio,
                metadata.parent_snapshot,
                now
            ))
            
            conn.commit()
            logger.debug(f"Created snapshot record: {metadata.id}")
    
    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """Retrieve snapshot metadata by ID.
        
        Args:
            snapshot_id: Unique snapshot identifier
            
        Returns:
            SnapshotMetadata if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, action_type, prompt_context,
                       files_affected, total_size, compression_ratio,
                       parent_snapshot
                FROM snapshots WHERE id = ?
            """, (snapshot_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return SnapshotMetadata(
                id=row['id'],
                timestamp=datetime.fromtimestamp(row['timestamp']),
                action_type=row['action_type'],
                prompt_context=row['prompt_context'],
                files_affected=[],  # Will be populated by file_changes
                total_size=row['total_size'],
                compression_ratio=row['compression_ratio'],
                parent_snapshot=row['parent_snapshot']
            )
    
    def list_snapshots(self, limit: Optional[int] = None, 
                      offset: int = 0) -> List[SnapshotMetadata]:
        """List all snapshots ordered by timestamp.
        
        Args:
            limit: Maximum number of snapshots to return
            offset: Number of snapshots to skip
            
        Returns:
            List of snapshot metadata
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT id, timestamp, action_type, prompt_context,
                       files_affected, total_size, compression_ratio,
                       parent_snapshot
                FROM snapshots 
                ORDER BY timestamp DESC
            """
            
            params = []
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
                if offset > 0:
                    query += " OFFSET ?"
                    params.append(offset)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                SnapshotMetadata(
                    id=row['id'],
                    timestamp=datetime.fromtimestamp(row['timestamp']),
                    action_type=row['action_type'],
                    prompt_context=row['prompt_context'],
                    files_affected=[],
                    total_size=row['total_size'],
                    compression_ratio=row['compression_ratio'],
                    parent_snapshot=row['parent_snapshot']
                )
                for row in rows
            ]
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete snapshot and associated file changes.
        
        Args:
            snapshot_id: Unique snapshot identifier
            
        Returns:
            True if snapshot was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete snapshot (file_changes will be deleted by CASCADE)
            cursor.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            
            if deleted:
                logger.debug(f"Deleted snapshot: {snapshot_id}")
            
            return deleted
    
    def add_file_change(self, snapshot_id: str, file_change: FileChange) -> None:
        """Add file change record to snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            file_change: File change information
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            now = int(datetime.now().timestamp())
            cursor.execute("""
                INSERT INTO file_changes (
                    snapshot_id, file_path, change_type, content_hash,
                    size_bytes, before_hash, after_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_id,
                str(file_change.path),
                file_change.change_type.value,
                file_change.after_hash,
                0,  # Size will be calculated separately
                file_change.before_hash,
                file_change.after_hash,
                now
            ))
            
            conn.commit()
    
    def get_file_changes(self, snapshot_id: str) -> List[FileChange]:
        """Get all file changes for a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            List of file changes
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path, change_type, content_hash, 
                       before_hash, after_hash
                FROM file_changes 
                WHERE snapshot_id = ?
                ORDER BY file_path
            """, (snapshot_id,))
            
            rows = cursor.fetchall()
            
            return [
                FileChange(
                    path=Path(row['file_path']),
                    change_type=ChangeType(row['change_type']),
                    before_hash=row['before_hash'],
                    after_hash=row['after_hash'],
                    line_changes=[]  # Will be populated when needed
                )
                for row in rows
            ]
    
    def cleanup_old_snapshots(self, keep_count: int) -> int:
        """Remove old snapshots keeping only the most recent ones.
        
        Args:
            keep_count: Number of recent snapshots to keep
            
        Returns:
            Number of snapshots deleted
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get IDs of snapshots to delete
            cursor.execute("""
                SELECT id FROM snapshots 
                ORDER BY timestamp DESC 
                LIMIT -1 OFFSET ?
            """, (keep_count,))
            
            old_snapshots = [row[0] for row in cursor.fetchall()]
            
            if not old_snapshots:
                return 0
            
            # Delete old snapshots
            placeholders = ','.join('?' * len(old_snapshots))
            cursor.execute(f"""
                DELETE FROM snapshots 
                WHERE id IN ({placeholders})
            """, old_snapshots)
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            logger.info(f"Cleaned up {deleted_count} old snapshots")
            return deleted_count
    
    def add_bookmark(self, snapshot_id: str, name: str, description: Optional[str] = None) -> bool:
        """Add a bookmark to a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            name: Bookmark name
            description: Optional bookmark description
            
        Returns:
            True if bookmark was added successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            now = int(datetime.now().timestamp())
            
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO bookmarks (snapshot_id, name, description, created_at)
                    VALUES (?, ?, ?, ?)
                """, (snapshot_id, name, description, now))
                
                conn.commit()
                logger.debug(f"Added bookmark '{name}' to snapshot {snapshot_id}")
                return True
                
            except sqlite3.Error as e:
                logger.error(f"Error adding bookmark: {e}")
                return False
    
    def remove_bookmark(self, snapshot_id: str) -> bool:
        """Remove bookmark from a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            True if bookmark was removed successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM bookmarks WHERE snapshot_id = ?", (snapshot_id,))
            removed = cursor.rowcount > 0
            
            conn.commit()
            
            if removed:
                logger.debug(f"Removed bookmark from snapshot {snapshot_id}")
            
            return removed
    
    def get_bookmark(self, snapshot_id: str) -> Optional[Tuple[str, Optional[str]]]:
        """Get bookmark for a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Tuple of (name, description) if bookmark exists, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, description FROM bookmarks WHERE snapshot_id = ?
            """, (snapshot_id,))
            
            row = cursor.fetchone()
            return (row['name'], row['description']) if row else None
    
    def list_bookmarks(self) -> List[Tuple[str, str, Optional[str], datetime]]:
        """List all bookmarks.
        
        Returns:
            List of tuples: (snapshot_id, name, description, created_at)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT snapshot_id, name, description, created_at 
                FROM bookmarks 
                ORDER BY created_at DESC
            """)
            
            rows = cursor.fetchall()
            
            return [
                (row['snapshot_id'], row['name'], row['description'], 
                 datetime.fromtimestamp(row['created_at']))
                for row in rows
            ]
    
    def search_snapshots_by_metadata(self, query: str) -> List[SnapshotMetadata]:
        """Search snapshots by metadata content.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching snapshot metadata
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Search in snapshot metadata and bookmark names/descriptions
            search_pattern = f"%{query}%"
            
            cursor.execute("""
                SELECT DISTINCT s.id, s.timestamp, s.action_type, s.prompt_context,
                       s.files_affected, s.total_size, s.compression_ratio,
                       s.parent_snapshot
                FROM snapshots s
                LEFT JOIN bookmarks b ON s.id = b.snapshot_id
                WHERE s.prompt_context LIKE ? COLLATE NOCASE
                   OR s.action_type LIKE ? COLLATE NOCASE
                   OR s.id LIKE ? COLLATE NOCASE
                   OR b.name LIKE ? COLLATE NOCASE
                   OR b.description LIKE ? COLLATE NOCASE
                ORDER BY s.timestamp DESC
            """, (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))
            
            rows = cursor.fetchall()
            
            return [
                SnapshotMetadata(
                    id=row['id'],
                    timestamp=datetime.fromtimestamp(row['timestamp']),
                    action_type=row['action_type'],
                    prompt_context=row['prompt_context'],
                    files_affected=[],  # Will be populated separately if needed
                    total_size=row['total_size'],
                    compression_ratio=row['compression_ratio'],
                    parent_snapshot=row['parent_snapshot']
                )
                for row in rows
            ]
    
    def get_snapshots_with_bookmarks(self, limit: Optional[int] = None, 
                                   offset: int = 0) -> List[Tuple[SnapshotMetadata, Optional[Tuple[str, Optional[str]]]]]:
        """Get snapshots with their bookmark information.
        
        Args:
            limit: Maximum number of snapshots to return
            offset: Number of snapshots to skip
            
        Returns:
            List of tuples: (snapshot_metadata, bookmark_info)
            bookmark_info is (name, description) tuple or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT s.id, s.timestamp, s.action_type, s.prompt_context,
                       s.files_affected, s.total_size, s.compression_ratio,
                       s.parent_snapshot, b.name as bookmark_name, b.description as bookmark_desc
                FROM snapshots s
                LEFT JOIN bookmarks b ON s.id = b.snapshot_id
                ORDER BY s.timestamp DESC
            """
            
            params = []
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
                if offset > 0:
                    query += " OFFSET ?"
                    params.append(offset)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                snapshot = SnapshotMetadata(
                    id=row['id'],
                    timestamp=datetime.fromtimestamp(row['timestamp']),
                    action_type=row['action_type'],
                    prompt_context=row['prompt_context'],
                    files_affected=[],
                    total_size=row['total_size'],
                    compression_ratio=row['compression_ratio'],
                    parent_snapshot=row['parent_snapshot']
                )
                
                bookmark_info = None
                if row['bookmark_name']:
                    bookmark_info = (row['bookmark_name'], row['bookmark_desc'])
                
                result.append((snapshot, bookmark_info))
            
            return result
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get database storage statistics.
        
        Returns:
            Dictionary with storage statistics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get snapshot count
            cursor.execute("SELECT COUNT(*) FROM snapshots")
            snapshot_count = cursor.fetchone()[0]
            
            # Get file change count
            cursor.execute("SELECT COUNT(*) FROM file_changes")
            file_change_count = cursor.fetchone()[0]
            
            # Get bookmark count
            cursor.execute("SELECT COUNT(*) FROM bookmarks")
            bookmark_count = cursor.fetchone()[0]
            
            # Get total size
            cursor.execute("SELECT SUM(total_size) FROM snapshots")
            total_size = cursor.fetchone()[0] or 0
            
            # Get database file size
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            
            return {
                'snapshot_count': snapshot_count,
                'file_change_count': file_change_count,
                'bookmark_count': bookmark_count,
                'total_content_size': total_size,
                'database_size': db_size,
                'schema_version': self.get_schema_version()
            }