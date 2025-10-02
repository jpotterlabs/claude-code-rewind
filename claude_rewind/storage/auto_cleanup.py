"""Automatic storage cleanup and enforcement system."""

import logging
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

from .database import DatabaseManager
from .file_store import FileStore
from ..core.config import StorageConfig

logger = logging.getLogger(__name__)


class StorageCleanupManager:
    """Manages automatic cleanup and storage limit enforcement."""

    def __init__(self,
                 db_manager: DatabaseManager,
                 file_store: FileStore,
                 storage_config: StorageConfig,
                 storage_root: Path):
        """Initialize storage cleanup manager.

        Args:
            db_manager: Database manager instance
            file_store: File store instance
            storage_config: Storage configuration
            storage_root: Root directory for snapshot storage
        """
        self.db_manager = db_manager
        self.file_store = file_store
        self.storage_config = storage_config
        self.storage_root = storage_root

        # Background thread for automatic cleanup
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cleanup_interval = 300  # 5 minutes

        # Callbacks for cleanup events
        self._on_cleanup_callback: Optional[Callable] = None

        logger.info("StorageCleanupManager initialized")

    def start_automatic_cleanup(self, interval_seconds: int = 300) -> None:
        """Start background thread for automatic cleanup.

        Args:
            interval_seconds: How often to check and enforce limits (default: 5 minutes)
        """
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            logger.warning("Automatic cleanup already running")
            return

        self._cleanup_interval = interval_seconds
        self._stop_event.clear()

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="StorageCleanup"
        )
        self._cleanup_thread.start()

        logger.info(f"Started automatic cleanup (interval: {interval_seconds}s)")

    def stop_automatic_cleanup(self) -> None:
        """Stop background cleanup thread."""
        if not self._cleanup_thread or not self._cleanup_thread.is_alive():
            logger.warning("Automatic cleanup not running")
            return

        self._stop_event.set()
        self._cleanup_thread.join(timeout=5)

        logger.info("Stopped automatic cleanup")

    def _cleanup_loop(self) -> None:
        """Main loop for background cleanup thread."""
        while not self._stop_event.is_set():
            try:
                self.enforce_storage_limits()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)

            # Wait for next interval or stop event
            self._stop_event.wait(timeout=self._cleanup_interval)

    def enforce_storage_limits(self) -> int:
        """Enforce all storage limits and return number of snapshots deleted.

        Returns:
            Number of snapshots deleted
        """
        total_deleted = 0

        # 1. Enforce age-based cleanup
        total_deleted += self._cleanup_old_snapshots()

        # 2. Enforce snapshot count limit
        total_deleted += self._cleanup_excess_snapshots()

        # 3. Enforce disk usage limit
        total_deleted += self._cleanup_by_disk_usage()

        if total_deleted > 0:
            logger.info(f"Automatic cleanup: deleted {total_deleted} snapshots")
            if self._on_cleanup_callback:
                self._on_cleanup_callback(total_deleted)

        return total_deleted

    def _cleanup_old_snapshots(self) -> int:
        """Remove snapshots older than cleanup_after_days.

        Returns:
            Number of snapshots deleted
        """
        # Don't do age-based cleanup if cleanup_after_days is 0 or negative
        if self.storage_config.cleanup_after_days <= 0:
            return 0

        cutoff_date = datetime.now() - timedelta(days=self.storage_config.cleanup_after_days)
        all_snapshots = self.db_manager.list_snapshots()

        old_snapshots = [s for s in all_snapshots if s.timestamp < cutoff_date]

        if not old_snapshots:
            return 0

        deleted_count = 0
        for snapshot in old_snapshots:
            try:
                self.db_manager.delete_snapshot(snapshot.id)
                self.file_store.delete_snapshot(snapshot.id)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete old snapshot {snapshot.id}: {e}")

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} snapshots older than {self.storage_config.cleanup_after_days} days")

        return deleted_count

    def _cleanup_excess_snapshots(self) -> int:
        """Remove snapshots exceeding max_snapshots limit.

        Returns:
            Number of snapshots deleted
        """
        all_snapshots = self.db_manager.list_snapshots()

        if len(all_snapshots) <= self.storage_config.max_snapshots:
            return 0

        # Sort by timestamp (oldest first) and delete excess
        sorted_snapshots = sorted(all_snapshots, key=lambda x: x.timestamp)
        excess_count = len(all_snapshots) - self.storage_config.max_snapshots
        snapshots_to_delete = sorted_snapshots[:excess_count]

        deleted_count = 0
        for snapshot in snapshots_to_delete:
            try:
                self.db_manager.delete_snapshot(snapshot.id)
                self.file_store.delete_snapshot(snapshot.id)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete excess snapshot {snapshot.id}: {e}")

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} snapshots to stay under limit of {self.storage_config.max_snapshots}")

        return deleted_count

    def _cleanup_by_disk_usage(self) -> int:
        """Remove oldest snapshots if disk usage exceeds limit.

        Returns:
            Number of snapshots deleted
        """
        current_usage_mb = self.get_total_disk_usage_mb()
        max_usage_mb = self.storage_config.max_disk_usage_mb

        if current_usage_mb <= max_usage_mb:
            return 0

        logger.info(f"Disk usage ({current_usage_mb:.1f} MB) exceeds limit ({max_usage_mb} MB)")

        # Delete oldest snapshots until under limit
        all_snapshots = sorted(self.db_manager.list_snapshots(), key=lambda x: x.timestamp)
        deleted_count = 0

        for snapshot in all_snapshots:
            if current_usage_mb <= max_usage_mb:
                break

            try:
                # Get snapshot size before deletion
                snapshot_size_mb = self._get_snapshot_size_mb(snapshot.id)

                self.db_manager.delete_snapshot(snapshot.id)
                self.file_store.delete_snapshot(snapshot.id)

                current_usage_mb -= snapshot_size_mb
                deleted_count += 1

            except Exception as e:
                logger.error(f"Failed to delete snapshot {snapshot.id} for disk usage: {e}")

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} snapshots to reduce disk usage to {current_usage_mb:.1f} MB")

        return deleted_count

    def get_total_disk_usage_mb(self) -> float:
        """Calculate total disk usage of all snapshots in MB.

        Returns:
            Total disk usage in megabytes
        """
        try:
            total_bytes = sum(
                f.stat().st_size
                for f in self.storage_root.rglob('*')
                if f.is_file()
            )
            return total_bytes / (1024 * 1024)
        except Exception as e:
            logger.error(f"Failed to calculate disk usage: {e}")
            return 0.0

    def _get_snapshot_size_mb(self, snapshot_id: str) -> float:
        """Get the disk size of a specific snapshot in MB.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            Size in megabytes
        """
        try:
            snapshot_data = self.file_store.get_snapshot_manifest(snapshot_id)
            return snapshot_data.get('total_size', 0) / (1024 * 1024)
        except Exception:
            return 0.0

    def get_storage_stats(self) -> dict:
        """Get current storage statistics.

        Returns:
            Dictionary with storage stats
        """
        all_snapshots = self.db_manager.list_snapshots()
        current_usage_mb = self.get_total_disk_usage_mb()

        return {
            'total_snapshots': len(all_snapshots),
            'max_snapshots': self.storage_config.max_snapshots,
            'current_disk_usage_mb': current_usage_mb,
            'max_disk_usage_mb': self.storage_config.max_disk_usage_mb,
            'usage_percentage': (current_usage_mb / self.storage_config.max_disk_usage_mb * 100)
                               if self.storage_config.max_disk_usage_mb > 0 else 0,
            'cleanup_after_days': self.storage_config.cleanup_after_days,
            'oldest_snapshot': min(all_snapshots, key=lambda x: x.timestamp).timestamp
                              if all_snapshots else None,
            'newest_snapshot': max(all_snapshots, key=lambda x: x.timestamp).timestamp
                              if all_snapshots else None,
        }

    def set_cleanup_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback to be called after cleanup operations.

        Args:
            callback: Function that takes deleted_count as argument
        """
        self._on_cleanup_callback = callback
