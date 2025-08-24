"""Rollback engine for restoring project state from snapshots."""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime

from .interfaces import IRollbackEngine, IStorageManager
from .models import (
    SnapshotId, RollbackOptions, RollbackPreview, RollbackResult,
    FileConflict, ConflictResolution, FileState, ChangeType
)


logger = logging.getLogger(__name__)


class RollbackError(Exception):
    """Base exception for rollback operations."""
    pass


class ConflictError(RollbackError):
    """Exception raised when conflicts cannot be resolved automatically."""
    pass


class RollbackEngine(IRollbackEngine):
    """Engine for executing rollback operations with conflict resolution."""
    
    def __init__(self, storage_manager: IStorageManager, project_root: Path):
        """Initialize rollback engine.
        
        Args:
            storage_manager: Storage manager for snapshot operations
            project_root: Root directory of the project
        """
        self.storage_manager = storage_manager
        self.project_root = project_root
        self.backup_dir = project_root / ".claude-rewind" / "backups"
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"RollbackEngine initialized for project: {project_root}")
    
    def preview_rollback(self, target_snapshot: SnapshotId, 
                        options: RollbackOptions) -> RollbackPreview:
        """Preview what a rollback operation would do.
        
        Args:
            target_snapshot: Snapshot to rollback to
            options: Rollback options
            
        Returns:
            Preview of rollback operation
            
        Raises:
            RollbackError: If preview cannot be generated
        """
        logger.info(f"Generating rollback preview for snapshot: {target_snapshot}")
        
        try:
            # Load target snapshot
            snapshot = self.storage_manager.load_snapshot(target_snapshot)
            if not snapshot:
                raise RollbackError(f"Snapshot not found: {target_snapshot}")
            
            # Get current project state
            current_state = self._get_current_project_state(options.selective_files)
            
            # Analyze differences
            files_to_restore = []
            files_to_delete = []
            conflicts = []
            
            # Check files in snapshot
            for file_path, target_file_state in snapshot.file_states.items():
                # Skip if selective files specified and this file not included
                if options.selective_files and file_path not in options.selective_files:
                    continue
                
                current_file_path = self.project_root / file_path
                
                if target_file_state.exists:
                    # File should exist in target state
                    if current_file_path.exists():
                        # File exists - check for conflicts
                        current_content = current_file_path.read_bytes()
                        current_hash = self._calculate_hash(current_content)
                        
                        if current_hash != target_file_state.content_hash:
                            # File has changed - potential conflict
                            if options.preserve_manual_changes:
                                # Check if this is a manual change or Claude change
                                conflict = self._detect_conflict(
                                    file_path, current_hash, target_file_state.content_hash
                                )
                                if conflict:
                                    conflicts.append(conflict)
                                else:
                                    files_to_restore.append(file_path)
                            else:
                                files_to_restore.append(file_path)
                    else:
                        # File doesn't exist but should - restore it
                        files_to_restore.append(file_path)
                else:
                    # File should not exist in target state
                    if current_file_path.exists():
                        files_to_delete.append(file_path)
            
            # Check for files that exist now but not in snapshot
            if not options.selective_files:
                for current_path in current_state:
                    if current_path not in snapshot.file_states:
                        # File exists now but not in snapshot - should be deleted
                        files_to_delete.append(current_path)
            
            estimated_changes = len(files_to_restore) + len(files_to_delete)
            
            preview = RollbackPreview(
                files_to_restore=files_to_restore,
                files_to_delete=files_to_delete,
                conflicts=conflicts,
                estimated_changes=estimated_changes
            )
            
            logger.info(f"Rollback preview: {estimated_changes} changes, {len(conflicts)} conflicts")
            return preview
            
        except Exception as e:
            logger.error(f"Failed to generate rollback preview: {e}")
            raise RollbackError(f"Failed to generate rollback preview: {e}")
    
    def execute_rollback(self, target_snapshot: SnapshotId, 
                        options: RollbackOptions) -> RollbackResult:
        """Execute a rollback operation.
        
        Args:
            target_snapshot: Snapshot to rollback to
            options: Rollback options
            
        Returns:
            Result of rollback operation
            
        Raises:
            RollbackError: If rollback fails
        """
        logger.info(f"Executing rollback to snapshot: {target_snapshot}")
        
        if options.dry_run:
            logger.info("Dry run mode - no actual changes will be made")
            preview = self.preview_rollback(target_snapshot, options)
            return RollbackResult(
                success=True,
                files_restored=[],
                files_deleted=[],
                conflicts_resolved=[],
                errors=[f"Dry run: Would restore {len(preview.files_to_restore)} files, "
                       f"delete {len(preview.files_to_delete)} files, "
                       f"resolve {len(preview.conflicts)} conflicts"]
            )
        
        # Create backup if requested
        backup_id = None
        if options.create_backup:
            backup_id = self._create_backup()
            logger.info(f"Created backup: {backup_id}")
        
        files_restored = []
        files_deleted = []
        conflicts_resolved = []
        errors = []
        
        try:
            # Get rollback preview
            preview = self.preview_rollback(target_snapshot, options)
            
            # Handle conflicts first
            if preview.conflicts:
                if not options.preserve_manual_changes:
                    # Force rollback - treat conflicts as regular restores
                    preview.files_to_restore.extend([c.file_path for c in preview.conflicts])
                    preview.conflicts = []
                else:
                    # Resolve conflicts
                    resolutions = self.resolve_conflicts(preview.conflicts)
                    for resolution in resolutions:
                        try:
                            self._apply_conflict_resolution(resolution)
                            conflicts_resolved.append(resolution)
                        except Exception as e:
                            errors.append(f"Failed to resolve conflict for {resolution.file_path}: {e}")
            
            # Load target snapshot
            snapshot = self.storage_manager.load_snapshot(target_snapshot)
            if not snapshot:
                raise RollbackError(f"Snapshot not found: {target_snapshot}")
            
            # Restore files
            for file_path in preview.files_to_restore:
                try:
                    if file_path in snapshot.file_states:
                        target_file_state = snapshot.file_states[file_path]
                        self._restore_file(file_path, target_file_state)
                        files_restored.append(file_path)
                    else:
                        errors.append(f"File not found in snapshot: {file_path}")
                except Exception as e:
                    errors.append(f"Failed to restore {file_path}: {e}")
            
            # Delete files
            for file_path in preview.files_to_delete:
                try:
                    current_file_path = self.project_root / file_path
                    if current_file_path.exists():
                        current_file_path.unlink()
                        files_deleted.append(file_path)
                        logger.debug(f"Deleted file: {file_path}")
                except Exception as e:
                    errors.append(f"Failed to delete {file_path}: {e}")
            
            success = len(errors) == 0
            
            if success:
                logger.info(f"Rollback completed successfully: "
                           f"{len(files_restored)} restored, {len(files_deleted)} deleted")
            else:
                logger.warning(f"Rollback completed with {len(errors)} errors")
            
            return RollbackResult(
                success=success,
                files_restored=files_restored,
                files_deleted=files_deleted,
                conflicts_resolved=[c.file_path for c in conflicts_resolved],
                errors=errors
            )
            
        except Exception as e:
            # Rollback failed - restore from backup if available
            if backup_id and options.create_backup:
                try:
                    self._restore_from_backup(backup_id)
                    logger.info(f"Restored from backup due to rollback failure: {backup_id}")
                except Exception as backup_error:
                    logger.error(f"Failed to restore from backup: {backup_error}")
                    errors.append(f"Backup restoration failed: {backup_error}")
            
            logger.error(f"Rollback failed: {e}")
            return RollbackResult(
                success=False,
                files_restored=files_restored,
                files_deleted=files_deleted,
                conflicts_resolved=[c.file_path for c in conflicts_resolved],
                errors=errors + [f"Rollback failed: {e}"]
            )
    
    def resolve_conflicts(self, conflicts: List[FileConflict]) -> List[ConflictResolution]:
        """Resolve conflicts during rollback.
        
        Args:
            conflicts: List of file conflicts
            
        Returns:
            List of conflict resolutions
        """
        resolutions = []
        
        for conflict in conflicts:
            # For now, implement simple resolution strategy
            # In the future, this could be made interactive or configurable
            
            if conflict.conflict_type == "content_mismatch":
                # Default to keeping current version for manual changes
                resolution = ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="keep_current"
                )
            elif conflict.conflict_type == "file_added":
                # Keep newly added files by default
                resolution = ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="keep_current"
                )
            else:
                # Default to snapshot version
                resolution = ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="use_snapshot"
                )
            
            resolutions.append(resolution)
            logger.debug(f"Resolved conflict for {conflict.file_path}: {resolution.resolution_type}")
        
        return resolutions
    
    def _get_current_project_state(self, selective_files: Optional[List[Path]] = None) -> Dict[Path, str]:
        """Get current state of project files.
        
        Args:
            selective_files: Optional list of specific files to check
            
        Returns:
            Dictionary mapping file paths to content hashes
        """
        current_state = {}
        
        if selective_files:
            # Only check specified files
            for file_path in selective_files:
                full_path = self.project_root / file_path
                if full_path.exists() and full_path.is_file():
                    content = full_path.read_bytes()
                    current_state[file_path] = self._calculate_hash(content)
        else:
            # Scan entire project (excluding .claude-rewind directory)
            for file_path in self._scan_project_files():
                try:
                    content = file_path.read_bytes()
                    relative_path = file_path.relative_to(self.project_root)
                    current_state[relative_path] = self._calculate_hash(content)
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")
        
        return current_state
    
    def _scan_project_files(self) -> List[Path]:
        """Scan project directory for files, excluding .claude-rewind.
        
        Returns:
            List of file paths
        """
        files = []
        
        def should_exclude(path: Path) -> bool:
            """Check if path should be excluded from scanning."""
            parts = path.parts
            return (
                '.claude-rewind' in parts or
                '.git' in parts or
                '__pycache__' in parts or
                path.name.startswith('.')
            )
        
        for file_path in self.project_root.rglob('*'):
            if file_path.is_file() and not should_exclude(file_path):
                files.append(file_path)
        
        return files
    
    def _calculate_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of content."""
        import hashlib
        return hashlib.sha256(content).hexdigest()
    
    def _detect_conflict(self, file_path: Path, current_hash: str, 
                        target_hash: str) -> Optional[FileConflict]:
        """Detect if there's a conflict for a file.
        
        Args:
            file_path: Path to the file
            current_hash: Hash of current file content
            target_hash: Hash of target file content
            
        Returns:
            FileConflict if conflict detected, None otherwise
        """
        # Simple conflict detection - in practice this could be more sophisticated
        # by checking if changes were made after the last Claude action
        
        if current_hash != target_hash:
            return FileConflict(
                file_path=file_path,
                current_hash=current_hash,
                target_hash=target_hash,
                conflict_type="content_mismatch",
                description=f"File {file_path} has been modified since snapshot"
            )
        
        return None
    
    def _restore_file(self, file_path: Path, target_file_state: FileState) -> None:
        """Restore a single file from snapshot.
        
        Args:
            file_path: Path to the file
            target_file_state: Target file state from snapshot
            
        Raises:
            RollbackError: If restoration fails
        """
        full_path = self.project_root / file_path
        
        try:
            if not target_file_state.exists:
                # File should not exist - delete if present
                if full_path.exists():
                    full_path.unlink()
                    logger.debug(f"Deleted file: {file_path}")
                return
            
            # Retrieve content from storage
            content = self.storage_manager.load_file_content(target_file_state.content_hash)
            if content is None:
                raise RollbackError(f"Content not found for hash: {target_file_state.content_hash}")
            
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            full_path.write_bytes(content)
            
            # Restore permissions
            full_path.chmod(target_file_state.permissions)
            
            logger.debug(f"Restored file: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to restore {file_path}: {e}")
            raise RollbackError(f"Failed to restore {file_path}: {e}")
    
    def _apply_conflict_resolution(self, resolution: ConflictResolution) -> None:
        """Apply a conflict resolution.
        
        Args:
            resolution: Conflict resolution to apply
            
        Raises:
            RollbackError: If resolution fails
        """
        if resolution.resolution_type == "keep_current":
            # Do nothing - keep current version
            logger.debug(f"Keeping current version of {resolution.file_path}")
        elif resolution.resolution_type == "use_snapshot":
            # This would require loading the snapshot version
            # For now, just log - full implementation would restore from snapshot
            logger.debug(f"Using snapshot version of {resolution.file_path}")
        elif resolution.resolution_type == "merge" and resolution.merged_content:
            # Apply merged content
            full_path = self.project_root / resolution.file_path
            full_path.write_text(resolution.merged_content)
            logger.debug(f"Applied merged content to {resolution.file_path}")
        else:
            raise RollbackError(f"Unknown resolution type: {resolution.resolution_type}")
    
    def _create_backup(self) -> str:
        """Create a backup of current project state.
        
        Returns:
            Backup identifier
            
        Raises:
            RollbackError: If backup creation fails
        """
        backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_path = self.backup_dir / backup_id
        
        try:
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # Copy current project files (excluding .claude-rewind)
            for file_path in self._scan_project_files():
                relative_path = file_path.relative_to(self.project_root)
                backup_file_path = backup_path / relative_path
                
                # Create parent directories
                backup_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(file_path, backup_file_path)
            
            logger.info(f"Created backup: {backup_id}")
            return backup_id
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise RollbackError(f"Failed to create backup: {e}")
    
    def _restore_from_backup(self, backup_id: str) -> None:
        """Restore project state from backup.
        
        Args:
            backup_id: Backup identifier
            
        Raises:
            RollbackError: If restoration fails
        """
        backup_path = self.backup_dir / backup_id
        
        if not backup_path.exists():
            raise RollbackError(f"Backup not found: {backup_id}")
        
        try:
            # Remove current files (excluding .claude-rewind)
            for file_path in self._scan_project_files():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove {file_path}: {e}")
            
            # Restore files from backup
            for backup_file in backup_path.rglob('*'):
                if backup_file.is_file():
                    relative_path = backup_file.relative_to(backup_path)
                    target_path = self.project_root / relative_path
                    
                    # Create parent directories
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(backup_file, target_path)
            
            logger.info(f"Restored from backup: {backup_id}")
            
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")
            raise RollbackError(f"Failed to restore from backup: {e}")