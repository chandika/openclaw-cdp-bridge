#!/bin/bash
# OpenClaw CDP Bridge — one-line install
# Run on the host machine where Chrome is

set -e

echo "🔌 Installing OpenClaw CDP Bridge..."

# Check Python 3.11+
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3.11+ required. Install from python.org"
    exit 1
fi

PY_VER=$(python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')")
PY_MIN=$(python3 -c "import sys; print(1 if sys.version_info >= (3,11) else 0)")
echo "  Python: $PY_VER"
if [ "$PY_MIN" = "0" ]; then
    echo "❌ Python 3.11+ required (you have $PY_VER)"
    exit 1
fi

# Install dependencies
echo "  Installing core deps (httpx, websockets)..."
pip3 install -q httpx websockets 2>/dev/null || python3 -m pip install -q httpx websockets

# Optional: browser-use for AI features
read -p "  Install browser-use for AI features? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  Installing browser-use + cdp-use..."
    pip3 install -q browser-use cdp-use 2>/dev/null || python3 -m pip install -q browser-use cdp-use
fi

# Install bridge
INSTALL_DIR="${OPENCLAW_CDP_BRIDGE_DIR:-$HOME/.openclaw/cdp-bridge}"
mkdir -p "$INSTALL_DIR"

REPO_URL="https://raw.githubusercontent.com/chandika/openclaw-cdp-bridge/main"
echo "  Downloading to $INSTALL_DIR..."
curl -sSL "$REPO_URL/bridge.py" -o "$INSTALL_DIR/bridge.py"
chmod +x "$INSTALL_DIR/bridge.py"

# Test CDP
CDP_PORT="${CDP_PORT:-18800}"
echo "  Testing CDP on port $CDP_PORT..."
if curl -s "http://localhost:$CDP_PORT/json" > /dev/null 2>&1; then
    TAB_COUNT=$(curl -s "http://localhost:$CDP_PORT/json" | python3 -c "import sys,json; print(len([t for t in json.load(sys.stdin) if t.get('type')=='page']))" 2>/dev/null || echo "?")
    echo "  ✅ Chrome CDP reachable — $TAB_COUNT tabs"
else
    echo "  ⚠️  Chrome CDP not reachable on port $CDP_PORT"
    echo "     Start OpenClaw's managed browser first"
fi

echo ""
echo "✅ Installed!"
echo ""
echo "Commands:"
echo "  python3 $INSTALL_DIR/bridge.py tabs"
echo "  python3 $INSTALL_DIR/bridge.py type --text 'Hello' --tab-url x.com"
echo "  python3 $INSTALL_DIR/bridge.py serve  # HTTP server for OpenClaw"
echo ""
echo "Start as service:"
echo "  nohup python3 $INSTALL_DIR/bridge.py serve &"
