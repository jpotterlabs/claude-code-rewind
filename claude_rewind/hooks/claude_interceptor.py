"""Advanced Claude Code action interceptor using multiple detection methods."""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass

from ..core.models import ActionContext
from .claude_hook_manager import ClaudeActionType


logger = logging.getLogger(__name__)


@dataclass
class ClaudeToolCall:
    """Information about a detected Claude tool call."""
    tool_name: str
    parameters: Dict[str, Any]
    timestamp: datetime
    file_paths: List[Path]
    estimated_confidence: float
    detection_method: str


class ClaudeCodeInterceptor:
    """Advanced interceptor for Claude Code actions using multiple detection methods."""

    def __init__(self, project_root: Path, config: Optional[Dict[str, Any]] = None):
        """Initialize Claude Code interceptor.

        Args:
            project_root: Root directory of the project
            config: Configuration settings
        """
        self.project_root = project_root.resolve()
        self.config = config or {}

        # Detection state
        self._last_check_time = 0
        self._check_interval = 0.5  # 500ms
        self._recent_tool_calls: List[ClaudeToolCall] = []
        self._max_recent_calls = 50

        # File monitoring
        self._file_snapshots: Dict[Path, Dict[str, Any]] = {}
        self._snapshot_interval = 1.0  # seconds

        # Claude Code environment detection
        self._claude_env_markers = self._detect_claude_environment()
        self._claude_process_markers = set()

        # Pattern matching for Claude-generated content
        self._claude_patterns = self._compile_claude_patterns()

        # Tool call signatures
        self._tool_signatures = self._build_tool_signatures()

        logger.info("ClaudeCodeInterceptor initialized")

    def detect_claude_actions(self) -> List[ClaudeToolCall]:
        """Detect Claude Code actions using multiple methods.

        Returns:
            List of detected Claude tool calls
        """
        current_time = time.time()

        # Skip if we've checked too recently
        if current_time - self._last_check_time < self._check_interval:
            return []

        self._last_check_time = current_time

        detected_calls = []

        try:
            # Method 1: Environment-based detection
            env_calls = self._detect_from_environment()
            detected_calls.extend(env_calls)

            # Method 2: File change pattern analysis
            file_calls = self._detect_from_file_changes()
            detected_calls.extend(file_calls)

            # Method 3: Process monitoring
            process_calls = self._detect_from_processes()
            detected_calls.extend(process_calls)

            # Method 4: Content analysis
            content_calls = self._detect_from_content_analysis()
            detected_calls.extend(content_calls)

            # Method 5: Stdout/stderr monitoring (if possible)
            stdio_calls = self._detect_from_stdio()
            detected_calls.extend(stdio_calls)

            # Deduplicate and rank by confidence
            unique_calls = self._deduplicate_tool_calls(detected_calls)
            high_confidence_calls = [call for call in unique_calls if call.estimated_confidence > 0.7]

            # Update recent calls history
            self._recent_tool_calls.extend(high_confidence_calls)
            if len(self._recent_tool_calls) > self._max_recent_calls:
                self._recent_tool_calls = self._recent_tool_calls[-self._max_recent_calls:]

            return high_confidence_calls

        except Exception as e:
            logger.error(f"Error detecting Claude actions: {e}")
            return []

    def _detect_claude_environment(self) -> Dict[str, Any]:
        """Detect Claude Code environment markers.

        Returns:
            Dictionary with environment information
        """
        markers = {}

        # Check environment variables
        env_vars = ['CLAUDE_SESSION', 'CLAUDE_CODE_SESSION', 'ANTHROPIC_API_KEY']
        for var in env_vars:
            if os.getenv(var):
                markers[f'env_{var.lower()}'] = True

        # Check for Claude Code installation
        try:
            result = subprocess.run(['which', 'claude'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                markers['claude_binary'] = result.stdout.strip()
        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        # Check Python environment for Claude libraries
        try:
            import importlib.util
            claude_modules = ['anthropic', 'claude', 'claude-api']
            for module in claude_modules:
                spec = importlib.util.find_spec(module.replace('-', '_'))
                if spec:
                    markers[f'python_{module}'] = True
        except ImportError:
            pass

        return markers

    def _compile_claude_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for Claude-generated content.

        Returns:
            List of compiled regex patterns
        """
        patterns = [
            # Tool call patterns
            re.compile(r'<function_calls>', re.IGNORECASE),
            re.compile(r'<invoke name="([^"]+)">', re.IGNORECASE),
            re.compile(r'<parameter name="([^"]+)">([^<]*)</parameter>', re.IGNORECASE),

            # Code generation patterns
            re.compile(r'# Generated by Claude|// Generated by Claude', re.IGNORECASE),
            re.compile(r'def\s+\w+\([^)]*\)\s*:', re.MULTILINE),  # Function definitions
            re.compile(r'class\s+\w+[^{:]*[:{]', re.MULTILINE),   # Class definitions

            # File operation patterns
            re.compile(r'Writing to file:|Reading from file:|Creating file:', re.IGNORECASE),
            re.compile(r'File\s+(created|modified|deleted):', re.IGNORECASE),

            # Command patterns
            re.compile(r'Running command:|Executing:', re.IGNORECASE),
            re.compile(r'(bash|shell|cmd)\s*:', re.IGNORECASE),
        ]

        return patterns

    def _build_tool_signatures(self) -> Dict[str, Dict[str, Any]]:
        """Build signatures for Claude Code tools.

        Returns:
            Dictionary mapping tool names to their signatures
        """
        return {
            'Edit': {
                'required_params': ['file_path', 'old_string', 'new_string'],
                'optional_params': ['replace_all'],
                'file_indicators': ['file_path'],
                'confidence_boost': 0.3
            },
            'Write': {
                'required_params': ['file_path', 'content'],
                'optional_params': [],
                'file_indicators': ['file_path'],
                'confidence_boost': 0.3
            },
            'Read': {
                'required_params': ['file_path'],
                'optional_params': ['limit', 'offset'],
                'file_indicators': ['file_path'],
                'confidence_boost': 0.2
            },
            'Bash': {
                'required_params': ['command'],
                'optional_params': ['description', 'timeout'],
                'file_indicators': [],
                'confidence_boost': 0.2
            },
            'MultiEdit': {
                'required_params': ['file_path', 'edits'],
                'optional_params': [],
                'file_indicators': ['file_path'],
                'confidence_boost': 0.4
            },
            'NotebookEdit': {
                'required_params': ['notebook_path', 'new_source'],
                'optional_params': ['cell_number', 'cell_type'],
                'file_indicators': ['notebook_path'],
                'confidence_boost': 0.3
            }
        }

    def _detect_from_environment(self) -> List[ClaudeToolCall]:
        """Detect Claude actions from environment changes.

        Returns:
            List of detected tool calls
        """
        detected_calls = []

        try:
            # Check for new environment markers
            current_env = self._detect_claude_environment()

            # Compare with previous state to detect changes
            new_markers = set(current_env.keys()) - set(self._claude_env_markers.keys())

            if new_markers:
                logger.debug(f"Detected new Claude environment markers: {new_markers}")

                # This suggests Claude Code started or was activated
                call = ClaudeToolCall(
                    tool_name="claude_session_start",
                    parameters={'markers': list(new_markers)},
                    timestamp=datetime.now(),
                    file_paths=[],
                    estimated_confidence=0.6,
                    detection_method="environment"
                )
                detected_calls.append(call)

            self._claude_env_markers = current_env

        except Exception as e:
            logger.debug(f"Error in environment detection: {e}")

        return detected_calls

    def _detect_from_file_changes(self) -> List[ClaudeToolCall]:
        """Detect Claude actions from file change patterns.

        Returns:
            List of detected tool calls
        """
        detected_calls = []

        try:
            current_time = time.time()

            # Take snapshot of current file states
            current_snapshot = self._take_file_snapshot()

            if self._file_snapshots:
                # Compare with previous snapshot
                changes = self._compare_file_snapshots(self._file_snapshots, current_snapshot)

                for change in changes:
                    # Analyze change to determine if it looks like Claude action
                    tool_call = self._analyze_file_change(change)
                    if tool_call:
                        detected_calls.append(tool_call)

            # Update snapshot
            self._file_snapshots = current_snapshot

        except Exception as e:
            logger.debug(f"Error in file change detection: {e}")

        return detected_calls

    def _take_file_snapshot(self) -> Dict[Path, Dict[str, Any]]:
        """Take a snapshot of current file states.

        Returns:
            Dictionary mapping file paths to their states
        """
        snapshot = {}
        current_time = time.time()

        try:
            for file_path in self.project_root.rglob('*'):
                if not file_path.is_file() or self._should_ignore_file(file_path):
                    continue

                try:
                    stat = file_path.stat()
                    relative_path = file_path.relative_to(self.project_root)

                    snapshot[relative_path] = {
                        'mtime': stat.st_mtime,
                        'size': stat.st_size,
                        'exists': True,
                        'snapshot_time': current_time
                    }

                except OSError:
                    continue

        except Exception as e:
            logger.debug(f"Error taking file snapshot: {e}")

        return snapshot

    def _compare_file_snapshots(self, old_snapshot: Dict[Path, Dict[str, Any]],
                               new_snapshot: Dict[Path, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare two file snapshots to detect changes.

        Args:
            old_snapshot: Previous file snapshot
            new_snapshot: Current file snapshot

        Returns:
            List of detected file changes
        """
        changes = []

        # Find new and modified files
        for path, new_state in new_snapshot.items():
            if path not in old_snapshot:
                # New file
                changes.append({
                    'type': 'created',
                    'path': path,
                    'new_state': new_state,
                    'old_state': None
                })
            else:
                old_state = old_snapshot[path]
                if (new_state['mtime'] != old_state['mtime'] or
                    new_state['size'] != old_state['size']):
                    # Modified file
                    changes.append({
                        'type': 'modified',
                        'path': path,
                        'new_state': new_state,
                        'old_state': old_state
                    })

        # Find deleted files
        for path in old_snapshot:
            if path not in new_snapshot:
                changes.append({
                    'type': 'deleted',
                    'path': path,
                    'new_state': None,
                    'old_state': old_snapshot[path]
                })

        return changes

    def _analyze_file_change(self, change: Dict[str, Any]) -> Optional[ClaudeToolCall]:
        """Analyze a file change to determine if it's a Claude action.

        Args:
            change: File change information

        Returns:
            ClaudeToolCall if this appears to be a Claude action, None otherwise
        """
        change_type = change['type']
        file_path = change['path']
        confidence = 0.3  # Base confidence

        # Boost confidence for code files
        if self._is_code_file(file_path):
            confidence += 0.2

        # Analyze change patterns
        if change_type == 'created':
            tool_name = ClaudeActionType.CREATE_FILE
            confidence += 0.2
        elif change_type == 'modified':
            tool_name = ClaudeActionType.EDIT_FILE
            confidence += 0.1

            # Check if multiple files changed around same time
            new_state = change['new_state']
            recent_threshold = new_state['snapshot_time'] - 2.0

            recent_changes = sum(1 for _, state in self._file_snapshots.items()
                               if state.get('snapshot_time', 0) > recent_threshold)

            if recent_changes > 1:
                tool_name = ClaudeActionType.MULTI_EDIT
                confidence += 0.2

        elif change_type == 'deleted':
            tool_name = ClaudeActionType.DELETE_FILE
            confidence += 0.1
        else:
            return None

        # Analyze file content if possible
        try:
            full_path = self.project_root / file_path
            if full_path.exists() and change_type in ['created', 'modified']:
                content_confidence = self._analyze_file_content(full_path)
                confidence += content_confidence

        except Exception as e:
            logger.debug(f"Error analyzing file content: {e}")

        # Only return if confidence is sufficient
        if confidence > 0.6:
            return ClaudeToolCall(
                tool_name=tool_name,
                parameters={'file_path': str(file_path)},
                timestamp=datetime.now(),
                file_paths=[file_path],
                estimated_confidence=confidence,
                detection_method="file_analysis"
            )

        return None

    def _analyze_file_content(self, file_path: Path) -> float:
        """Analyze file content for Claude indicators.

        Args:
            file_path: Path to the file to analyze

        Returns:
            Confidence boost based on content analysis
        """
        confidence_boost = 0.0

        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')

            # Check for Claude patterns
            pattern_matches = 0
            for pattern in self._claude_patterns:
                if pattern.search(content):
                    pattern_matches += 1

            if pattern_matches > 0:
                confidence_boost += min(0.3, pattern_matches * 0.1)

            # Check for common AI-generated code characteristics
            lines = content.splitlines()

            # Well-structured code with good comments
            comment_ratio = sum(1 for line in lines if line.strip().startswith('#') or line.strip().startswith('//')) / max(1, len(lines))
            if comment_ratio > 0.1:  # More than 10% comments
                confidence_boost += 0.1

            # Function/class definitions
            definition_count = sum(1 for line in lines
                                 if any(keyword in line for keyword in ['def ', 'class ', 'function ', 'interface ']))
            if definition_count > 0:
                confidence_boost += 0.1

            # Import statements (suggests new code)
            import_count = sum(1 for line in lines
                             if any(keyword in line for keyword in ['import ', 'from ', 'require(', '#include']))
            if import_count > 0:
                confidence_boost += 0.05

        except Exception as e:
            logger.debug(f"Error analyzing content of {file_path}: {e}")

        return min(confidence_boost, 0.4)  # Cap the boost

    def _detect_from_processes(self) -> List[ClaudeToolCall]:
        """Detect Claude actions from process monitoring.

        Returns:
            List of detected tool calls
        """
        detected_calls = []

        try:
            # Look for Claude-related processes
            claude_processes = self._find_claude_processes()

            # Check for new processes
            new_processes = set(claude_processes) - self._claude_process_markers

            if new_processes:
                logger.debug(f"Detected new Claude processes: {new_processes}")

                call = ClaudeToolCall(
                    tool_name="claude_process_detected",
                    parameters={'processes': list(new_processes)},
                    timestamp=datetime.now(),
                    file_paths=[],
                    estimated_confidence=0.5,
                    detection_method="process_monitoring"
                )
                detected_calls.append(call)

            self._claude_process_markers = set(claude_processes)

        except Exception as e:
            logger.debug(f"Error in process detection: {e}")

        return detected_calls

    def _find_claude_processes(self) -> List[str]:
        """Find running processes related to Claude.

        Returns:
            List of process descriptions
        """
        processes = []

        try:
            # Use ps to find processes
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.splitlines()

                for line in lines:
                    # Look for Claude-related keywords in process names
                    if any(keyword in line.lower() for keyword in ['claude', 'anthropic']):
                        processes.append(line.strip())

        except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            logger.debug(f"Process search failed: {e}")

        return processes

    def _detect_from_content_analysis(self) -> List[ClaudeToolCall]:
        """Detect Claude actions from recent content analysis.

        Returns:
            List of detected tool calls
        """
        detected_calls = []

        try:
            # Look for recently modified files that might contain Claude indicators
            current_time = time.time()
            recent_threshold = current_time - 10  # Last 10 seconds

            for file_path in self.project_root.rglob('*'):
                if not file_path.is_file() or self._should_ignore_file(file_path):
                    continue

                try:
                    stat = file_path.stat()
                    if stat.st_mtime > recent_threshold:
                        # File was recently modified
                        content_confidence = self._analyze_file_content(file_path)

                        if content_confidence > 0.2:
                            relative_path = file_path.relative_to(self.project_root)

                            call = ClaudeToolCall(
                                tool_name=ClaudeActionType.EDIT_FILE,
                                parameters={'file_path': str(relative_path)},
                                timestamp=datetime.fromtimestamp(stat.st_mtime),
                                file_paths=[relative_path],
                                estimated_confidence=0.4 + content_confidence,
                                detection_method="content_analysis"
                            )
                            detected_calls.append(call)

                except OSError:
                    continue

        except Exception as e:
            logger.debug(f"Error in content analysis detection: {e}")

        return detected_calls

    def _detect_from_stdio(self) -> List[ClaudeToolCall]:
        """Detect Claude actions from stdout/stderr monitoring.

        Returns:
            List of detected tool calls
        """
        detected_calls = []

        # This would require more advanced process monitoring
        # For now, we'll implement a basic version that looks for
        # Claude-specific output patterns in the current process

        try:
            # Check if we can access any log files or output streams
            log_paths = [
                Path.home() / '.claude' / 'logs',
                Path('/tmp') / 'claude_logs',
                self.project_root / '.claude-rewind' / 'activity.log'
            ]

            for log_path in log_paths:
                if log_path.exists() and log_path.is_file():
                    try:
                        # Read recent log entries
                        content = log_path.read_text(encoding='utf-8', errors='ignore')
                        recent_entries = self._parse_log_entries(content)

                        for entry in recent_entries:
                            if self._looks_like_claude_action(entry):
                                call = self._log_entry_to_tool_call(entry)
                                if call:
                                    detected_calls.append(call)

                    except Exception as e:
                        logger.debug(f"Error reading log file {log_path}: {e}")

        except Exception as e:
            logger.debug(f"Error in stdio detection: {e}")

        return detected_calls

    def _parse_log_entries(self, content: str) -> List[Dict[str, Any]]:
        """Parse log content into entries.

        Args:
            content: Log file content

        Returns:
            List of parsed log entries
        """
        entries = []
        current_time = time.time()
        recent_threshold = current_time - 30  # Last 30 seconds

        lines = content.splitlines()
        for line in lines:
            # Simple log parsing - could be enhanced
            if any(keyword in line.lower() for keyword in ['claude', 'tool', 'action', 'edit', 'write']):
                entries.append({
                    'content': line,
                    'timestamp': current_time,  # Approximate
                    'raw': line
                })

        return entries

    def _looks_like_claude_action(self, entry: Dict[str, Any]) -> bool:
        """Check if a log entry looks like a Claude action.

        Args:
            entry: Log entry to check

        Returns:
            True if this looks like a Claude action
        """
        content = entry.get('content', '').lower()

        action_indicators = [
            'edit file', 'write file', 'create file', 'delete file',
            'tool call', 'function call', 'claude action',
            'editing', 'writing', 'creating', 'modifying'
        ]

        return any(indicator in content for indicator in action_indicators)

    def _log_entry_to_tool_call(self, entry: Dict[str, Any]) -> Optional[ClaudeToolCall]:
        """Convert a log entry to a tool call.

        Args:
            entry: Log entry to convert

        Returns:
            ClaudeToolCall if conversion successful, None otherwise
        """
        content = entry.get('content', '')

        # Extract tool name and parameters from log entry
        tool_name = "unknown_action"
        parameters = {}
        file_paths = []
        confidence = 0.3

        # Simple pattern matching - could be enhanced
        if 'edit' in content.lower():
            tool_name = ClaudeActionType.EDIT_FILE
            confidence = 0.5
        elif 'write' in content.lower():
            tool_name = ClaudeActionType.WRITE_FILE
            confidence = 0.5
        elif 'create' in content.lower():
            tool_name = ClaudeActionType.CREATE_FILE
            confidence = 0.5

        return ClaudeToolCall(
            tool_name=tool_name,
            parameters=parameters,
            timestamp=datetime.fromtimestamp(entry.get('timestamp', time.time())),
            file_paths=file_paths,
            estimated_confidence=confidence,
            detection_method="stdio_monitoring"
        )

    def _deduplicate_tool_calls(self, calls: List[ClaudeToolCall]) -> List[ClaudeToolCall]:
        """Remove duplicate tool calls and merge similar ones.

        Args:
            calls: List of detected tool calls

        Returns:
            Deduplicated list of tool calls
        """
        if not calls:
            return []

        # Sort by timestamp
        sorted_calls = sorted(calls, key=lambda c: c.timestamp)

        # Group similar calls within time window
        unique_calls = []
        time_window = 2.0  # 2 seconds

        for call in sorted_calls:
            # Check if this call is similar to any recent unique call
            is_duplicate = False

            for unique_call in unique_calls:
                time_diff = abs((call.timestamp - unique_call.timestamp).total_seconds())

                if (time_diff < time_window and
                    call.tool_name == unique_call.tool_name and
                    set(call.file_paths) == set(unique_call.file_paths)):

                    # This is a duplicate, merge if new one has higher confidence
                    if call.estimated_confidence > unique_call.estimated_confidence:
                        unique_calls.remove(unique_call)
                        unique_calls.append(call)

                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_calls.append(call)

        return unique_calls

    def _should_ignore_file(self, file_path: Path) -> bool:
        """Check if a file should be ignored for monitoring.

        Args:
            file_path: Path to check

        Returns:
            True if file should be ignored
        """
        # Reuse logic from hook manager
        ignore_patterns = {
            '.git', '.svn', '.hg',
            '__pycache__', '.pytest_cache',
            'node_modules', '.npm',
            '.vscode', '.idea',
            'venv', '.venv', 'env',
            'target', 'build', 'dist',
            '.claude-rewind'
        }

        for part in file_path.parts:
            if part in ignore_patterns or part.startswith('.'):
                return True

        ignore_extensions = {'.pyc', '.pyo', '.pyd', '.log', '.tmp', '.temp'}
        if file_path.suffix.lower() in ignore_extensions:
            return True

        return False

    def _is_code_file(self, file_path: Path) -> bool:
        """Check if a file is a code file.

        Args:
            file_path: Path to check

        Returns:
            True if this is a code file
        """
        code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
            '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
            '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg',
            '.sql', '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd',
            '.md', '.rst', '.txt'
        }

        return file_path.suffix.lower() in code_extensions

    def get_detection_stats(self) -> Dict[str, Any]:
        """Get statistics about detection performance.

        Returns:
            Dictionary with detection statistics
        """
        return {
            'recent_calls_count': len(self._recent_tool_calls),
            'environment_markers': len(self._claude_env_markers),
            'process_markers': len(self._claude_process_markers),
            'file_snapshots_count': len(self._file_snapshots),
            'last_check_time': self._last_check_time,
            'check_interval': self._check_interval
        }