"""Core data models and type definitions for Claude Rewind Tool."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import uuid


# Type aliases for better readability
SnapshotId = str
ContentHash = str


class ChangeType(Enum):
    """Types of file changes that can be tracked."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class DiffFormat(Enum):
    """Available diff output formats."""
    UNIFIED = "unified"
    SIDE_BY_SIDE = "side-by-side"
    PATCH = "patch"
    HTML = "html"


class RecoveryAction(Enum):
    """Actions that can be taken during error recovery."""
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    REPAIR = "repair"


@dataclass
class ActionContext:
    """Context information for a Claude Code action."""
    action_type: str
    timestamp: datetime
    prompt_context: str
    affected_files: List[Path]
    tool_name: str
    session_id: Optional[str] = None


@dataclass
class FileMetadata:
    """Metadata for a file in the project."""
    path: Path
    size: int
    modified_time: datetime
    permissions: int
    content_hash: ContentHash


@dataclass
class FileState:
    """Complete state information for a file."""
    path: Path
    content_hash: ContentHash
    size: int
    modified_time: datetime
    permissions: int
    exists: bool = True


@dataclass
class LineChange:
    """Represents a change to a specific line in a file."""
    line_number: int
    change_type: ChangeType
    content: str
    context: str


@dataclass
class FileChange:
    """Represents changes to a file between snapshots."""
    path: Path
    change_type: ChangeType
    before_hash: Optional[ContentHash]
    after_hash: Optional[ContentHash]
    line_changes: List[LineChange]


@dataclass
class SnapshotMetadata:
    """Metadata for a project snapshot."""
    id: SnapshotId
    timestamp: datetime
    action_type: str
    prompt_context: str
    files_affected: List[Path]
    total_size: int
    compression_ratio: float
    parent_snapshot: Optional[SnapshotId] = None
    bookmark_name: Optional[str] = None


@dataclass
class Snapshot:
    """Complete snapshot of project state."""
    id: SnapshotId
    timestamp: datetime
    metadata: SnapshotMetadata
    file_states: Dict[Path, FileState]


@dataclass
class ProjectState:
    """Current state of the entire project."""
    root_path: Path
    git_commit: Optional[str]
    file_tree: Dict[Path, FileMetadata]
    total_files: int
    total_size: int


@dataclass
class RollbackOptions:
    """Options for rollback operations."""
    selective_files: Optional[List[Path]] = None
    preserve_manual_changes: bool = True
    create_backup: bool = True
    dry_run: bool = False


@dataclass
class FileConflict:
    """Represents a conflict during rollback."""
    file_path: Path
    current_hash: ContentHash
    target_hash: ContentHash
    conflict_type: str
    description: str


@dataclass
class RollbackPreview:
    """Preview of what a rollback operation will do."""
    files_to_restore: List[Path]
    files_to_delete: List[Path]
    conflicts: List[FileConflict]
    estimated_changes: int


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    files_restored: List[Path]
    files_deleted: List[Path]
    conflicts_resolved: List[FileConflict]
    errors: List[str]


@dataclass
class ConflictResolution:
    """Resolution strategy for file conflicts."""
    file_path: Path
    resolution_type: str  # "keep_current", "use_snapshot", "merge"
    merged_content: Optional[str] = None


@dataclass
class TimelineFilters:
    """Filters for timeline navigation."""
    date_range: Optional[Tuple[datetime, datetime]] = None
    action_types: Optional[List[str]] = None
    file_patterns: Optional[List[str]] = None
    bookmarked_only: bool = False


@dataclass
class ValidationReport:
    """Report from system integrity validation."""
    is_valid: bool
    corrupted_snapshots: List[SnapshotId]
    missing_files: List[Path]
    database_issues: List[str]
    repair_suggestions: List[str]


@dataclass
class RepairResult:
    """Result of storage repair operation."""
    success: bool
    repaired_snapshots: List[SnapshotId]
    removed_corrupted: List[SnapshotId]
    errors: List[str]


def generate_snapshot_id() -> SnapshotId:
    """Generate a unique snapshot ID."""
    return f"cr_{uuid.uuid4().hex[:8]}"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"session_{uuid.uuid4().hex[:12]}"