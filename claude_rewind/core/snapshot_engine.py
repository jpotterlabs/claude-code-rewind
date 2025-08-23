"""Core snapshot creation and management engine."""

import hashlib
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .interfaces import ISnapshotEngine
from .models import (
    ActionContext, Snapshot, SnapshotId, SnapshotMetadata, FileState,
    TimelineFilters, ChangeType, FileChange, generate_snapshot_id
)
from ..storage.database import DatabaseManager
from ..storage.file_store import FileStore


logger = logging.getLogger(__name__)


class SnapshotEngineError(Exception):
    """Base exception for snapshot engine operations."""
    pass


class SnapshotEngine(ISnapshotEngine):
    """Core engine for creating and managing project snapshots."""
    
    def __init__(self, project_root: Path, storage_root: Path):
        """Initialize snapshot engine.
        
        Args:
            project_root: Root directory of the project to snapshot
            storage_root: Root directory for snapshot storage
        """
        self.project_root = project_root.resolve()
        self.storage_root = storage_root
        
        # Initialize storage components
        self.db_manager = DatabaseManager(storage_root / "metadata.db")
        self.file_store = FileStore(storage_root)
        
        # Cache for file states to optimize incremental snapshots
        self._last_snapshot_states: Dict[Path, FileState] = {}
        self._last_snapshot_id: Optional[SnapshotId] = None
        
        logger.info(f"SnapshotEngine initialized for project: {project_root}")
    
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
        file_states = {}
        
        try:
            # Walk through all files in project
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
                        # Get file stats
                        stat = file_path.stat()
                        
                        # Calculate content hash
                        content_hash = self._calculate_file_hash(file_path)
                        
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
            
            logger.debug(f"Scanned {len(file_states)} files in project")
            return file_states
            
        except Exception as e:
            logger.error(f"Failed to scan project state: {e}")
            raise SnapshotEngineError(f"Project scan failed: {e}")
    
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
        
        return dir_name in ignore_patterns or dir_name.startswith('.')
    
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
        
        return suffix in ignore_extensions
    
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