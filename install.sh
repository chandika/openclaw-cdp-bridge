#!/bin/bash
# OpenClaw CDP Bridge — one-line install for the host machine
# Run this on your Mac/Linux where Chrome is running

set -e

echo "🔌 Installing OpenClaw CDP Bridge..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Install it first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PYTHON_VERSION"

# Install deps
echo "  Installing dependencies..."
pip3 install --quiet httpx websockets 2>/dev/null || python3 -m pip install --quiet httpx websockets

# Determine install location
INSTALL_DIR="${OPENCLAW_CDP_BRIDGE_DIR:-$HOME/.openclaw/cdp-bridge}"
mkdir -p "$INSTALL_DIR"

# Download bridge.py
BRIDGE_URL="https://raw.githubusercontent.com/chandika/openclaw-cdp-bridge/main/bridge.py"
echo "  Downloading bridge.py to $INSTALL_DIR..."
curl -sSL "$BRIDGE_URL" -o "$INSTALL_DIR/bridge.py"
chmod +x "$INSTALL_DIR/bridge.py"

# Test CDP connection
CDP_PORT="${CDP_PORT:-18800}"
echo "  Testing CDP connection on port $CDP_PORT..."
if curl -s "http://localhost:$CDP_PORT/json" > /dev/null 2>&1; then
    TAB_COUNT=$(curl -s "http://localhost:$CDP_PORT/json" | python3 -c "import sys,json; print(len([t for t in json.load(sys.stdin) if t.get('type')=='page']))")
    echo "  ✅ Chrome CDP reachable — $TAB_COUNT tabs found"
else
    echo "  ⚠️  Chrome CDP not reachable on port $CDP_PORT"
    echo "     Start Chrome with: openclaw browser --browser-profile openclaw start"
    echo "     Or set CDP_PORT to your Chrome's debugging port"
fi

echo ""
echo "✅ Installed to $INSTALL_DIR/bridge.py"
echo ""
echo "Usage:"
echo "  # Type text into X"
echo "  python3 $INSTALL_DIR/bridge.py type --text 'Hello world' --tab-url x.com"
echo ""
echo "  # Run as server (for OpenClaw agent)"
echo "  python3 $INSTALL_DIR/bridge.py serve"
echo ""
echo "  # List tabs"
echo "  python3 $INSTALL_DIR/bridge.py tabs"
