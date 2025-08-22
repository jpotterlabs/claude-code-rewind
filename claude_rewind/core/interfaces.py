"""Core interfaces and abstract base classes for Claude Rewind Tool."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

from .models import (
    ActionContext, Snapshot, SnapshotId, SnapshotMetadata, FileState,
    RollbackOptions, RollbackPreview, RollbackResult, FileConflict,
    ConflictResolution, TimelineFilters, DiffFormat, ValidationReport,
    RepairResult, RecoveryAction
)


class ISnapshotEngine(ABC):
    """Interface for snapshot creation and management."""
    
    @abstractmethod
    def create_snapshot(self, context: ActionContext) -> SnapshotId:
        """Create a new snapshot of the current project state."""
        pass
    
    @abstractmethod
    def get_snapshot(self, snapshot_id: SnapshotId) -> Optional[Snapshot]:
        """Retrieve a specific snapshot by ID."""
        pass
    
    @abstractmethod
    def list_snapshots(self, filters: Optional[TimelineFilters] = None) -> List[SnapshotMetadata]:
        """List all snapshots with optional filtering."""
        pass
    
    @abstractmethod
    def delete_snapshot(self, snapshot_id: SnapshotId) -> bool:
        """Delete a specific snapshot."""
        pass


class IStorageManager(ABC):
    """Interface for persistent storage operations."""
    
    @abstractmethod
    def store_snapshot(self, snapshot: Snapshot) -> bool:
        """Store a snapshot to persistent storage."""
        pass
    
    @abstractmethod
    def load_snapshot(self, snapshot_id: SnapshotId) -> Optional[Snapshot]:
        """Load a snapshot from persistent storage."""
        pass
    
    @abstractmethod
    def store_file_content(self, content_hash: str, content: bytes) -> bool:
        """Store file content with deduplication."""
        pass
    
    @abstractmethod
    def load_file_content(self, content_hash: str) -> Optional[bytes]:
        """Load file content by hash."""
        pass
    
    @abstractmethod
    def cleanup_old_snapshots(self, keep_count: int) -> List[SnapshotId]:
        """Remove old snapshots, keeping the specified number."""
        pass
    
    @abstractmethod
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage usage statistics."""
        pass


class IRollbackEngine(ABC):
    """Interface for rollback operations."""
    
    @abstractmethod
    def preview_rollback(self, target_snapshot: SnapshotId, 
                        options: RollbackOptions) -> RollbackPreview:
        """Preview what a rollback operation would do."""
        pass
    
    @abstractmethod
    def execute_rollback(self, target_snapshot: SnapshotId, 
                        options: RollbackOptions) -> RollbackResult:
        """Execute a rollback operation."""
        pass
    
    @abstractmethod
    def resolve_conflicts(self, conflicts: List[FileConflict]) -> List[ConflictResolution]:
        """Resolve conflicts during rollback."""
        pass


class IDiffViewer(ABC):
    """Interface for diff viewing capabilities."""
    
    @abstractmethod
    def show_snapshot_diff(self, snapshot_id: SnapshotId, 
                          format: DiffFormat = DiffFormat.UNIFIED) -> str:
        """Show diff for a specific snapshot."""
        pass
    
    @abstractmethod
    def show_file_diff(self, file_path: Path, 
                      before_snapshot: SnapshotId, 
                      after_snapshot: SnapshotId,
                      format: DiffFormat = DiffFormat.UNIFIED) -> str:
        """Show diff for a specific file between snapshots."""
        pass
    
    @abstractmethod
    def export_diff(self, snapshot_id: SnapshotId, 
                   format: DiffFormat) -> str:
        """Export diff in specified format."""
        pass


class ITimelineManager(ABC):
    """Interface for timeline navigation and management."""
    
    @abstractmethod
    def show_interactive_timeline(self) -> None:
        """Display interactive timeline interface."""
        pass
    
    @abstractmethod
    def filter_snapshots(self, filters: TimelineFilters) -> List[SnapshotMetadata]:
        """Filter snapshots based on criteria."""
        pass
    
    @abstractmethod
    def bookmark_snapshot(self, snapshot_id: SnapshotId, name: str) -> bool:
        """Add a bookmark to a snapshot."""
        pass
    
    @abstractmethod
    def search_snapshots(self, query: str) -> List[SnapshotMetadata]:
        """Search snapshots by content or metadata."""
        pass


class IClaudeHookManager(ABC):
    """Interface for Claude Code integration hooks."""
    
    @abstractmethod
    def register_pre_action_hook(self, callback: Callable[[ActionContext], None]) -> None:
        """Register a callback to be called before Claude actions."""
        pass
    
    @abstractmethod
    def register_post_action_hook(self, callback: Callable[[ActionContext], None]) -> None:
        """Register a callback to be called after Claude actions."""
        pass
    
    @abstractmethod
    def get_current_action_context(self) -> Optional[ActionContext]:
        """Get context for the currently executing action."""
        pass
    
    @abstractmethod
    def start_monitoring(self) -> bool:
        """Start monitoring Claude Code actions."""
        pass
    
    @abstractmethod
    def stop_monitoring(self) -> bool:
        """Stop monitoring Claude Code actions."""
        pass


class IErrorRecovery(ABC):
    """Interface for error handling and recovery."""
    
    @abstractmethod
    def handle_snapshot_error(self, error: Exception) -> RecoveryAction:
        """Handle errors during snapshot creation."""
        pass
    
    @abstractmethod
    def repair_corrupted_storage(self) -> RepairResult:
        """Attempt to repair corrupted storage."""
        pass
    
    @abstractmethod
    def validate_system_integrity(self) -> ValidationReport:
        """Validate the integrity of the entire system."""
        pass


class IConfigManager(ABC):
    """Interface for configuration management."""
    
    @abstractmethod
    def load_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """Load configuration from file."""
        pass
    
    @abstractmethod
    def save_config(self, config: Dict[str, Any], config_path: Optional[Path] = None) -> bool:
        """Save configuration to file."""
        pass
    
    @abstractmethod
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration and return any errors."""
        pass