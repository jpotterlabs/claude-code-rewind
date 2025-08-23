"""Database migration system for schema changes."""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, Callable, List
from datetime import datetime

from .database import DatabaseManager, DatabaseError


logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Exception raised during database migrations."""
    pass


class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize migration manager.
        
        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.migrations = self._get_migrations()
    
    def _get_migrations(self) -> Dict[int, Callable]:
        """Get all available migrations.
        
        Returns:
            Dictionary mapping version numbers to migration functions
        """
        return {
            # Future migrations will be added here
            # 2: self._migrate_to_v2,
            # 3: self._migrate_to_v3,
        }
    
    def needs_migration(self) -> bool:
        """Check if database needs migration.
        
        Returns:
            True if migration is needed
        """
        current_version = self.db_manager.get_schema_version()
        target_version = self.db_manager.SCHEMA_VERSION
        return current_version < target_version
    
    def get_pending_migrations(self) -> List[int]:
        """Get list of pending migration versions.
        
        Returns:
            List of version numbers that need to be applied
        """
        current_version = self.db_manager.get_schema_version()
        target_version = self.db_manager.SCHEMA_VERSION
        
        return [
            version for version in range(current_version + 1, target_version + 1)
            if version in self.migrations
        ]
    
    def migrate(self) -> None:
        """Apply all pending migrations.
        
        Raises:
            MigrationError: If migration fails
        """
        if not self.needs_migration():
            logger.info("Database is up to date")
            return
        
        pending = self.get_pending_migrations()
        logger.info(f"Applying {len(pending)} migrations: {pending}")
        
        for version in pending:
            try:
                self._apply_migration(version)
                logger.info(f"Applied migration to version {version}")
            except Exception as e:
                logger.error(f"Migration to version {version} failed: {e}")
                raise MigrationError(f"Migration to version {version} failed: {e}")
        
        logger.info("All migrations applied successfully")
    
    def _apply_migration(self, version: int) -> None:
        """Apply a specific migration.
        
        Args:
            version: Migration version to apply
            
        Raises:
            MigrationError: If migration function not found or fails
        """
        if version not in self.migrations:
            raise MigrationError(f"Migration for version {version} not found")
        
        migration_func = self.migrations[version]
        
        with self.db_manager._get_connection() as conn:
            # Start transaction
            conn.execute("BEGIN TRANSACTION")
            
            try:
                # Apply migration
                migration_func(conn)
                
                # Update schema version
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO schema_info (version, applied_at)
                    VALUES (?, ?)
                """, (version, int(datetime.now().timestamp())))
                
                # Commit transaction
                conn.commit()
                
            except Exception as e:
                # Rollback on error
                conn.rollback()
                raise e
    
    def create_backup(self, backup_path: Path) -> None:
        """Create database backup before migration.
        
        Args:
            backup_path: Path for backup file
        """
        try:
            import shutil
            shutil.copy2(self.db_manager.db_path, backup_path)
            logger.info(f"Database backup created: {backup_path}")
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    # Example migration functions (for future use)
    
    def _migrate_to_v2(self, conn: sqlite3.Connection) -> None:
        """Example migration to version 2.
        
        Args:
            conn: Database connection
        """
        cursor = conn.cursor()
        
        # Example: Add new column to snapshots table
        cursor.execute("""
            ALTER TABLE snapshots 
            ADD COLUMN bookmark_name TEXT DEFAULT NULL
        """)
        
        # Example: Create new index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_bookmark 
            ON snapshots(bookmark_name) 
            WHERE bookmark_name IS NOT NULL
        """)
    
    def _migrate_to_v3(self, conn: sqlite3.Connection) -> None:
        """Example migration to version 3.
        
        Args:
            conn: Database connection
        """
        cursor = conn.cursor()
        
        # Example: Create new table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshot_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
                UNIQUE(snapshot_id, tag_name)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshot_tags_name 
            ON snapshot_tags(tag_name)
        """)


def migrate_database(db_path: Path) -> None:
    """Convenience function to migrate database.
    
    Args:
        db_path: Path to database file
        
    Raises:
        MigrationError: If migration fails
    """
    db_manager = DatabaseManager(db_path)
    migration_manager = MigrationManager(db_manager)
    
    if migration_manager.needs_migration():
        # Create backup before migration
        backup_path = db_path.with_suffix('.backup')
        migration_manager.create_backup(backup_path)
        
        # Apply migrations
        migration_manager.migrate()
    else:
        logger.info("Database is already up to date")