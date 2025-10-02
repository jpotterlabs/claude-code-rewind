"""Analyzer for smart rollback system."""

import logging
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
import difflib

logger = logging.getLogger(__name__)

@dataclass
class ChangeAnalysis:
    """Analysis results for a file change."""
    
    change_type: str  # 'formatting', 'comments', 'content', 'structural'
    severity: float  # 0.0 to 1.0
    patterns: List[str]  # Detected change patterns
    structure_changes: Dict[str, Any]  # Changes to code structure
    additions: int  # Number of added lines
    deletions: int  # Number of deleted lines
    modifications: int  # Number of modified lines

class ChangeAnalyzer:
    """Analyzes changes for smart rollback."""
    
    def __init__(self):
        self.structure_analyzers = {
            '.py': PythonAnalyzer(),
            '.js': JavaScriptAnalyzer(),
            '.java': JavaAnalyzer()
        }
    
    def analyze_changes(self, current_content: str, target_content: str,
                       file_type: str) -> ChangeAnalysis:
        """Analyze differences between current and target content.
        
        Args:
            current_content: Current file content
            target_content: Target file content
            file_type: Type of file (extension)
            
        Returns:
            Analysis of changes
        """
        # Get appropriate analyzer
        analyzer = self.structure_analyzers.get(file_type, DefaultAnalyzer())
        
        # Basic diff analysis
        change_stats = self._analyze_diff(current_content, target_content)
        
        # Determine change type
        change_type = self._determine_change_type(current_content, target_content)
        
        # Calculate severity
        severity = self._calculate_severity(change_stats, change_type)
        
        # Detect patterns
        patterns = self._detect_patterns(current_content, target_content)
        
        # Analyze structure
        structure_changes = analyzer.analyze_structure(current_content, target_content)
        
        return ChangeAnalysis(
            change_type=change_type,
            severity=severity,
            patterns=patterns,
            structure_changes=structure_changes,
            additions=change_stats['additions'],
            deletions=change_stats['deletions'],
            modifications=change_stats['modifications']
        )
    
    def _analyze_diff(self, current: str, target: str) -> Dict[str, int]:
        """Analyze basic diff statistics.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            Dict with diff statistics
        """
        current_lines = current.splitlines()
        target_lines = target.splitlines()
        
        matcher = difflib.SequenceMatcher(None, current_lines, target_lines)
        
        stats = {
            'additions': 0,
            'deletions': 0,
            'modifications': 0,
            'moves': 0
        }
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'insert':
                stats['additions'] += j2 - j1
            elif tag == 'delete':
                stats['deletions'] += i2 - i1
            elif tag == 'replace':
                stats['modifications'] += max(i2 - i1, j2 - j1)
        
        return stats
    
    def _determine_change_type(self, current: str, target: str) -> str:
        """Determine the type of changes made.

        Args:
            current: Current content
            target: Target content

        Returns:
            Change type string
        """
        if self._only_formatting_changes(current, target):
            return 'formatting'
            
        if self._only_comments_changed(current, target):
            return 'comments'
            
        if self._is_structural_change(current, target):
            return 'structural'
            
        return 'content'
    
    def _calculate_severity(self, stats: Dict[str, int], change_type: str) -> float:
        """Calculate severity of changes.
        
        Args:
            stats: Diff statistics
            change_type: Type of change
            
        Returns:
            Severity score 0.0-1.0
        """
        total_changes = stats['additions'] + stats['deletions'] + stats['modifications']
        
        # Base severity on number of changes
        severity = min(1.0, total_changes / 100)
        
        # Adjust based on change type
        if change_type == 'formatting':
            severity *= 0.2
        elif change_type == 'comments':
            severity *= 0.3
        elif change_type == 'structural':
            # Structural changes should have high severity
            severity = max(0.6, min(1.0, severity * 2.0))
            
        return severity
    
    def _detect_patterns(self, current: str, target: str) -> List[str]:
        """Detect common change patterns.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            List of detected patterns
        """
        patterns = []
        
        if self._has_systematic_changes(current, target):
            patterns.append('systematic')
            
        if self._has_formatting_changes(current, target):
            patterns.append('formatting')
            
        if self._has_imports_changed(current, target):
            patterns.append('imports')
            
        if self._has_docstring_changes(current, target):
            patterns.append('documentation')
            
        return patterns
    
    def _only_formatting_changes(self, current: str, target: str) -> bool:
        """Check if only formatting changed.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            True if only formatting changed
        """
        # Remove all whitespace and compare
        current_norm = ''.join(current.split())
        target_norm = ''.join(target.split())
        return current_norm == target_norm
    
    def _only_comments_changed(self, current: str, target: str) -> bool:
        """Check if only comments changed.
        
        Args:
            current: Current content 
            target: Target content
            
        Returns:
            True if only comments changed
        """
        def strip_comments_python(text: str) -> str:
            lines = []
            for line in text.splitlines():
                # Handle inline comments
                if '#' in line:
                    code_part = line[:line.find('#')]
                    lines.append(code_part.rstrip())
                else:
                    lines.append(line.rstrip())
            return '\n'.join(lines)
        
        # Strip comments and compare
        current_no_comments = strip_comments_python(current)
        target_no_comments = strip_comments_python(target)
        return current_no_comments == target_no_comments
    
    def _is_structural_change(self, current: str, target: str) -> bool:
        """Check if changes are structural (functions, classes, etc).
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            True if changes are structural
        """
        structural_markers = [
            'class ', 'def ', 'function', 'interface',
            'struct', 'enum', 'typedef'
        ]
        
        current_lines = set(current.splitlines())
        target_lines = set(target.splitlines())
        
        for line in current_lines.symmetric_difference(target_lines):
            if any(marker in line for marker in structural_markers):
                return True
                
        return False
    
    def _has_systematic_changes(self, current: str, target: str) -> bool:
        """Check if changes follow a systematic pattern.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            True if changes are systematic
        """
        current_lines = current.splitlines()
        target_lines = target.splitlines()
        
        if len(current_lines) != len(target_lines):
            return False
            
        changes = []
        for c, t in zip(current_lines, target_lines, strict=True):
            if c != t:
                changes.append((c.strip(), t.strip()))
                
        if len(changes) < 2:
            return False
        
        # Check for similar patterns across changes
        pattern_count = 0
        for i, (c1, t1) in enumerate(changes):
            for _j, (c2, t2) in enumerate(changes[i+1:], i+1):
                # Look for similar transformations
                if self._similar_transformation(c1, t1, c2, t2):
                    pattern_count += 1
        
        # Consider systematic if there are at least 2 similar changes
        return pattern_count >= 1
    
    def _similar_transformation(self, c1: str, t1: str, c2: str, t2: str) -> bool:
        """Check if two line transformations are similar."""
        # Simple heuristics: same operation pattern (= to +=, etc.)
        if '=' in c1 and '=' in c2 and '+=' in t1 and '+=' in t2:
            return True
        if '+=' in c1 and '+=' in c2 and '=' in t1 and '=' in t2:
            return True
        # Similar variable operations
        if c1.split() and c2.split() and t1.split() and t2.split():
            c1_parts = c1.split()
            c2_parts = c2.split()
            t1_parts = t1.split()
            t2_parts = t2.split()
            if (len(c1_parts) == len(c2_parts) == len(t1_parts) == len(t2_parts) and
                c1_parts[1:] == t1_parts[1:] and c2_parts[1:] == t2_parts[1:]):
                return True
        return False
    
    def _has_formatting_changes(self, current: str, target: str) -> bool:
        """Check if changes include formatting.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            True if formatting changed
        """
        def get_indent(line: str) -> int:
            return len(line) - len(line.lstrip())
        
        current_indents = [get_indent(line) for line in current.splitlines()]
        target_indents = [get_indent(line) for line in target.splitlines()]
        
        return current_indents != target_indents
    
    def _has_imports_changed(self, current: str, target: str) -> bool:
        """Check if imports changed.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            True if imports changed
        """
        def get_imports(text: str) -> Set[str]:
            imports = set()
            for line in text.splitlines():
                if line.startswith(('import ', 'from ')):
                    imports.add(line.strip())
            return imports
        
        return get_imports(current) != get_imports(target)
    
    def _has_docstring_changes(self, current: str, target: str) -> bool:
        """Check if docstrings changed.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            True if docstrings changed
        """
        def get_docstrings(text: str) -> List[str]:
            docstrings = []
            lines = text.splitlines()
            for line in lines:
                if line.strip().startswith('"""') or line.strip().startswith("'''"):
                    docstrings.append(line)
            return docstrings
        
        return get_docstrings(current) != get_docstrings(target)

class StructureAnalyzer:
    """Base class for language-specific structure analysis."""
    
    def analyze_structure(self, current: str, target: str) -> Dict[str, Any]:
        """Analyze code structure changes.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            Dict with structure analysis
        """
        raise NotImplementedError

class DefaultAnalyzer(StructureAnalyzer):
    """Default analyzer for unknown file types."""
    
    def analyze_structure(self, current: str, target: str) -> Dict[str, Any]:
        return {
            'type': 'unknown',
            'changes': []
        }

class PythonAnalyzer(StructureAnalyzer):
    """Analyzer for Python code."""
    
    def analyze_structure(self, current: str, target: str) -> Dict[str, Any]:
        """Analyze Python code structure.
        
        Args:
            current: Current content
            target: Target content
            
        Returns:
            Dict with structure analysis
        """
        import ast
        
        try:
            current_ast = ast.parse(current)
            target_ast = ast.parse(target)
            
            current_info = self._analyze_ast(current_ast)
            target_info = self._analyze_ast(target_ast)
            
            return {
                'type': 'python',
                'current': current_info,
                'target': target_info,
                'changes': self._diff_info(current_info, target_info)
            }
            
        except Exception as e:
            logger.warning(f"Failed to analyze Python structure: {e}")
            return {
                'type': 'python',
                'error': str(e)
            }
    
    def _analyze_ast(self, tree: ast.AST) -> Dict[str, Any]:
        """Analyze Python AST.
        
        Args:
            tree: AST to analyze
            
        Returns:
            Dict with AST info
        """
        classes = []
        functions = []
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append({
                    'name': node.name,
                    'lineno': node.lineno
                })
            elif isinstance(node, ast.FunctionDef):
                functions.append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'args': [a.arg for a in node.args.args]
                })
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = [n.name for n in node.names]
                else:
                    names = [f"{node.module}.{n.name}" for n in node.names]
                imports.append({
                    'names': names,
                    'lineno': node.lineno
                })
        
        return {
            'classes': classes,
            'functions': functions,
            'imports': imports
        }
    
    def _diff_info(self, current: Dict[str, Any], target: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compare structure info.
        
        Args:
            current: Current structure info
            target: Target structure info
            
        Returns:
            List of structural changes
        """
        changes = []
        
        # Compare classes
        current_classes = {c['name']: c for c in current['classes']}
        target_classes = {c['name']: c for c in target['classes']}
        
        for name in set(current_classes) - set(target_classes):
            changes.append({
                'type': 'remove_class',
                'name': name
            })
        
        for name in set(target_classes) - set(current_classes):
            changes.append({
                'type': 'add_class',
                'name': name
            })
        
        # Compare functions
        current_funcs = {f['name']: f for f in current['functions']}
        target_funcs = {f['name']: f for f in target['functions']}
        
        # Use a more accurate diffing approach for functions
        current_func_names = set(current_funcs.keys())
        target_func_names = set(target_funcs.keys())
        
        added_funcs = target_func_names - current_func_names
        removed_funcs = current_func_names - target_func_names
        common_funcs = current_func_names & target_func_names
        
        for name in added_funcs:
            changes.append({'type': 'add_function', 'name': name})
            
        for name in removed_funcs:
            changes.append({'type': 'remove_function', 'name': name})
            
        for name in common_funcs:
            if current_funcs[name]['args'] != target_funcs[name]['args']:
                changes.append({
                    'type': 'modify_function',
                    'name': name,
                    'current_args': current_funcs[name]['args'],
                    'target_args': target_funcs[name]['args']
                })
        
        return changes

class JavaScriptAnalyzer(StructureAnalyzer):
    """Analyzer for JavaScript code."""
    
    def analyze_structure(self, current: str, target: str) -> Dict[str, Any]:
        # TODO: Implement JavaScript structure analysis
        return {
            'type': 'javascript',
            'changes': []
        }

class JavaAnalyzer(StructureAnalyzer):
    """Analyzer for Java code."""
    
    def analyze_structure(self, current: str, target: str) -> Dict[str, Any]:
        # TODO: Implement Java structure analysis
        return {
            'type': 'java',
            'changes': []
        }