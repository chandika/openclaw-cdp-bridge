---
name: cdp-bridge
description: Reliable browser typing for OpenClaw via CDP. Handles hostile editors (DraftJS, TipTap, ProseMirror) that reject Playwright input. Complements the built-in browser tool — use browser for reading, cdp-bridge for writing.
version: 1.0.0
homepage: https://github.com/chandika/openclaw-cdp-bridge
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# CDP Bridge for OpenClaw

Use the built-in browser tool for reading pages. Use this bridge for typing into hostile editors.

## When to Use This

**Use the built-in browser tool for:**
- Navigation, clicking, scrolling
- Snapshots, screenshots, PDFs
- Reading page content
- Simple form inputs (`<input>`, `<textarea>`)
- Clicking buttons (Reply, Submit, etc.)

**Use CDP Bridge for:**
- Typing into rich text editors (DraftJS, TipTap, ProseMirror, Slate)
- Any contenteditable div that rejects Playwright's `type()` or `fill()`
- Multi-line text entry in editors that check `event.isTrusted`
- Sites known to need it: **X/Twitter**, **Grok**, **Notion**, **Slack web**, **LinkedIn post editor**

## How It Works

The bridge runs on the host machine (where Chrome is) and dispatches raw CDP `Input.dispatchKeyEvent` events. These events have `isTrusted: true` — indistinguishable from real keyboard input.

## Detection: When to Route to CDP Bridge

Before typing into any contenteditable element, check if the built-in browser tool can handle it:

1. Try `type` with `slowly: true` on the target ref
2. Read back the element's `textContent` via `evaluate`
3. If the text doesn't match (garbled, duplicated, empty, reversed) → route to CDP Bridge

**Known hostile editors (always use CDP Bridge):**
- `data-testid="tweetTextarea_0"` (X/Twitter DraftJS)
- `.ProseMirror` (ProseMirror-based editors)
- `.tiptap` (TipTap editors)
- `[data-slate-editor]` (Slate editors)
- `.DraftEditor-content` (any DraftJS editor)
- `.ql-editor` (Quill editors)

## Prerequisites

The CDP Bridge must be running on the host machine. Check with:

```bash
# Via nodes.run
nodes.run on "Mac Browser Node": curl -s http://127.0.0.1:18850/health

# Or check if bridge.py is available
nodes.run on "Mac Browser Node": python3 /path/to/bridge.py tabs
```

If not running, tell the user:
```
CDP Bridge isn't running on your Mac. Start it with:
  cd openclaw-cdp-bridge && python3 bridge.py serve
Or for one-off typing:
  python3 bridge.py type --text "your text" --tab-url "x.com"
```

## API

### Via nodes.run (CLI mode)

```bash
# Type text into the focused element of a tab matching "x.com"
nodes.run: python3 bridge.py type --text "Hello world" --tab-url "x.com"

# Type with newlines
nodes.run: python3 bridge.py type --text "Line 1\nLine 2" --tab-url "x.com"

# Clear existing text first, then type
nodes.run: python3 bridge.py type --text "New text" --tab-url "x.com" --clear

# Focus a specific element before typing
nodes.run: python3 bridge.py type --text "tweet text" --tab-url "x.com" --selector '[data-testid="tweetTextarea_0"]'
```

### Via HTTP (server mode)

If the bridge is running as a server (`python3 bridge.py serve --port 18850`):

```bash
# Type text
curl -X POST http://127.0.0.1:18850/type \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "tabUrl": "x.com"}'

# Clear and type
curl -X POST http://127.0.0.1:18850/type \
  -H "Content-Type: application/json" \
  -d '{"text": "New text", "tabUrl": "x.com", "clear": true, "selector": "[data-testid=\"tweetTextarea_0\"]"}'

# List tabs
curl http://127.0.0.1:18850/tabs
```

## Workflow: Posting a Tweet

Here's the complete flow combining browser tool + CDP bridge:

1. **Navigate** (browser tool): `browser navigate to https://x.com/chandika/status/XXX`
2. **Click reply box** (browser tool): `browser act click ref=e40` (the reply textbox)
3. **Wait for focus** (browser tool): snapshot to confirm textarea is active
4. **Type text** (CDP bridge): `nodes.run: python3 bridge.py type --text "tweet content" --tab-url "x.com" --selector '[data-testid="tweetTextarea_0"]'`
5. **Verify** (browser tool): `browser evaluate` to read back textContent
6. **Click Reply** (browser tool): `browser act click` on the Reply button

Steps 1-3 and 5-6 use OpenClaw's built-in browser. Only step 4 uses CDP bridge.

## Workflow: Posting on LinkedIn

1. **Navigate** (browser tool): `browser navigate to https://linkedin.com/in/chandika`
2. **Click "Start a post"** (browser tool)
3. **Type** (CDP bridge): `nodes.run: python3 bridge.py type --text "post content" --tab-url "linkedin.com" --selector '.ql-editor'`
4. **Click Post** (browser tool)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CDP_URL` | `http://localhost:18800` | Chrome CDP endpoint URL |
| `CDP_PORT` | `18800` | Chrome CDP port (ignored if CDP_URL is set) |

## Troubleshooting

**"No tab found matching..."**
- Chrome must be running with the target page open
- Use `python3 bridge.py tabs` to see available tabs

**"Connection refused"**
- Chrome's CDP port must be accessible. OpenClaw's managed browser exposes port 18800 by default.
- Check: `curl -s http://localhost:18800/json`

**Text appears garbled**
- Increase delay: edit `bridge.py` and change `asyncio.sleep(0.008)` to `0.02`
- Some editors need more time between keystrokes

**Bridge not reachable from OpenClaw**
- The bridge runs on the host, not in Docker
- Use `nodes.run` to execute commands on the host
- Or run bridge in server mode and ensure port 18850 is accessible
