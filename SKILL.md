---
name: cdp-bridge
description: Full CDP browser automation for OpenClaw. Handles hostile editors, Shadow DOM, AI element finding, and everything Playwright struggles with. Built on browser-use + cdp-use.
version: 1.0.0
homepage: https://github.com/chandika/openclaw-cdp-bridge
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# CDP Bridge for OpenClaw

Two-layer browser control: **built-in browser tool for reading, CDP bridge for everything else.**

## Routing Rules

### Use built-in browser tool when:
- Navigating to URLs
- Taking screenshots and snapshots
- Clicking simple buttons and links
- Reading page content
- Filling simple `<input>` and `<textarea>` fields

### Use CDP bridge when:
- Typing into **rich text editors** (DraftJS, TipTap, ProseMirror, Slate, Quill)
- Interacting with **Shadow DOM** elements
- Need **accessibility tree** for element discovery
- Complex **cross-origin iframe** interactions
- **AI-powered element finding** ("find the submit button" instead of CSS selectors)
- Any interaction where built-in browser tool produces garbled/empty results

### Known hostile editors (ALWAYS use CDP bridge):
- `[data-testid="tweetTextarea_0"]` — X/Twitter (DraftJS)
- `.DraftEditor-content` — any DraftJS editor
- `.ProseMirror` — ProseMirror-based editors
- `.tiptap` — TipTap editors
- `[data-slate-editor]` — Slate editors
- `.ql-editor` — Quill editors
- `[contenteditable="true"]` inside Shadow DOM

## Prerequisites

CDP bridge runs on the **host machine** (where Chrome is). Check availability:

```
# Via nodes.run on Mac
nodes.run: curl -s http://127.0.0.1:18850/health

# If not running, tell user:
"CDP bridge isn't running. Start it with:
  python3 ~/.openclaw/cdp-bridge/bridge.py serve

Or install first:
  bash <(curl -sSL https://raw.githubusercontent.com/chandika/openclaw-cdp-bridge/main/install.sh)"
```

## API Reference

All commands via `nodes.run` on the host node, or HTTP if bridge server is running.

### Core CDP Operations

#### Type text (raw CDP keyboard events)
```bash
# CLI
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py type \
  --text "Your multi-line\ntext here" \
  --tab-url "x.com" \
  --selector '[data-testid="tweetTextarea_0"]' \
  --clear
```
```json
// HTTP POST /type
{"text": "Your text", "tabUrl": "x.com", "selector": "[data-testid='tweetTextarea_0']", "clear": true}
```

#### Click at coordinates
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py click --x 500 --y 300 --tab-url "x.com"
```
```json
// HTTP POST /click
{"x": 500, "y": 300, "tabUrl": "x.com"}
```

#### Evaluate JavaScript
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py eval \
  --expr "document.querySelector('[data-testid=\"tweetTextarea_0\"]').innerText" \
  --tab-url "x.com"
```
```json
// HTTP POST /eval
{"expression": "document.title", "tabUrl": "x.com"}
```

#### Get DOM tree (pierces Shadow DOM)
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py dom --tab-url "x.com"
```

#### Get accessibility tree
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py axtree --tab-url "x.com"
```

#### List tabs
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py tabs
```

### AI-Powered Operations (requires browser-use)

#### Run agent task
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py agent \
  --task "Reply to the top tweet saying 'Great insight!'" \
  --tab-url "x.com"
```
```json
// HTTP POST /agent
{"task": "Fill in the contact form with name John Doe", "tabUrl": "example.com"}
```

#### AI element finding
```bash
nodes.run: python3 ~/.openclaw/cdp-bridge/bridge.py find \
  --prompt "the reply textbox" \
  --tab-url "x.com"
```
```json
// HTTP POST /find
{"prompt": "the submit button", "tabUrl": "example.com"}
```

## Common Workflows

### Post a tweet on X
```
1. browser navigate → https://x.com/chandika/status/XXX
2. browser act click → reply textbox ref
3. nodes.run → bridge.py type --text "tweet text" --tab-url x.com --selector '[data-testid="tweetTextarea_0"]'
4. browser evaluate → verify textContent matches
5. browser act click → Reply button
```

### Post on LinkedIn
```
1. browser navigate → https://linkedin.com/in/chandika
2. browser act click → "Start a post" button
3. nodes.run → bridge.py type --text "post text" --tab-url linkedin.com --selector '.ql-editor'
4. browser act click → Post button
```

### Interact with Shadow DOM
```
1. browser navigate → target URL
2. nodes.run → bridge.py dom --tab-url "target.com"  (gets full DOM with Shadow DOM pierced)
3. nodes.run → bridge.py eval --expr "document.querySelector('my-component').shadowRoot.querySelector('input').value"
4. nodes.run → bridge.py type --text "value" --selector "my-component" --tab-url "target.com"
```

### AI-powered form filling
```
1. browser navigate → form URL
2. nodes.run → bridge.py agent --task "Fill in the form with: Name=John, Email=john@example.com, Submit"
```

## Auto-Detection Logic

Before routing to CDP bridge, the agent should check if built-in browser can handle it:

1. Try `browser act type` with `slowly: true` on the target
2. Use `browser act evaluate` to read back the element's `textContent`
3. **If text matches** → built-in browser works, keep using it
4. **If text is garbled, empty, duplicated, or reversed** → route to CDP bridge
5. **If element matches known hostile selectors** → skip check, route directly to CDP bridge

## Fallback Chain

```
1. Built-in browser tool (Playwright) — try first
   ↓ fails?
2. CDP bridge type (raw keyboard) — try second
   ↓ fails?
3. CDP bridge agent (browser-use AI) — try third
   ↓ fails?
4. Tell user to use clipboard/manual paste
```
