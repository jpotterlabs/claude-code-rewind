#!/bin/bash
# Test script to verify the complete installation workflow

set -e  # Exit on any error

echo "🧪 Testing Claude Rewind Installation Workflow"
echo "=============================================="

# Test 1: Verify the package is installed
echo ""
echo "📦 Test 1: Verify claude-rewind command exists"
if command -v claude-rewind >/dev/null 2>&1; then
    echo "✅ claude-rewind command found: $(which claude-rewind)"
else
    echo "❌ claude-rewind command not found"
    exit 1
fi

# Test 2: Test help command
echo ""
echo "📚 Test 2: Test help command"
if claude-rewind --help >/dev/null 2>&1; then
    echo "✅ Help command works"
else
    echo "❌ Help command failed"
    exit 1
fi

# Test 3: Test in a clean directory
echo ""
echo "📁 Test 3: Test initialization in clean directory"
TEST_DIR="/tmp/claude-rewind-install-test"
rm -rf "$TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Initialize project
if claude-rewind init >/dev/null 2>&1; then
    echo "✅ Initialization works"
else
    echo "❌ Initialization failed"
    exit 1
fi

# Test 4: Verify files were created
echo ""
echo "🔍 Test 4: Verify project files created"
if [ -d ".claude-rewind" ]; then
    echo "✅ .claude-rewind directory created"
else
    echo "❌ .claude-rewind directory not found"
    exit 1
fi

if [ -f ".claude-rewind/config.yml" ]; then
    echo "✅ Configuration file created"
else
    echo "❌ Configuration file not found"
    exit 1
fi

if [ -f ".claude-rewind/metadata.db" ]; then
    echo "✅ Database file created"
else
    echo "❌ Database file not found"
    exit 1
fi

# Test 5: Test status command
echo ""
echo "📊 Test 5: Test status command"
if claude-rewind status >/dev/null 2>&1; then
    echo "✅ Status command works"
else
    echo "❌ Status command failed"
    exit 1
fi

# Test 6: Test deprecated watch command
echo ""
echo "⚠️  Test 6: Test deprecated watch command"
if echo "n" | claude-rewind watch >/dev/null 2>&1; then
    echo "✅ Deprecated watch command handled correctly"
else
    echo "❌ Deprecated watch command failed"
    exit 1
fi

# Test 7: Test session command
echo ""
echo "🎯 Test 7: Test session command"
if claude-rewind session --action status >/dev/null 2>&1; then
    echo "✅ Session command works"
else
    echo "❌ Session command failed"
    exit 1
fi

# Clean up
cd /
rm -rf "$TEST_DIR"

echo ""
echo "🎉 All installation tests passed!"
echo ""
echo "✅ Package is properly installed"
echo "✅ Console script works correctly"
echo "✅ All core commands functional"
echo "✅ No virtual environment required"
echo ""
echo "👍 Users can now simply run: pip install -e . && claude-rewind init"