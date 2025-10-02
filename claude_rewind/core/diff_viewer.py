"""Core diff viewing engine with multiple output formats and syntax highlighting."""

import difflib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.formatters import TerminalFormatter, Terminal256Formatter
    from pygments.util import ClassNotFound
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False

from ..core.interfaces import IDiffViewer, IStorageManager
from ..core.models import (
    SnapshotId, DiffFormat, FileChange, LineChange, ChangeType,
    SnapshotMetadata, Snapshot
)


logger = logging.getLogger(__name__)


class DiffViewerError(Exception):
    """Base exception for diff viewer operations."""
    pass


class DiffViewer(IDiffViewer):
    """Core diff engine with multiple output formats and syntax highlighting."""
    
    def __init__(self, storage_manager: IStorageManager, 
                 context_lines: int = 3, enable_colors: bool = True):
        """Initialize diff viewer.
        
        Args:
            storage_manager: Storage manager for retrieving snapshots
            context_lines: Number of context lines around changes
            enable_colors: Whether to enable syntax highlighting and colors
        """
        self.storage_manager = storage_manager
        self.context_lines = context_lines
        self.enable_colors = enable_colors
        
        # Initialize syntax highlighting if available
        self.syntax_highlighting = PYGMENTS_AVAILABLE and enable_colors
        if self.syntax_highlighting:
            # Use 256-color formatter for better colors in modern terminals
            self.formatter = Terminal256Formatter(style='monokai')
        
        logger.debug(f"DiffViewer initialized with context_lines={context_lines}, "
                    f"colors={enable_colors}, syntax_highlighting={self.syntax_highlighting}")

    def _should_filter_file(self, file_path: Path) -> bool:
        """Check if file should be filtered from diff output.

        Args:
            file_path: Path to check

        Returns:
            True if file should be filtered out
        """
        path_parts = file_path.parts

        # Filter out .claude-rewind directory
        if '.claude-rewind' in path_parts:
            return True

        # Filter out other common directories to ignore
        ignore_dirs = {
            '.git', '.svn', '.hg',  # Version control
            '__pycache__', '.pytest_cache',  # Python
            'node_modules', '.npm',  # Node.js
            '.venv', 'venv', 'env',  # Virtual environments
            'target', 'build', 'dist',  # Build outputs
        }

        for part in path_parts:
            if part in ignore_dirs or part.startswith('.'):
                return True

        # Filter out common files to ignore
        file_name = file_path.name
        if file_name.startswith('.'):
            return True

        ignore_extensions = {'.pyc', '.pyo', '.pyd', '.log', '.tmp', '.swp'}
        if file_path.suffix.lower() in ignore_extensions:
            return True

        return False

    def _get_lexer_for_file(self, file_path: Path) -> Any:
        """Get appropriate lexer for file based on extension.
        
        Args:
            file_path: Path to file
            
        Returns:
            Pygments lexer or TextLexer as fallback
        """
        if not self.syntax_highlighting:
            return None
        
        try:
            return get_lexer_for_filename(str(file_path))
        except ClassNotFound:
            return TextLexer()
    
    def _highlight_code(self, code: str, lexer: Any) -> str:
        """Apply syntax highlighting to code.
        
        Args:
            code: Code to highlight
            lexer: Pygments lexer
            
        Returns:
            Highlighted code or original if highlighting fails
        """
        if not self.syntax_highlighting or not lexer:
            return code
        
        try:
            return highlight(code, lexer, self.formatter).rstrip('\n')
        except Exception as e:
            logger.debug(f"Syntax highlighting failed: {e}")
            return code
    
    def _get_file_content(self, snapshot_id: SnapshotId, file_path: Path) -> Optional[str]:
        """Get file content from snapshot or current filesystem.

        Args:
            snapshot_id: Snapshot identifier or "current" for current filesystem state
            file_path: Path to file

        Returns:
            File content as string or None if file doesn't exist
        """
        try:
            # Handle "current" as special case - read from current filesystem
            if snapshot_id == "current":
                return self._get_current_file_content(file_path)

            snapshot = self.storage_manager.load_snapshot(snapshot_id)
            if not snapshot:
                raise DiffViewerError(f"Snapshot not found: {snapshot_id}")
            
            # Check if file exists in snapshot
            if file_path not in snapshot.file_states:
                return None
            
            file_state = snapshot.file_states[file_path]
            if not file_state.exists:
                return None
            
            # Get file content from storage
            content_bytes = self.storage_manager.load_file_content(file_state.content_hash)
            if content_bytes is None:
                raise DiffViewerError(f"Content not found for {file_path} in snapshot {snapshot_id}")
            
            # Try to decode as text
            try:
                return content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Handle binary files
                return f"<Binary file: {len(content_bytes)} bytes>"
            
        except Exception as e:
            logger.error(f"Failed to get file content for {file_path} in {snapshot_id}: {e}")
            raise DiffViewerError(f"Failed to get file content: {e}")
    
    def _get_current_file_content(self, file_path: Path) -> Optional[str]:
        """Get current file content from filesystem.
        
        Args:
            file_path: Path to file
            
        Returns:
            File content as string or None if file doesn't exist
        """
        try:
            if not file_path.exists():
                return None
            
            with open(file_path, 'rb') as f:
                content_bytes = f.read()
            
            # Try to decode as text
            try:
                return content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Handle binary files
                return f"<Binary file: {len(content_bytes)} bytes>"
            
        except Exception as e:
            logger.debug(f"Failed to read current file {file_path}: {e}")
            return None
    
    def _generate_unified_diff(self, before_content: Optional[str], 
                             after_content: Optional[str],
                             before_label: str, after_label: str,
                             file_path: Path) -> str:
        """Generate unified diff format.
        
        Args:
            before_content: Content before changes
            after_content: Content after changes
            before_label: Label for before version
            after_label: Label for after version
            file_path: Path to file for syntax highlighting
            
        Returns:
            Unified diff as string
        """
        # Handle None content (file creation/deletion)
        before_lines = before_content.splitlines(keepends=True) if before_content else []
        after_lines = after_content.splitlines(keepends=True) if after_content else []
        
        # Generate diff
        diff_lines = list(difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=before_label,
            tofile=after_label,
            n=self.context_lines
        ))
        
        if not diff_lines:
            return ""
        
        # Apply syntax highlighting to diff if enabled
        if self.syntax_highlighting:
            lexer = self._get_lexer_for_file(file_path)
            highlighted_lines = []
            
            for line in diff_lines:
                if line.startswith('+++') or line.startswith('---'):
                    # File headers - use bold
                    if self.enable_colors:
                        highlighted_lines.append(f"\033[1m{line}\033[0m")
                    else:
                        highlighted_lines.append(line)
                elif line.startswith('@@'):
                    # Hunk headers - use cyan
                    if self.enable_colors:
                        highlighted_lines.append(f"\033[36m{line}\033[0m")
                    else:
                        highlighted_lines.append(line)
                elif line.startswith('+'):
                    # Added lines - use green
                    content = line[1:]  # Remove + prefix
                    if lexer and content.strip():
                        highlighted_content = self._highlight_code(content, lexer)
                        if self.enable_colors:
                            highlighted_lines.append(f"\033[32m+{highlighted_content}\033[0m")
                        else:
                            highlighted_lines.append(f"+{highlighted_content}")
                    else:
                        if self.enable_colors:
                            highlighted_lines.append(f"\033[32m{line}\033[0m")
                        else:
                            highlighted_lines.append(line)
                elif line.startswith('-'):
                    # Removed lines - use red
                    content = line[1:]  # Remove - prefix
                    if lexer and content.strip():
                        highlighted_content = self._highlight_code(content, lexer)
                        if self.enable_colors:
                            highlighted_lines.append(f"\033[31m-{highlighted_content}\033[0m")
                        else:
                            highlighted_lines.append(f"-{highlighted_content}")
                    else:
                        if self.enable_colors:
                            highlighted_lines.append(f"\033[31m{line}\033[0m")
                        else:
                            highlighted_lines.append(line)
                else:
                    # Context lines - apply syntax highlighting only
                    if line.startswith(' '):
                        content = line[1:]  # Remove space prefix
                        if lexer and content.strip():
                            highlighted_content = self._highlight_code(content, lexer)
                            highlighted_lines.append(f" {highlighted_content}")
                        else:
                            highlighted_lines.append(line)
                    else:
                        # Other lines (like file headers)
                        highlighted_lines.append(line)
            
            return ''.join(highlighted_lines)
        else:
            return ''.join(diff_lines)
    
    def _generate_side_by_side_diff(self, before_content: Optional[str],
                                   after_content: Optional[str],
                                   before_label: str, after_label: str,
                                   file_path: Path, width: int = 80) -> str:
        """Generate side-by-side diff format.
        
        Args:
            before_content: Content before changes
            after_content: Content after changes
            before_label: Label for before version
            after_label: Label for after version
            file_path: Path to file for syntax highlighting
            width: Terminal width for formatting
            
        Returns:
            Side-by-side diff as string
        """
        # Handle None content
        before_lines = before_content.splitlines() if before_content else []
        after_lines = after_content.splitlines() if after_content else []
        
        # Calculate column width
        col_width = (width - 3) // 2  # 3 chars for separator
        
        # Get lexer for syntax highlighting
        lexer = self._get_lexer_for_file(file_path) if self.syntax_highlighting else None
        
        # Generate side-by-side comparison
        result_lines = []
        
        # Add headers
        header_sep = "=" * width
        result_lines.append(header_sep)
        result_lines.append(f"{before_label:<{col_width}} | {after_label}")
        result_lines.append(header_sep)
        
        # Use difflib.SequenceMatcher for better alignment
        matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Lines are the same
                for i in range(i1, i2):
                    line = before_lines[i]
                    if lexer:
                        line = self._highlight_code(line, lexer)
                    
                    # Truncate if too long
                    if len(line) > col_width:
                        line = line[:col_width-3] + "..."
                    
                    result_lines.append(f"{line:<{col_width}} | {line}")
            
            elif tag == 'delete':
                # Lines deleted from before
                for i in range(i1, i2):
                    line = before_lines[i]
                    if lexer:
                        line = self._highlight_code(line, lexer)
                    
                    if len(line) > col_width:
                        line = line[:col_width-3] + "..."
                    
                    if self.enable_colors:
                        colored_line = f"\033[31m{line}\033[0m"
                        result_lines.append(f"{colored_line:<{col_width+9}} | {'':>{col_width}}")
                    else:
                        result_lines.append(f"- {line:<{col_width-2}} | {'':>{col_width}}")
            
            elif tag == 'insert':
                # Lines added to after
                for j in range(j1, j2):
                    line = after_lines[j]
                    if lexer:
                        line = self._highlight_code(line, lexer)
                    
                    if len(line) > col_width:
                        line = line[:col_width-3] + "..."
                    
                    if self.enable_colors:
                        colored_line = f"\033[32m{line}\033[0m"
                        result_lines.append(f"{'':>{col_width}} | {colored_line}")
                    else:
                        result_lines.append(f"{'':>{col_width}} | + {line}")
            
            elif tag == 'replace':
                # Lines changed
                max_lines = max(i2 - i1, j2 - j1)
                
                for k in range(max_lines):
                    before_line = before_lines[i1 + k] if k < (i2 - i1) else ""
                    after_line = after_lines[j1 + k] if k < (j2 - j1) else ""
                    
                    if lexer:
                        if before_line:
                            before_line = self._highlight_code(before_line, lexer)
                        if after_line:
                            after_line = self._highlight_code(after_line, lexer)
                    
                    # Truncate if too long
                    if len(before_line) > col_width:
                        before_line = before_line[:col_width-3] + "..."
                    if len(after_line) > col_width:
                        after_line = after_line[:col_width-3] + "..."
                    
                    if self.enable_colors:
                        before_colored = f"\033[31m{before_line}\033[0m" if before_line else ""
                        after_colored = f"\033[32m{after_line}\033[0m" if after_line else ""
                        result_lines.append(f"{before_colored:<{col_width+9}} | {after_colored}")
                    else:
                        before_marked = f"- {before_line}" if before_line else ""
                        after_marked = f"+ {after_line}" if after_line else ""
                        result_lines.append(f"{before_marked:<{col_width}} | {after_marked}")
        
        return '\n'.join(result_lines)
    
    def _generate_patch_format(self, before_content: Optional[str],
                              after_content: Optional[str],
                              before_label: str, after_label: str,
                              file_path: Path) -> str:
        """Generate patch format suitable for git apply.
        
        Args:
            before_content: Content before changes
            after_content: Content after changes
            before_label: Label for before version
            after_label: Label for after version
            file_path: Path to file
            
        Returns:
            Patch format as string
        """
        # Handle None content
        before_lines = before_content.splitlines(keepends=True) if before_content else []
        after_lines = after_content.splitlines(keepends=True) if after_content else []
        
        # Generate unified diff without color
        diff_lines = list(difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=self.context_lines
        ))
        
        return ''.join(diff_lines)
    
    def show_snapshot_diff(self, snapshot_id: SnapshotId, 
                          format: DiffFormat = DiffFormat.UNIFIED) -> str:
        """Show diff for a specific snapshot against current state.
        
        Args:
            snapshot_id: Snapshot identifier
            format: Output format for diff
            
        Returns:
            Formatted diff string
        """
        try:
            snapshot = self.storage_manager.load_snapshot(snapshot_id)
            if not snapshot:
                raise DiffViewerError(f"Snapshot not found: {snapshot_id}")
            
            result_lines = []
            has_differences = False
            
            # Add header
            header = f"Diff for snapshot {snapshot_id} ({snapshot.metadata.action_type})"
            if format != DiffFormat.PATCH:
                if self.enable_colors:
                    result_lines.append(f"\033[1;34m{header}\033[0m")
                else:
                    result_lines.append(header)
                result_lines.append("=" * len(header))
                result_lines.append("")
            
            # Get all files that were affected, filtering out internal files
            affected_files = {
                f for f in snapshot.file_states.keys()
                if not self._should_filter_file(f)
            }
            
            # Also check current directory for files that might have been added since
            try:
                current_files = set()
                for file_path in Path.cwd().rglob('*'):
                    if file_path.is_file():
                        try:
                            relative_path = file_path.relative_to(Path.cwd())

                            # Filter out internal and hidden files/directories
                            if self._should_filter_file(relative_path):
                                continue

                            current_files.add(relative_path)
                        except ValueError:
                            # Skip files outside current directory
                            continue
                affected_files.update(current_files)
            except Exception as e:
                logger.debug(f"Failed to scan current directory: {e}")
            
            # Generate diff for each affected file
            for file_path in sorted(affected_files):
                snapshot_content = self._get_file_content(snapshot_id, file_path)
                current_content = self._get_current_file_content(file_path)
                
                # Skip if contents are identical
                if snapshot_content == current_content:
                    continue
                
                has_differences = True
                
                # Generate diff based on format
                before_label = f"{file_path} (snapshot {snapshot_id})"
                after_label = f"{file_path} (current)"
                
                if format == DiffFormat.UNIFIED:
                    diff_text = self._generate_unified_diff(
                        snapshot_content, current_content,
                        before_label, after_label, file_path
                    )
                elif format == DiffFormat.SIDE_BY_SIDE:
                    diff_text = self._generate_side_by_side_diff(
                        snapshot_content, current_content,
                        before_label, after_label, file_path
                    )
                elif format == DiffFormat.PATCH:
                    diff_text = self._generate_patch_format(
                        snapshot_content, current_content,
                        before_label, after_label, file_path
                    )
                else:
                    raise DiffViewerError(f"Unsupported diff format: {format}")
                
                if diff_text.strip():
                    if format != DiffFormat.PATCH:
                        result_lines.append(f"File: {file_path}")
                        result_lines.append("-" * 40)
                    result_lines.append(diff_text)
                    if format != DiffFormat.PATCH:
                        result_lines.append("")
            
            if not has_differences:
                return "No differences found."
            
            return '\n'.join(result_lines)
            
        except Exception as e:
            logger.error(f"Failed to generate snapshot diff: {e}")
            raise DiffViewerError(f"Failed to generate diff: {e}")
    
    def show_file_diff(self, file_path: Path, 
                      before_snapshot: SnapshotId, 
                      after_snapshot: SnapshotId,
                      format: DiffFormat = DiffFormat.UNIFIED) -> str:
        """Show diff for a specific file between snapshots.
        
        Args:
            file_path: Path to file
            before_snapshot: Before snapshot identifier
            after_snapshot: After snapshot identifier
            format: Output format for diff
            
        Returns:
            Formatted diff string
        """
        try:
            # Get file content from both snapshots
            before_content = self._get_file_content(before_snapshot, file_path)
            after_content = self._get_file_content(after_snapshot, file_path)
            
            # Check if contents are identical
            if before_content == after_content:
                return f"No differences found for {file_path} between snapshots."
            
            # Generate labels
            before_label = f"{file_path} (snapshot {before_snapshot})"
            after_label = f"{file_path} (snapshot {after_snapshot})"
            
            # Generate diff based on format
            if format == DiffFormat.UNIFIED:
                diff_text = self._generate_unified_diff(
                    before_content, after_content,
                    before_label, after_label, file_path
                )
            elif format == DiffFormat.SIDE_BY_SIDE:
                diff_text = self._generate_side_by_side_diff(
                    before_content, after_content,
                    before_label, after_label, file_path
                )
            elif format == DiffFormat.PATCH:
                diff_text = self._generate_patch_format(
                    before_content, after_content,
                    before_label, after_label, file_path
                )
            else:
                raise DiffViewerError(f"Unsupported diff format: {format}")
            
            # Add header for non-patch formats
            if format != DiffFormat.PATCH and diff_text.strip():
                header = f"Diff for {file_path} between snapshots {before_snapshot} and {after_snapshot}"
                if self.enable_colors:
                    header = f"\033[1;34m{header}\033[0m"
                
                header_clean = header.replace('\033[1;34m', '').replace('\033[0m', '')
                return f"{header}\n{'=' * len(header_clean)}\n\n{diff_text}"
            
            return diff_text
            
        except Exception as e:
            logger.error(f"Failed to generate file diff: {e}")
            raise DiffViewerError(f"Failed to generate file diff: {e}")
    
    def export_diff(self, snapshot_id: SnapshotId, 
                   format: DiffFormat) -> str:
        """Export diff in specified format.
        
        Args:
            snapshot_id: Snapshot identifier
            format: Export format
            
        Returns:
            Formatted diff string suitable for export
        """
        # For export, disable colors to ensure clean output
        original_colors = self.enable_colors
        self.enable_colors = False
        
        try:
            return self.show_snapshot_diff(snapshot_id, format)
        finally:
            self.enable_colors = original_colors
    
    def get_file_changes(self, snapshot_id: SnapshotId) -> List[FileChange]:
        """Get detailed file changes for a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            List of file changes with line-level details
        """
        try:
            snapshot = self.storage_manager.load_snapshot(snapshot_id)
            if not snapshot:
                raise DiffViewerError(f"Snapshot not found: {snapshot_id}")
            
            file_changes = []
            
            # Get all affected files from snapshot and current directory
            affected_files = set(snapshot.file_states.keys())
            current_files = set()
            
            # Also check current directory
            try:
                for file_path in Path.cwd().rglob('*'):
                    if file_path.is_file():
                        try:
                            relative_path = file_path.relative_to(Path.cwd())
                            current_files.add(relative_path)
                        except ValueError:
                            # Skip files outside current directory
                            continue
            except Exception as e:
                logger.debug(f"Failed to scan current directory: {e}")
            
            # Combine both sets
            all_files = affected_files.union(current_files)
            
            for file_path in all_files:
                snapshot_content = self._get_file_content(snapshot_id, file_path)
                current_content = self._get_current_file_content(file_path)
                
                # Determine change type
                if snapshot_content is None and current_content is not None:
                    change_type = ChangeType.ADDED
                elif snapshot_content is not None and current_content is None:
                    change_type = ChangeType.DELETED
                elif snapshot_content != current_content:
                    change_type = ChangeType.MODIFIED
                else:
                    continue  # No change
                
                # Generate line changes for modified files
                line_changes = []
                if change_type == ChangeType.MODIFIED:
                    before_lines = snapshot_content.splitlines() if snapshot_content else []
                    after_lines = current_content.splitlines() if current_content else []
                    
                    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
                    
                    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                        if tag == 'delete':
                            for i in range(i1, i2):
                                line_changes.append(LineChange(
                                    line_number=i + 1,
                                    change_type=ChangeType.DELETED,
                                    content=before_lines[i],
                                    context=""
                                ))
                        elif tag == 'insert':
                            for j in range(j1, j2):
                                line_changes.append(LineChange(
                                    line_number=j + 1,
                                    change_type=ChangeType.ADDED,
                                    content=after_lines[j],
                                    context=""
                                ))
                        elif tag == 'replace':
                            # Handle as delete + insert
                            for i in range(i1, i2):
                                line_changes.append(LineChange(
                                    line_number=i + 1,
                                    change_type=ChangeType.DELETED,
                                    content=before_lines[i],
                                    context=""
                                ))
                            for j in range(j1, j2):
                                line_changes.append(LineChange(
                                    line_number=j + 1,
                                    change_type=ChangeType.ADDED,
                                    content=after_lines[j],
                                    context=""
                                ))
                
                # Get content hashes
                before_hash = None
                after_hash = None
                
                if file_path in snapshot.file_states:
                    before_hash = snapshot.file_states[file_path].content_hash
                
                if current_content is not None:
                    import hashlib
                    after_hash = hashlib.sha256(current_content.encode('utf-8')).hexdigest()
                
                file_changes.append(FileChange(
                    path=file_path,
                    change_type=change_type,
                    before_hash=before_hash,
                    after_hash=after_hash,
                    line_changes=line_changes
                ))
            
            return file_changes
            
        except Exception as e:
            logger.error(f"Failed to get file changes: {e}")
            raise DiffViewerError(f"Failed to get file changes: {e}")