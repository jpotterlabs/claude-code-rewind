# 🚀 Installation Guide

## Quick Install (Recommended)

### From Source (Current)
```bash
# Clone the repository
git clone https://github.com/holasoymalva/claude-code-rewind.git
cd claude-code-rewind

# Install directly with pip (no virtual environment needed!)
pip install -e .

# Verify installation
claude-rewind --help
```

### From PyPI (Coming Soon)
```bash
# When published to PyPI, it will be this simple:
pip install claude-rewind

# Verify installation
claude-rewind --help
```

## 🎯 That's It!

Once installed, `claude-rewind` is available globally. No virtual environments, no PYTHONPATH, no complex setup required.

## ✅ Verify Installation

```bash
# Check that the command is available
which claude-rewind

# Test basic functionality
cd your-project
claude-rewind init
claude-rewind status
```

## 🔧 System Requirements

- **Python**: 3.11 or higher
- **Operating System**: Windows, macOS, Linux
- **Dependencies**: Automatically installed with pip

### Dependencies Installed Automatically:
- `click` - Command-line interface
- `rich` - Rich terminal output
- `pyyaml` - Configuration management
- `watchdog` - File system monitoring
- `gitpython` - Git integration
- `pygments` - Syntax highlighting
- `zstandard` - Compression

## 🏗️ Development Installation

If you want to contribute or modify the code:

```bash
# Clone and install in development mode
git clone https://github.com/holasoymalva/claude-code-rewind.git
cd claude-code-rewind

# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
black claude_rewind
isort claude_rewind
mypy claude_rewind
```

## 🐍 Multiple Python Versions

If you have multiple Python versions:

```bash
# Use specific Python version
python3.11 -m pip install -e .
# or
python3.12 -m pip install -e .

# The claude-rewind command will use the Python version it was installed with
```

## 🗑️ Uninstallation

```bash
pip uninstall claude-rewind
```

## 🛠️ Troubleshooting

### Command Not Found
If `claude-rewind` command is not found after installation:

1. **Check pip installation location**:
   ```bash
   pip show claude-rewind
   ```

2. **Check if pip's bin directory is in PATH**:
   ```bash
   python -m site --user-base
   # Add the bin subdirectory to your PATH
   ```

3. **Use direct execution**:
   ```bash
   python -m claude_rewind.cli.main --help
   ```

### Permission Issues
If you get permission errors:

```bash
# Install for current user only
pip install --user -e .

# Or use virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

### Python Version Issues
```bash
# Check Python version
python --version

# Update Python if needed (must be 3.11+)
# On Ubuntu/Debian:
sudo apt update && sudo apt install python3.11

# On macOS with Homebrew:
brew install python@3.11

# On Windows: Download from python.org
```

## 📦 Package Structure

After installation, you get:

- **Global command**: `claude-rewind` available anywhere
- **Python package**: `claude_rewind` importable in Python
- **Configuration**: Auto-created in `~/.claude-rewind/` (global) or `.claude-rewind/` (per-project)

## 🎉 Next Steps

Once installed:

1. **Initialize your project**:
   ```bash
   cd your-project
   claude-rewind init
   ```

2. **Start monitoring**:
   ```bash
   claude-rewind monitor
   ```

3. **Explore features**:
   ```bash
   claude-rewind timeline
   claude-rewind session --action stats
   claude-rewind --help
   ```

---

**🎯 No more virtual environments or complex setups - just install and use!**