"""Test configuration and fixtures."""

import pytest
import tempfile
import shutil
from pathlib import Path

@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Create project structure
        (temp_dir / "src").mkdir()
        (temp_dir / "tests").mkdir()
        (temp_dir / ".claude-rewind").mkdir()
        (temp_dir / ".claude-rewind/plugins").mkdir()
        
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)

@pytest.fixture
def sample_python_file(temp_project):
    """Create a sample Python file."""
    file_path = temp_project / "src" / "sample.py"
    file_path.write_text("""
def example_function(x: int) -> int:
    \"\"\"Example function.
    
    Args:
        x: Input value
        
    Returns:
        Doubled input
    \"\"\"
    return x * 2

class ExampleClass:
    def method(self):
        pass
""")
    return file_path