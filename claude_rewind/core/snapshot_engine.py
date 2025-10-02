"""Core snapshot creation and management engine."""

import hashlib
import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import pathspec

from .interfaces import ISnapshotEngine
from .models import (
    ActionContext, Snapshot, SnapshotId, SnapshotMetadata, FileState,
    TimelineFilters, ChangeType, FileChange, generate_snapshot_id
)
from ..storage.database import DatabaseManager
from ..storage.file_store import FileStore
from ..storage.auto_cleanup import StorageCleanupManager
from .config import PerformanceConfig, StorageConfig, GitIntegrationConfig


logger = logging.getLogger(__name__)


class SnapshotEngineError(Exception):
    """Base exception for snapshot engine operations."""
    pass


class SnapshotEngine(ISnapshotEngine):
    """Core engine for creating and managing project snapshots."""

    def __init__(self, project_root: Path, storage_root: Path,
                 performance_config: Optional[PerformanceConfig] = None,
                 storage_config: Optional[StorageConfig] = None,
                 git_config: Optional[GitIntegrationConfig] = None,
                 auto_cleanup_enabled: bool = True):
        """Initialize snapshot engine.

        Args:
            project_root: Root directory of the project to snapshot
            storage_root: Root directory for snapshot storage
            performance_config: Performance configuration settings
            storage_config: Storage configuration for cleanup limits
            git_config: Git integration configuration
            auto_cleanup_enabled: Enable automatic storage cleanup (default: True)
        """
        self.project_root = project_root.resolve()
        self.storage_root = storage_root
        self.performance_config = performance_config or PerformanceConfig()
        self.storage_config = storage_config or StorageConfig()
        self.git_config = git_config or GitIntegrationConfig()

        # Initialize storage components with performance config
        self.db_manager = DatabaseManager(storage_root / "metadata.db")
        self.file_store = FileStore(
            storage_root,
            compression_level=getattr(performance_config, 'compression_level', 3) if performance_config else 3
        )

        # Initialize automatic cleanup manager
        self.cleanup_manager = StorageCleanupManager(
            self.db_manager,
            self.file_store,
            self.storage_config,
            self.storage_root
        )

        # Start automatic cleanup if enabled
        if auto_cleanup_enabled:
            self.cleanup_manager.start_automatic_cleanup(interval_seconds=300)  # Check every 5 minutes

        # Cache for file states to optimize incremental snapshots
        self._last_snapshot_states: Dict[Path, FileState] = {}
        self._last_snapshot_id: Optional[SnapshotId] = None

        # Performance optimization caches
        self._file_hash_cache: Dict[Tuple[Path, float, int], str] = {}  # (path, mtime, size) -> hash
        self._cache_lock = threading.Lock()

        # Lazy loading cache for large files
        self._lazy_content_cache: Dict[str, bytes] = {}
        self._lazy_cache_lock = threading.Lock()

        # Load .gitignore patterns if respect_gitignore is enabled
        self._gitignore_spec = None
        if self.git_config.respect_gitignore:
            self._load_gitignore()

        logger.info(f"SnapshotEngine initialized for project: {project_root}")
        logger.debug(f"Performance config: max_file_size={self.performance_config.max_file_size_mb}MB, "
                    f"parallel={self.performance_config.parallel_processing}, "
                    f"memory_limit={self.performance_config.memory_limit_mb}MB")
        logger.debug(f"Auto cleanup: enabled={auto_cleanup_enabled}, "
                    f"max_snapshots={self.storage_config.max_snapshots}, "
                    f"max_disk_mb={self.storage_config.max_disk_usage_mb}")

    def _load_gitignore(self) -> None:
        """Load .gitignore patterns from project root."""
        gitignore_path = self.project_root / ".gitignore"

        if not gitignore_path.exists():
            logger.debug("No .gitignore found in project root")
            return

        try:
            with open(gitignore_path, 'r') as f:
                patterns = f.read().splitlines()

            # Filter out comments and empty lines
            patterns = [p for p in patterns if p.strip() and not p.strip().startswith('#')]

            # Create pathspec from patterns
            self._gitignore_spec = pathspec.PathSpec.from_lines('gitwildmatch', patterns)

            logger.info(f"Loaded {len(patterns)} .gitignore patterns")
            logger.debug(f"Gitignore patterns: {patterns[:5]}..." if len(patterns) > 5 else f"Gitignore patterns: {patterns}")

        except Exception as e:
            logger.warning(f"Failed to load .gitignore: {e}")
            self._gitignore_spec = None

    def create_snapshot(self, context: ActionContext) -> SnapshotId:
        """Create a new snapshot of the current project state.
        
        Args:
            context: Context information for the action triggering this snapshot
            
        Returns:
            Unique identifier for the created snapshot
            
        Raises:
            SnapshotEngineError: If snapshot creation fails
        """
        start_time = time.time()
        snapshot_id = generate_snapshot_id()
        
        try:
            logger.info(f"Creating snapshot {snapshot_id} for action: {context.action_type}")
            
            # Scan current project state
            current_states = self._scan_project_state()
            
            # Detect changes since last snapshot
            file_changes = self._detect_file_changes(current_states)
            
            # Create snapshot metadata
            metadata = SnapshotMetadata(
                id=snapshot_id,
                timestamp=context.timestamp,
                action_type=context.action_type,
                prompt_context=context.prompt_context,
                files_affected=context.affected_files,
                total_size=sum(state.size for state in current_states.values() if state.exists),
                compression_ratio=0.0,  # Will be updated after storage
                parent_snapshot=self._last_snapshot_id
            )
            
            # Convert relative paths to absolute paths for file store
            absolute_states = {}
            for rel_path, state in current_states.items():
                abs_path = self.project_root / rel_path
                absolute_states[abs_path] = FileState(
                    path=abs_path,
                    content_hash=state.content_hash,
                    size=state.size,
                    modified_time=state.modified_time,
                    permissions=state.permissions,
                    exists=state.exists
                )
            
            # Store snapshot content
            manifest = self.file_store.create_snapshot(snapshot_id, absolute_states)
            
            # Update compression ratio from actual storage
            if manifest['total_size'] > 0:
                metadata.compression_ratio = manifest['compressed_size'] / manifest['total_size']
            
            # Store metadata in database
            self.db_manager.create_snapshot(metadata)
            
            # Store file changes
            for file_change in file_changes:
                self.db_manager.add_file_change(snapshot_id, file_change)
            
            # Update cache for next incremental snapshot
            self._last_snapshot_states = current_states.copy()
            self._last_snapshot_id = snapshot_id

            # Trigger immediate cleanup check after snapshot creation
            # This ensures limits are enforced proactively
            try:
                deleted_count = self.cleanup_manager.enforce_storage_limits()
                if deleted_count > 0:
                    logger.info(f"Post-snapshot cleanup: removed {deleted_count} old snapshots")

                    # Check if our last snapshot ID was deleted during cleanup
                    # If so, clear it to avoid foreign key issues
                    if self._last_snapshot_id:
                        try:
                            remaining_snapshot = self.db_manager.get_snapshot(self._last_snapshot_id)
                            if not remaining_snapshot:
                                logger.debug(f"Last snapshot {self._last_snapshot_id} was deleted during cleanup, clearing reference")
                                self._last_snapshot_id = None
                                self._last_snapshot_states.clear()
                        except Exception:
                            self._last_snapshot_id = None
                            self._last_snapshot_states.clear()

            except Exception as e:
                logger.error(f"Post-snapshot cleanup failed: {e}")

            elapsed_time = time.time() - start_time
            logger.info(f"Snapshot {snapshot_id} created in {elapsed_time:.3f}s "
                       f"({len(current_states)} files, {len(file_changes)} changes)")
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to create snapshot {snapshot_id}: {e}")
            
            # Clean up partial snapshot
            try:
                self.file_store.delete_snapshot(snapshot_id)
                self.db_manager.delete_snapshot(snapshot_id)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up partial snapshot: {cleanup_error}")
            
            raise SnapshotEngineError(f"Snapshot creation failed: {e}")
    
    def get_snapshot(self, snapshot_id: SnapshotId) -> Optional[Snapshot]:
        """Retrieve a specific snapshot by ID.
        
        Args:
            snapshot_id: Unique snapshot identifier
            
        Returns:
            Complete snapshot object or None if not found
        """
        try:
            # Get metadata from database
            metadata = self.db_manager.get_snapshot(snapshot_id)
            if not metadata:
                return None
            
            # Get file changes
            file_changes = self.db_manager.get_file_changes(snapshot_id)
            metadata.files_affected = [change.path for change in file_changes]
            
            # Get snapshot manifest from file store
            manifest = self.file_store.get_snapshot_manifest(snapshot_id)
            
            # Build file states from manifest
            file_states = {}
            for file_path_str, file_info in manifest['files'].items():
                abs_path = Path(file_path_str)
                # Convert absolute path back to relative path for consistency
                try:
                    rel_path = abs_path.relative_to(self.project_root)
                except ValueError:
                    # If path is not under project root, use as-is
                    rel_path = abs_path
                
                file_states[rel_path] = FileState(
                    path=rel_path,
                    content_hash=file_info.get('content_hash', ''),
                    size=file_info.get('size', 0),
                    modified_time=datetime.fromisoformat(file_info['modified_time']),
                    permissions=file_info.get('permissions', 0o644),
                    exists=file_info.get('exists', True)
                )
            
            return Snapshot(
                id=snapshot_id,
                timestamp=metadata.timestamp,
                metadata=metadata,
                file_states=file_states
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve snapshot {snapshot_id}: {e}")
            return None
    
    def list_snapshots(self, filters: Optional[TimelineFilters] = None) -> List[SnapshotMetadata]:
        """List all snapshots with optional filtering.
        
        Args:
            filters: Optional filters to apply
            
        Returns:
            List of snapshot metadata, ordered by timestamp (newest first)
        """
        try:
            # Get all snapshots from database
            snapshots = self.db_manager.list_snapshots()
            
            # Apply filters if provided
            if filters:
                snapshots = self._apply_filters(snapshots, filters)
            
            # Populate files_affected for each snapshot
            for snapshot in snapshots:
                file_changes = self.db_manager.get_file_changes(snapshot.id)
                snapshot.files_affected = [change.path for change in file_changes]
            
            return snapshots
            
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
            return []
    
    def delete_snapshot(self, snapshot_id: SnapshotId) -> bool:
        """Delete a specific snapshot.
        
        Args:
            snapshot_id: Unique snapshot identifier
            
        Returns:
            True if snapshot was deleted, False if not found
        """
        try:
            # Delete from file store
            file_deleted = self.file_store.delete_snapshot(snapshot_id)
            
            # Delete from database
            db_deleted = self.db_manager.delete_snapshot(snapshot_id)
            
            # Clear cache if this was the last snapshot
            if snapshot_id == self._last_snapshot_id:
                self._last_snapshot_states.clear()
                self._last_snapshot_id = None
            
            success = file_deleted or db_deleted
            if success:
                logger.info(f"Deleted snapshot: {snapshot_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False
    
    def _scan_project_state(self) -> Dict[Path, FileState]:
        """Scan current project state and return file states.
        
        Returns:
            Dictionary mapping file paths to their current states
        """
        start_time = time.time()
        file_states = {}
        
        try:
            # Collect all files to process
            files_to_process = []
            total_size = 0
            
            for root, dirs, files in os.walk(self.project_root):
                root_path = Path(root)
                
                # Skip hidden directories and common ignore patterns
                dirs[:] = [d for d in dirs if not self._should_ignore_directory(root_path / d)]
                
                for file_name in files:
                    file_path = root_path / file_name
                    
                    # Skip files that should be ignored
                    if self._should_ignore_file(file_path):
                        continue
                    
                    try:
                        stat = file_path.stat()
                        file_size_mb = stat.st_size / (1024 * 1024)
                        
                        # Skip files that are too large
                        if file_size_mb > self.performance_config.max_file_size_mb:
                            logger.warning(f"Skipping large file {file_path}: {file_size_mb:.1f}MB")
                            continue
                        
                        files_to_process.append((file_path, stat))
                        total_size += stat.st_size
                        
                    except Exception as e:
                        logger.warning(f"Failed to stat file {file_path}: {e}")
                        continue
            
            # Check if project is too large
            total_size_gb = total_size / (1024 * 1024 * 1024)
            if total_size_gb > 1.0:
                logger.warning(f"Large project detected: {total_size_gb:.2f}GB")
            
            # Process files with parallel processing if enabled and beneficial
            if (self.performance_config.parallel_processing and 
                len(files_to_process) > 10):  # Only use parallel for larger projects
                
                file_states = self._scan_files_parallel(files_to_process)
            else:
                file_states = self._scan_files_sequential(files_to_process)
            
            elapsed_time = time.time() - start_time
            logger.debug(f"Scanned {len(file_states)} files in {elapsed_time:.3f}s "
                        f"({total_size_gb:.2f}GB total)")
            
            # Warn if scan took too long
            if elapsed_time > 0.5:  # 500ms target
                logger.warning(f"Project scan took {elapsed_time:.3f}s, exceeding 500ms target")
            
            return file_states
            
        except Exception as e:
            logger.error(f"Failed to scan project state: {e}")
            raise SnapshotEngineError(f"Project scan failed: {e}")
    
    def _scan_files_sequential(self, files_to_process: List[Tuple[Path, os.stat_result]]) -> Dict[Path, FileState]:
        """Scan files sequentially.
        
        Args:
            files_to_process: List of (file_path, stat_result) tuples
            
        Returns:
            Dictionary mapping file paths to their states
        """
        file_states = {}
        
        for file_path, stat in files_to_process:
            try:
                # Calculate content hash with caching
                content_hash = self._calculate_file_hash_cached(file_path, stat)
                
                # Create file state
                relative_path = file_path.relative_to(self.project_root)
                file_states[relative_path] = FileState(
                    path=relative_path,
                    content_hash=content_hash,
                    size=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime),
                    permissions=stat.st_mode,
                    exists=True
                )
                
            except Exception as e:
                logger.warning(f"Failed to process file {file_path}: {e}")
                continue
        
        return file_states
    
    def _scan_files_parallel(self, files_to_process: List[Tuple[Path, os.stat_result]]) -> Dict[Path, FileState]:
        """Scan files in parallel using thread pool.
        
        Args:
            files_to_process: List of (file_path, stat_result) tuples
            
        Returns:
            Dictionary mapping file paths to their states
        """
        file_states = {}
        max_workers = min(4, len(files_to_process))  # Limit concurrent threads
        
        def process_file(file_path: Path, stat: os.stat_result) -> Optional[Tuple[Path, FileState]]:
            try:
                # Calculate content hash with caching
                content_hash = self._calculate_file_hash_cached(file_path, stat)
                
                # Create file state
                relative_path = file_path.relative_to(self.project_root)
                file_state = FileState(
                    path=relative_path,
                    content_hash=content_hash,
                    size=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime),
                    permissions=stat.st_mode,
                    exists=True
                )
                
                return (relative_path, file_state)
                
            except Exception as e:
                logger.warning(f"Failed to process file {file_path}: {e}")
                return None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(process_file, file_path, stat): (file_path, stat)
                for file_path, stat in files_to_process
            }
            
            # Collect results
            for future in as_completed(future_to_file):
                result = future.result()
                if result:
                    relative_path, file_state = result
                    file_states[relative_path] = file_state
        
        return file_states
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content.
        
        Args:
            file_path: Path to file
            
        Returns:
            SHA-256 hash as hex string
        """
        hasher = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            
            return hasher.hexdigest()
            
        except Exception as e:
            logger.warning(f"Failed to hash file {file_path}: {e}")
            # Return a placeholder hash for files we can't read
            return f"error_{int(time.time())}"
    
    def _calculate_file_hash_cached(self, file_path: Path, stat: os.stat_result) -> str:
        """Calculate SHA-256 hash of file content with caching.
        
        Uses file modification time and size as cache key to avoid
        recalculating hashes for unchanged files.
        
        Args:
            file_path: Path to file
            stat: File stat result
            
        Returns:
            SHA-256 hash as hex string
        """
        # Create cache key from path, mtime, and size
        cache_key = (file_path, stat.st_mtime, stat.st_size)
        
        with self._cache_lock:
            if cache_key in self._file_hash_cache:
                return self._file_hash_cache[cache_key]
        
        # Calculate hash
        content_hash = self._calculate_file_hash(file_path)
        
        # Cache the result
        with self._cache_lock:
            # Limit cache size to prevent memory issues
            cache_limit = getattr(self.performance_config, 'cache_size_limit', 10000)
            if len(self._file_hash_cache) >= cache_limit:
                # Remove oldest entries (simple FIFO)
                num_to_remove = max(1, cache_limit // 10)  # Remove 10% of cache
                oldest_keys = list(self._file_hash_cache.keys())[:num_to_remove]
                for key in oldest_keys:
                    del self._file_hash_cache[key]
            
            self._file_hash_cache[cache_key] = content_hash
        
        return content_hash
    
    def _detect_file_changes(self, current_states: Dict[Path, FileState]) -> List[FileChange]:
        """Detect changes between current state and last snapshot.
        
        Args:
            current_states: Current file states
            
        Returns:
            List of detected file changes
        """
        changes = []
        
        # Get all file paths from both current and previous states
        current_paths = set(current_states.keys())
        previous_paths = set(self._last_snapshot_states.keys())
        
        # Find added files
        for path in current_paths - previous_paths:
            changes.append(FileChange(
                path=path,
                change_type=ChangeType.ADDED,
                before_hash=None,
                after_hash=current_states[path].content_hash,
                line_changes=[]  # Will be populated when needed for diffs
            ))
        
        # Find deleted files
        for path in previous_paths - current_paths:
            changes.append(FileChange(
                path=path,
                change_type=ChangeType.DELETED,
                before_hash=self._last_snapshot_states[path].content_hash,
                after_hash=None,
                line_changes=[]
            ))
        
        # Find modified files
        for path in current_paths & previous_paths:
            current_state = current_states[path]
            previous_state = self._last_snapshot_states[path]
            
            if current_state.content_hash != previous_state.content_hash:
                changes.append(FileChange(
                    path=path,
                    change_type=ChangeType.MODIFIED,
                    before_hash=previous_state.content_hash,
                    after_hash=current_state.content_hash,
                    line_changes=[]
                ))
        
        logger.debug(f"Detected {len(changes)} file changes")
        return changes
    
    def _should_ignore_directory(self, dir_path: Path) -> bool:
        """Check if directory should be ignored during scanning.

        Args:
            dir_path: Directory path to check

        Returns:
            True if directory should be ignored
        """
        dir_name = dir_path.name

        # Common directories to ignore
        ignore_patterns = {
            '.git', '.svn', '.hg',  # Version control
            '__pycache__', '.pytest_cache',  # Python
            'node_modules', '.npm',  # Node.js
            '.vscode', '.idea',  # IDEs
            'venv', '.venv', 'env',  # Python virtual environments
            'target', 'build', 'dist',  # Build outputs
            '.claude-rewind'  # Our own storage
        }

        # Check hardcoded patterns first
        if dir_name in ignore_patterns or dir_name.startswith('.'):
            return True

        # Check .gitignore patterns if enabled
        if self._gitignore_spec:
            try:
                # Get relative path from project root
                rel_path = dir_path.relative_to(self.project_root)
                # pathspec expects directory paths to end with /
                if self._gitignore_spec.match_file(str(rel_path) + '/'):
                    logger.debug(f"Directory {rel_path} matched .gitignore")
                    return True
            except ValueError:
                # Path not under project root
                pass

        return False
    
    def _should_ignore_file(self, file_path: Path) -> bool:
        """Check if file should be ignored during scanning.

        Args:
            file_path: File path to check

        Returns:
            True if file should be ignored
        """
        file_name = file_path.name

        # Common file patterns to ignore
        ignore_patterns = {
            '.DS_Store',  # macOS
            'Thumbs.db',  # Windows
            '.gitignore', '.gitkeep',  # Git
            '*.pyc', '*.pyo', '*.pyd',  # Python compiled
            '*.log', '*.tmp', '*.temp',  # Temporary files
        }

        # Check exact matches
        if file_name in ignore_patterns:
            return True

        # Check file extensions
        suffix = file_path.suffix.lower()
        ignore_extensions = {'.pyc', '.pyo', '.pyd', '.log', '.tmp', '.temp'}

        if suffix in ignore_extensions:
            return True

        # Check .gitignore patterns if enabled
        if self._gitignore_spec:
            try:
                # Get relative path from project root
                rel_path = file_path.relative_to(self.project_root)
                if self._gitignore_spec.match_file(str(rel_path)):
                    logger.debug(f"File {rel_path} matched .gitignore")
                    return True
            except ValueError:
                # Path not under project root
                pass

        return False
    
    def _apply_filters(self, snapshots: List[SnapshotMetadata], 
                      filters: TimelineFilters) -> List[SnapshotMetadata]:
        """Apply filters to snapshot list.
        
        Args:
            snapshots: List of snapshots to filter
            filters: Filters to apply
            
        Returns:
            Filtered list of snapshots
        """
        filtered = snapshots
        
        # Apply date range filter
        if filters.date_range:
            start_date, end_date = filters.date_range
            filtered = [s for s in filtered 
                       if start_date <= s.timestamp <= end_date]
        
        # Apply action type filter
        if filters.action_types:
            filtered = [s for s in filtered 
                       if s.action_type in filters.action_types]
        
        # Apply file pattern filter
        if filters.file_patterns:
            filtered = [s for s in filtered 
                       if any(self._matches_pattern(f, filters.file_patterns) 
                             for f in s.files_affected)]
        
        # Apply bookmark filter
        if filters.bookmarked_only:
            filtered = [s for s in filtered if s.bookmark_name is not None]
        
        return filtered
    
    def _matches_pattern(self, file_path: Path, patterns: List[str]) -> bool:
        """Check if file path matches any of the given patterns.
        
        Args:
            file_path: File path to check
            patterns: List of patterns to match against
            
        Returns:
            True if file matches any pattern
        """
        file_str = str(file_path)
        
        for pattern in patterns:
            # Simple wildcard matching
            if '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(file_str, pattern):
                    return True
            else:
                # Exact substring match
                if pattern in file_str:
                    return True
        
        return False
    
    def get_file_content_lazy(self, snapshot_id: SnapshotId, file_path: Path) -> Optional[bytes]:
        """Lazily load file content from snapshot.
        
        This method loads file content on-demand rather than loading all
        content when retrieving a snapshot. Useful for large files.
        
        Args:
            snapshot_id: Snapshot identifier
            file_path: Path to file within snapshot
            
        Returns:
            File content as bytes, or None if not found
        """
        try:
            # Check lazy cache first
            cache_key = f"{snapshot_id}:{file_path}"
            with self._lazy_cache_lock:
                if cache_key in self._lazy_content_cache:
                    return self._lazy_content_cache[cache_key]
            
            # Get snapshot manifest
            manifest = self.file_store.get_snapshot_manifest(snapshot_id)
            
            # Try different path formats to find the file
            file_key = str(file_path)
            if file_key not in manifest['files']:
                # Try absolute path
                abs_path = self.project_root / file_path
                file_key = str(abs_path)
                if file_key not in manifest['files']:
                    # Try with forward slashes
                    file_key = str(file_path).replace('\\', '/')
                    if file_key not in manifest['files']:
                        logger.debug(f"File not found in manifest: {file_path}")
                        logger.debug(f"Available files: {list(manifest['files'].keys())[:5]}...")
                        return None
            
            file_info = manifest['files'][file_key]
            if not file_info['exists']:
                return None
            
            # Retrieve content from file store
            content = self.file_store.retrieve_content(file_info['content_hash'])
            
            # Cache content if it's not too large
            content_size_mb = len(content) / (1024 * 1024)
            if content_size_mb < 10:  # Cache files smaller than 10MB
                with self._lazy_cache_lock:
                    # Limit cache size
                    if len(self._lazy_content_cache) > 100:
                        # Remove oldest entry
                        oldest_key = next(iter(self._lazy_content_cache))
                        del self._lazy_content_cache[oldest_key]
                    
                    self._lazy_content_cache[cache_key] = content
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to load content for {file_path} in {snapshot_id}: {e}")
            return None
    
    def preload_snapshot_content(self, snapshot_id: SnapshotId, 
                               file_paths: Optional[List[Path]] = None) -> None:
        """Preload content for specific files in a snapshot.
        
        This can be used to warm up the lazy loading cache for files
        that are likely to be accessed soon.
        
        Args:
            snapshot_id: Snapshot identifier
            file_paths: Specific files to preload, or None for all files
        """
        try:
            snapshot = self.get_snapshot(snapshot_id)
            if not snapshot:
                return
            
            paths_to_load = file_paths or list(snapshot.file_states.keys())
            
            # Use parallel loading for multiple files
            if len(paths_to_load) > 1 and self.performance_config.parallel_processing:
                max_workers = min(4, len(paths_to_load))
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(self.get_file_content_lazy, snapshot_id, path)
                        for path in paths_to_load
                    ]
                    
                    # Wait for completion
                    for future in as_completed(futures):
                        future.result()  # This will raise any exceptions
            else:
                # Sequential loading
                for path in paths_to_load:
                    self.get_file_content_lazy(snapshot_id, path)
            
            logger.debug(f"Preloaded content for {len(paths_to_load)} files in {snapshot_id}")
            
        except Exception as e:
            logger.error(f"Failed to preload content for {snapshot_id}: {e}")
    
    def clear_caches(self) -> None:
        """Clear all internal caches to free memory."""
        with self._cache_lock:
            self._file_hash_cache.clear()
        
        with self._lazy_cache_lock:
            self._lazy_content_cache.clear()
        
        logger.debug("Cleared all caches")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about cache usage.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._cache_lock:
            hash_cache_size = len(self._file_hash_cache)
        
        with self._lazy_cache_lock:
            content_cache_size = len(self._lazy_content_cache)
            content_cache_memory = sum(len(content) for content in self._lazy_content_cache.values())
        
        return {
            'hash_cache_entries': hash_cache_size,
            'content_cache_entries': content_cache_size,
            'content_cache_memory_mb': content_cache_memory / (1024 * 1024),
            'performance_config': {
                'max_file_size_mb': self.performance_config.max_file_size_mb,
                'parallel_processing': self.performance_config.parallel_processing,
                'memory_limit_mb': self.performance_config.memory_limit_mb,
                'snapshot_timeout_seconds': self.performance_config.snapshot_timeout_seconds
            }
        }
    
    def get_incremental_stats(self) -> Dict[str, int]:
        """Get statistics about incremental snapshot efficiency.
        
        Returns:
            Dictionary with incremental snapshot statistics
        """
        return {
            'cached_files': len(self._last_snapshot_states),
            'last_snapshot_id': self._last_snapshot_id or 'none',
            'incremental_enabled': self._last_snapshot_id is not None
        }