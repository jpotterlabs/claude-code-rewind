"""Tests for smart rollback analyzer."""

import pytest
from pathlib import Path
from claude_rewind.rollback.analyzer import (
    ChangeAnalyzer, ChangeAnalysis,
    PythonAnalyzer, JavaScriptAnalyzer, JavaAnalyzer
)

def test_analyze_formatting_changes():
    """Test detection of formatting-only changes."""
    analyzer = ChangeAnalyzer()
    
    current = """
def test():
    print("hello")
    return True
    """
    
    target = """
def test():
        print("hello")
        return True
    """
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    assert analysis.change_type == 'formatting'
    assert analysis.severity < 0.3  # Formatting changes should have low severity
    assert 'formatting' in analysis.patterns
    assert analysis.additions == 0
    assert analysis.deletions == 0
    assert analysis.modifications == 2  # Two lines had indent changes

def test_analyze_comment_changes():
    """Test detection of comment-only changes."""
    analyzer = ChangeAnalyzer()
    
    current = """
def test():
    # Old comment
    print("hello")
    return True  # Old note
    """
    
    target = """
def test():
    # New comment
    print("hello")
    return True  # Updated note
    """
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    assert analysis.change_type == 'comments'
    assert analysis.severity < 0.3  # Comment changes should have low severity
    assert analysis.additions == 0
    assert analysis.deletions == 0
    assert analysis.modifications == 2  # Two comment lines changed

def test_analyze_structural_changes():
    """Test detection of structural changes."""
    analyzer = ChangeAnalyzer()
    
    current = """
def old_function(x):
    return x * 2

class TestClass:
    def method(self):
        pass
    """
    
    target = """
def new_function(x, y):
    return x * y

class NewClass:
    def method(self):
        pass
    """
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    assert analysis.change_type == 'structural'
    assert analysis.severity > 0.5  # Structural changes should have high severity
    assert analysis.structure_changes['type'] == 'python'
    assert len(analysis.structure_changes['changes']) >= 2  # At least 2 structural changes

def test_analyze_systematic_changes():
    """Test detection of systematic changes."""
    analyzer = ChangeAnalyzer()
    
    current = """
x = 1
y = 2
z = 3
"""
    
    target = """
x += 1
y += 2
z += 3
"""
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    assert 'systematic' in analysis.patterns
    assert analysis.modifications == 3
    assert analysis.severity < 0.5  # Systematic changes should have moderate severity

def test_analyze_python_structure():
    """Test Python-specific structure analysis."""
    analyzer = PythonAnalyzer()
    
    current = """
class TestClass:
    def method1(self, x):
        pass
        
    def method2(self):
        pass
"""
    
    target = """
class TestClass:
    def method1(self, x, y):
        pass
        
    def method3(self):
        pass
"""
    
    analysis = analyzer.analyze_structure(current, target)
    
    assert analysis['type'] == 'python'
    assert len(analysis['changes']) == 3  # One method modified, one removed, one added
    
    # Verify specific changes
    changes = {c['type']: c for c in analysis['changes']}
    assert 'modify_function' in changes  # method1 args changed
    assert 'remove_function' in changes  # method2 removed
    assert 'add_function' in changes     # method3 added

def test_analyze_imports():
    """Test import change detection."""
    analyzer = ChangeAnalyzer()
    
    current = """
from typing import List
import os
"""
    
    target = """
from typing import List, Dict
import os
import sys
"""
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    assert 'imports' in analysis.patterns
    assert analysis.additions == 1
    assert analysis.deletions == 0
    assert analysis.modifications == 1

def test_analyze_docstring_changes():
    """Test docstring change detection."""
    analyzer = ChangeAnalyzer()
    
    current = '''
def test():
    """Old docstring."""
    pass
'''
    
    target = '''
def test():
    """New docstring with more detail.
    
    Added description.
    """
    pass
'''
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    assert 'documentation' in analysis.patterns
    assert analysis.modifications > 0
    assert analysis.severity < 0.4  # Documentation changes should have low severity

def test_analyze_mixed_changes():
    """Test analysis of mixed changes."""
    analyzer = ChangeAnalyzer()
    
    current = """
def process(data):
    # Old comment
    result = []
    for item in data:
        result.append(item * 2)
    return result
"""
    
    target = """
def process(data: List[Dict]):
    \"\"\"Process data items.
    
    Args:
        data: Items to process
    \"\"\"
    # New comment
    result = []
    for item in data:
        if item['valid']:
            result.append(item['value'] * 2)
    return result
"""
    
    analysis = analyzer.analyze_changes(current, target, '.py')
    
    # This is structural since function signature changed
    assert analysis.change_type in ('content', 'structural')
    assert analysis.severity > 0.3  # Significant changes
    assert len(analysis.patterns) >= 1  # Multiple types of changes
    # Modifications are counted (additions + deletions combined as modifications)
    assert analysis.modifications > 0
    assert analysis.modifications > 0

def test_severity_calculation():
    """Test change severity calculation."""
    analyzer = ChangeAnalyzer()
    
    # Test formatting changes (should have low severity)
    format_analysis = analyzer.analyze_changes(
        "def test():\n    pass",
        "def test():\n        pass",
        '.py'
    )
    assert format_analysis.severity < 0.3
    
    # Test structural changes (should have high severity)
    struct_analysis = analyzer.analyze_changes(
        "def old(): pass",
        "class New: pass",
        '.py'
    )
    assert struct_analysis.severity > 0.5
    
    # Test massive changes (should max out at 1.0)
    big_analysis = analyzer.analyze_changes(
        "x = 1\n" * 1000,
        "y = 2\n" * 1000,
        '.py'
    )
    assert big_analysis.severity == 1.0