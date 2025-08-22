"""Setup configuration for Claude Rewind Tool."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read version from package
version = "0.1.0"

setup(
    name="claude-rewind",
    version=version,
    author="Claude Rewind Team",
    author_email="team@claude-rewind.dev",
    description="Time-travel debugging for Claude Code actions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/claude-rewind/claude-rewind-tool",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Debuggers",
        "Topic :: Software Development :: Version Control",
    ],
    python_requires=">=3.11",
    install_requires=[
        "click>=8.0.0",
        "rich>=13.0.0",
        "pyyaml>=6.0",
        "watchdog>=3.0.0",
        "gitpython>=3.1.0",
        "pygments>=2.14.0",
        "zstandard>=0.21.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "mypy>=1.0.0",
            "flake8>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "claude-rewind=claude_rewind.cli.main:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)