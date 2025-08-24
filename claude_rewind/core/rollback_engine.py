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
    
    def preview_selective_rollback(self, target_snapshot: SnapshotId, 
                                  selected_files: List[Path]) -> RollbackPreview:
        """Preview rollback for specific files only.
        
        Args:
            target_snapshot: Snapshot to rollback to
            selected_files: List of files to rollback
            
        Returns:
            Preview of selective rollback operation
        """
        options = RollbackOptions(
            selective_files=selected_files,
            preserve_manual_changes=True,
            create_backup=True,
            dry_run=True
        )
        
        return self.preview_rollback(target_snapshot, options)
    
    def execute_selective_rollback(self, target_snapshot: SnapshotId, 
                                  selected_files: List[Path],
                                  preserve_changes: bool = True) -> RollbackResult:
        """Execute rollback for specific files only.
        
        Args:
            target_snapshot: Snapshot to rollback to
            selected_files: List of files to rollback
            preserve_changes: Whether to preserve manual changes
            
        Returns:
            Result of selective rollback operation
        """
        options = RollbackOptions(
            selective_files=selected_files,
            preserve_manual_changes=preserve_changes,
            create_backup=True,
            dry_run=False
        )
        
        return self.execute_rollback(target_snapshot, options)
    
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
        """Resolve conflicts during rollback using smart resolution strategies.
        
        Args:
            conflicts: List of file conflicts
            
        Returns:
            List of conflict resolutions
        """
        resolutions = []
        
        for conflict in conflicts:
            resolution = self._resolve_single_conflict(conflict)
            resolutions.append(resolution)
            logger.debug(f"Resolved conflict for {conflict.file_path}: {resolution.resolution_type}")
        
        return resolutions
    
    def _resolve_single_conflict(self, conflict: FileConflict) -> ConflictResolution:
        """Resolve a single file conflict using smart strategies.
        
        Args:
            conflict: File conflict to resolve
            
        Returns:
            Conflict resolution
        """
        if conflict.conflict_type == "content_mismatch":
            # Try three-way merge for content conflicts
            return self._resolve_content_conflict(conflict)
        elif conflict.conflict_type == "file_added":
            # Keep newly added files by default
            return ConflictResolution(
                file_path=conflict.file_path,
                resolution_type="keep_current"
            )
        elif conflict.conflict_type == "file_deleted":
            # Ask user or use heuristics for deleted files
            return self._resolve_deletion_conflict(conflict)
        else:
            # Default to snapshot version for unknown conflicts
            return ConflictResolution(
                file_path=conflict.file_path,
                resolution_type="use_snapshot"
            )
    
    def _resolve_content_conflict(self, conflict: FileConflict) -> ConflictResolution:
        """Resolve content conflicts using three-way merge.
        
        Args:
            conflict: Content conflict to resolve
            
        Returns:
            Conflict resolution with merged content if possible
        """
        try:
            # Get current file content
            current_file = self.project_root / conflict.file_path
            if not current_file.exists():
                # File was deleted, use snapshot version
                return ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="use_snapshot"
                )
            
            current_content = current_file.read_text(encoding='utf-8', errors='ignore')
            
            # Get snapshot content
            snapshot_content = self.storage_manager.load_file_content(conflict.target_hash)
            if snapshot_content is None:
                # Can't get snapshot content, keep current
                return ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="keep_current"
                )
            
            snapshot_text = snapshot_content.decode('utf-8', errors='ignore')
            
            # Try to find a common ancestor (base version)
            # For now, we'll use a simple heuristic approach
            base_content = self._find_base_content(conflict.file_path, current_content, snapshot_text)
            
            if base_content is not None:
                # Attempt three-way merge
                merged_content = self._three_way_merge(base_content, current_content, snapshot_text)
                
                if merged_content is not None:
                    return ConflictResolution(
                        file_path=conflict.file_path,
                        resolution_type="merge",
                        merged_content=merged_content
                    )
            
            # If merge fails, analyze the changes to make a smart decision
            return self._analyze_and_resolve_conflict(current_content, snapshot_text, conflict)
            
        except Exception as e:
            logger.warning(f"Error resolving content conflict for {conflict.file_path}: {e}")
            # Fallback to keeping current version
            return ConflictResolution(
                file_path=conflict.file_path,
                resolution_type="keep_current"
            )
    
    def _resolve_deletion_conflict(self, conflict: FileConflict) -> ConflictResolution:
        """Resolve conflicts involving file deletion.
        
        Args:
            conflict: Deletion conflict to resolve
            
        Returns:
            Conflict resolution
        """
        current_file = self.project_root / conflict.file_path
        
        if current_file.exists():
            # File exists now but was deleted in snapshot
            # Check if it's been significantly modified
            current_content = current_file.read_text(encoding='utf-8', errors='ignore')
            
            # Simple heuristic: if file is small or looks like a generated file, delete it
            if len(current_content.strip()) < 50 or self._looks_like_generated_file(conflict.file_path):
                return ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="use_snapshot"  # Delete the file
                )
            else:
                # Keep the file if it has substantial content
                return ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="keep_current"
                )
        else:
            # File doesn't exist, no conflict
            return ConflictResolution(
                file_path=conflict.file_path,
                resolution_type="use_snapshot"
            )
    
    def _find_base_content(self, file_path: Path, current_content: str, snapshot_content: str) -> Optional[str]:
        """Find the common ancestor content for three-way merge.
        
        This is a simplified implementation. In a full system, this would
        look at git history or previous snapshots to find the actual base.
        
        Args:
            file_path: Path to the file
            current_content: Current file content
            snapshot_content: Snapshot file content
            
        Returns:
            Base content if found, None otherwise
        """
        # Simple heuristic: if the files are very similar, use the shorter one as base
        current_lines = current_content.splitlines()
        snapshot_lines = snapshot_content.splitlines()
        
        # Calculate similarity
        common_lines = set(current_lines) & set(snapshot_lines)
        total_lines = len(set(current_lines) | set(snapshot_lines))
        
        if total_lines == 0:
            return ""
        
        similarity = len(common_lines) / total_lines
        
        if similarity > 0.7:  # If files are 70% similar
            # Use the shorter version as a rough approximation of the base
            if len(current_lines) < len(snapshot_lines):
                return current_content
            else:
                return snapshot_content
        
        return None
    
    def _three_way_merge(self, base_content: str, current_content: str, snapshot_content: str) -> Optional[str]:
        """Perform three-way merge of file contents.
        
        Args:
            base_content: Common ancestor content
            current_content: Current file content
            snapshot_content: Snapshot file content
            
        Returns:
            Merged content if successful, None if conflicts cannot be resolved
        """
        try:
            # Simple line-based three-way merge
            base_lines = base_content.splitlines()
            current_lines = current_content.splitlines()
            snapshot_lines = snapshot_content.splitlines()
            
            # Find changes from base to current and base to snapshot
            current_changes = self._compute_line_changes(base_lines, current_lines)
            snapshot_changes = self._compute_line_changes(base_lines, snapshot_lines)
            
            # Check for conflicting changes
            if self._have_conflicting_changes(current_changes, snapshot_changes):
                return None  # Cannot auto-merge
            
            # Apply both sets of changes
            merged_lines = base_lines.copy()
            
            # Apply changes in reverse order to maintain line numbers
            all_changes = sorted(current_changes + snapshot_changes, key=lambda x: x[0], reverse=True)
            
            for line_num, change_type, content in all_changes:
                if change_type == "insert":
                    merged_lines.insert(line_num, content)
                elif change_type == "delete":
                    if line_num < len(merged_lines):
                        del merged_lines[line_num]
                elif change_type == "modify":
                    if line_num < len(merged_lines):
                        merged_lines[line_num] = content
            
            return "\n".join(merged_lines)
            
        except Exception as e:
            logger.warning(f"Three-way merge failed: {e}")
            return None
    
    def _compute_line_changes(self, base_lines: List[str], target_lines: List[str]) -> List[Tuple[int, str, str]]:
        """Compute line-level changes between base and target.
        
        Args:
            base_lines: Base file lines
            target_lines: Target file lines
            
        Returns:
            List of changes as (line_number, change_type, content) tuples
        """
        import difflib
        
        changes = []
        matcher = difflib.SequenceMatcher(None, base_lines, target_lines)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'delete':
                for i in range(i1, i2):
                    changes.append((i, "delete", ""))
            elif tag == 'insert':
                for j in range(j1, j2):
                    changes.append((i1, "insert", target_lines[j]))
            elif tag == 'replace':
                # Handle as delete + insert
                for i in range(i1, i2):
                    changes.append((i, "delete", ""))
                for j in range(j1, j2):
                    changes.append((i1, "insert", target_lines[j]))
        
        return changes
    
    def _have_conflicting_changes(self, changes1: List[Tuple[int, str, str]], 
                                 changes2: List[Tuple[int, str, str]]) -> bool:
        """Check if two sets of changes conflict with each other.
        
        Args:
            changes1: First set of changes
            changes2: Second set of changes
            
        Returns:
            True if changes conflict
        """
        # Simple conflict detection: changes affecting the same line
        lines1 = {change[0] for change in changes1}
        lines2 = {change[0] for change in changes2}
        
        return bool(lines1 & lines2)
    
    def _analyze_and_resolve_conflict(self, current_content: str, snapshot_content: str, 
                                    conflict: FileConflict) -> ConflictResolution:
        """Analyze content differences and make a smart resolution decision.
        
        Args:
            current_content: Current file content
            snapshot_content: Snapshot file content
            conflict: The conflict being resolved
            
        Returns:
            Conflict resolution
        """
        # Analyze the nature of changes
        current_lines = current_content.splitlines()
        snapshot_lines = snapshot_content.splitlines()
        
        # Check if current version just has additions at the end
        if len(current_lines) > len(snapshot_lines):
            if current_lines[:len(snapshot_lines)] == snapshot_lines:
                # Current version just has additions, keep current
                return ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="keep_current"
                )
        
        # Check if snapshot version just has additions at the end
        if len(snapshot_lines) > len(current_lines):
            if snapshot_lines[:len(current_lines)] == current_lines:
                # Snapshot version just has additions, use snapshot
                return ConflictResolution(
                    file_path=conflict.file_path,
                    resolution_type="use_snapshot"
                )
        
        # Check for comment-only changes
        if self._only_comments_changed(current_lines, snapshot_lines):
            # Keep current version if only comments changed
            return ConflictResolution(
                file_path=conflict.file_path,
                resolution_type="keep_current"
            )
        
        # Default to keeping current version for manual changes
        return ConflictResolution(
            file_path=conflict.file_path,
            resolution_type="keep_current"
        )
    
    def _looks_like_generated_file(self, file_path: Path) -> bool:
        """Check if a file looks like it was generated automatically.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file appears to be generated
        """
        path_str = str(file_path).lower()
        
        # Common patterns for generated files
        generated_patterns = [
            '__pycache__', '.pyc', '.pyo', '.egg-info',
            'node_modules', '.git', '.DS_Store',
            'build/', 'dist/', 'target/',
            '.min.js', '.min.css'
        ]
        
        return any(pattern in path_str for pattern in generated_patterns)
    
    def _only_comments_changed(self, lines1: List[str], lines2: List[str]) -> bool:
        """Check if only comments changed between two versions.
        
        Args:
            lines1: First version lines
            lines2: Second version lines
            
        Returns:
            True if only comments changed
        """
        # Remove comment lines and compare
        def remove_comments(lines):
            non_comment_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith('#') and not stripped.startswith('//') and stripped:
                    non_comment_lines.append(line)
            return non_comment_lines
        
        non_comment1 = remove_comments(lines1)
        non_comment2 = remove_comments(lines2)
        
        return non_comment1 == non_comment2
    
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
        """Detect if there's a conflict for a file using advanced heuristics.
        
        Args:
            file_path: Path to the file
            current_hash: Hash of current file content
            target_hash: Hash of target file content
            
        Returns:
            FileConflict if conflict detected, None otherwise
        """
        if current_hash == target_hash:
            return None  # No conflict if hashes match
        
        # Analyze the type and severity of conflict
        current_file = self.project_root / file_path
        
        if not current_file.exists():
            # File was deleted after snapshot
            return FileConflict(
                file_path=file_path,
                current_hash=current_hash,
                target_hash=target_hash,
                conflict_type="file_deleted",
                description=f"File {file_path} was deleted after snapshot"
            )
        
        try:
            current_content = current_file.read_text(encoding='utf-8', errors='ignore')
            
            # Get target content from storage
            target_content_bytes = self.storage_manager.load_file_content(target_hash)
            if target_content_bytes is None:
                # Can't compare, assume conflict
                return FileConflict(
                    file_path=file_path,
                    current_hash=current_hash,
                    target_hash=target_hash,
                    conflict_type="content_mismatch",
                    description=f"File {file_path} has been modified (cannot retrieve snapshot version)"
                )
            
            target_content = target_content_bytes.decode('utf-8', errors='ignore')
            
            # Analyze the nature of changes
            conflict_severity = self._analyze_conflict_severity(current_content, target_content)
            
            if conflict_severity == "minor":
                # Minor changes might not need user intervention
                return None
            
            # Determine conflict type based on analysis
            conflict_type = self._determine_conflict_type(current_content, target_content)
            description = self._generate_conflict_description(file_path, current_content, target_content, conflict_type)
            
            return FileConflict(
                file_path=file_path,
                current_hash=current_hash,
                target_hash=target_hash,
                conflict_type=conflict_type,
                description=description
            )
            
        except Exception as e:
            logger.warning(f"Error analyzing conflict for {file_path}: {e}")
            # Fallback to basic conflict
            return FileConflict(
                file_path=file_path,
                current_hash=current_hash,
                target_hash=target_hash,
                conflict_type="content_mismatch",
                description=f"File {file_path} has been modified since snapshot"
            )
    
    def _analyze_conflict_severity(self, current_content: str, target_content: str) -> str:
        """Analyze the severity of a content conflict.
        
        Args:
            current_content: Current file content
            target_content: Target file content
            
        Returns:
            Severity level: "minor", "moderate", or "major"
        """
        current_lines = current_content.splitlines()
        target_lines = target_content.splitlines()
        
        # Calculate similarity
        import difflib
        similarity = difflib.SequenceMatcher(None, current_lines, target_lines).ratio()
        
        if similarity > 0.95:
            return "minor"  # Very similar, likely whitespace or comment changes
        elif similarity > 0.8:
            return "moderate"  # Some changes but mostly similar
        else:
            return "major"  # Significant differences
    
    def _determine_conflict_type(self, current_content: str, target_content: str) -> str:
        """Determine the type of conflict based on content analysis.
        
        Args:
            current_content: Current file content
            target_content: Target file content
            
        Returns:
            Conflict type string
        """
        current_lines = current_content.splitlines()
        target_lines = target_content.splitlines()
        
        # Check if it's just additions (current has more lines)
        if len(current_lines) > len(target_lines):
            # Check if target lines are a prefix of current lines
            matches = True
            for i, target_line in enumerate(target_lines):
                if i >= len(current_lines) or current_lines[i] != target_line:
                    matches = False
                    break
            
            if matches:
                return "additions_only"
        
        # Check if it's just deletions (target has more lines)
        if len(target_lines) > len(current_lines):
            # Check if current lines are a prefix of target lines
            matches = True
            for i, current_line in enumerate(current_lines):
                if i >= len(target_lines) or target_lines[i] != current_line:
                    matches = False
                    break
            
            if matches:
                return "deletions_only"
        
        # Check if only comments changed
        if self._only_comments_changed(current_lines, target_lines):
            return "comments_only"
        
        # Check if only whitespace changed
        if self._only_whitespace_changed(current_content, target_content):
            return "whitespace_only"
        
        # Default to content mismatch
        return "content_mismatch"
    
    def _generate_conflict_description(self, file_path: Path, current_content: str, 
                                     target_content: str, conflict_type: str) -> str:
        """Generate a human-readable description of the conflict.
        
        Args:
            file_path: Path to the file
            current_content: Current file content
            target_content: Target file content
            conflict_type: Type of conflict
            
        Returns:
            Human-readable conflict description
        """
        current_lines = len(current_content.splitlines())
        target_lines = len(target_content.splitlines())
        
        if conflict_type == "additions_only":
            added_lines = current_lines - target_lines
            return f"File {file_path} has {added_lines} additional lines"
        elif conflict_type == "deletions_only":
            deleted_lines = target_lines - current_lines
            return f"File {file_path} is missing {deleted_lines} lines from snapshot"
        elif conflict_type == "comments_only":
            return f"File {file_path} has only comment changes"
        elif conflict_type == "whitespace_only":
            return f"File {file_path} has only whitespace changes"
        else:
            line_diff = abs(current_lines - target_lines)
            return f"File {file_path} has been modified ({line_diff} line difference)"
    
    def _only_whitespace_changed(self, content1: str, content2: str) -> bool:
        """Check if only whitespace changed between two versions.
        
        Args:
            content1: First version content
            content2: Second version content
            
        Returns:
            True if only whitespace changed
        """
        # Normalize whitespace and compare
        normalized1 = ' '.join(content1.split())
        normalized2 = ' '.join(content2.split())
        
        return normalized1 == normalized2
    
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