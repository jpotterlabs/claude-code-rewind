"""Context object for hook system."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

@dataclass
class HookContext:
    """Context information passed to hooks."""
    
    action_type: str
    files: List[Path]
    project_root: Path
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_cancelled: bool = False
    modifications: Dict[Path, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    
    def add_error(self, error: str) -> None:
        """Add an error message to the context."""
        self.errors.append(error)
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def add_modification(self, file: Path, modification: Any) -> None:
        """Add a modification for a file."""
        self.modifications[file] = modification
    
    def cancel(self, reason: str) -> None:
        """Cancel the action with a reason."""
        self.is_cancelled = True
        self.add_error(f"Action cancelled: {reason}")