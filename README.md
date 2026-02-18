# 🔌 OpenClaw CDP Bridge

Reliable browser automation for OpenClaw — including typing into hostile editors (DraftJS, TipTap, ProseMirror, Slate) that reject standard Playwright input.

## The Problem

OpenClaw's built-in browser tool uses Playwright, which works great for:
- ✅ Navigation, clicking, reading pages
- ✅ Screenshots, snapshots, PDFs
- ✅ Simple form inputs

But fails on:
- ❌ Rich text editors (DraftJS on X/Twitter, TipTap on Grok, Slate, ProseMirror)
- ❌ Multi-line typing in contenteditable divs
- ❌ Any editor that checks `event.isTrusted`

These editors only accept events from the browser's native input pipeline — not Playwright's synthetic events.

## The Solution

This package provides a **CDP (Chrome DevTools Protocol) bridge** that:
1. Runs a lightweight helper on the host machine (where Chrome is)
2. Connects directly to Chrome's CDP websocket
3. Uses `Input.dispatchKeyEvent` for raw keyboard events (`isTrusted: true`)
4. Exposes a simple API the OpenClaw agent can call via `nodes.run` or HTTP

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────┐
│  OpenClaw Agent      │     │  CDP Bridge (host)    │     │  Chrome      │
│  (Docker/sandbox)    │────▶│  Python script         │────▶│  (host Mac)  │
│                      │     │  via nodes.run or HTTP │     │  CDP :18800  │
│  browser tool: read  │     │                        │     │              │
│  cdp-bridge: write   │     │  Input.dispatchKeyEvent│     │  DraftJS ✅  │
└─────────────────────┘     └──────────────────────┘     └─────────────┘
```

**OpenClaw's browser tool** handles reading (snapshots, screenshots, navigation, clicking).
**CDP Bridge** handles writing (typing into any editor, including hostile ones).

## Install

### Host-side (where Chrome runs)

```bash
pip3 install cdp-use httpx
# Or: uv pip install cdp-use httpx
```

Clone or install the bridge:
```bash
git clone https://github.com/chandika/openclaw-cdp-bridge
cd openclaw-cdp-bridge
```

### OpenClaw-side

```bash
clawhub install chandika/cdp-bridge
```

Or copy `SKILL.md` to your OpenClaw skills directory.

## Usage

The agent calls the bridge when it needs to type into a hostile editor:

```
Agent: "I need to type a tweet on X"
→ Uses browser tool to navigate to X, click reply box
→ Uses cdp-bridge to type the text via raw CDP events
→ Uses browser tool to click Reply button
```

## Components

- `bridge.py` — Host-side CDP bridge server/CLI
- `SKILL.md` — OpenClaw skill with routing logic
- `install.sh` — One-line host setup

## License

MIT
