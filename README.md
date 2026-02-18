# 🔌 OpenClaw CDP Bridge

Full CDP browser automation for OpenClaw — powered by [browser-use](https://github.com/browser-use/browser-use) and [cdp-use](https://github.com/browser-use/cdp-use).

Connects to OpenClaw's managed Chrome instance and provides reliable browser interaction that goes beyond Playwright — Shadow DOM, hostile editors (DraftJS/TipTap/Slate), AI-powered element finding, and raw CDP access.

## Why

OpenClaw's built-in browser tool uses Playwright via a relay. It's great for reading pages, clicking, and navigating. But it struggles with:

- **Hostile editors** (DraftJS on X, TipTap, ProseMirror, Slate) — `event.isTrusted` checks reject Playwright input
- **Shadow DOM** — deeply nested shadow roots are hard to pierce with selectors
- **Complex interactions** — drag-and-drop across iframes, multi-step form wizards
- **Dynamic SPAs** — React/Vue apps that constantly re-render DOM

browser-use solves all of this. It's the #1 open-source browser agent framework (78K+ GitHub stars), built on pure CDP. This package bridges it to OpenClaw.

## Architecture

```
┌───────────────────────┐
│  OpenClaw Agent        │
│  (Docker container)    │
│                        │
│  browser tool → read   │─── Playwright relay ──┐
│  cdp-bridge  → write   │─── nodes.run / HTTP ──┤
└───────────────────────┘                        │
                                                  ▼
┌───────────────────────┐     ┌─────────────────┐
│  CDP Bridge (host)     │────▶│  Chrome (host)   │
│  browser-use + cdp-use │     │  CDP :18800      │
│                        │     │                  │
│  • AI element finding  │     │  Shadow DOM ✅   │
│  • Raw CDP keyboard    │     │  DraftJS ✅      │
│  • Shadow DOM piercing │     │  iFrames ✅      │
│  • Form automation     │     │  SPAs ✅         │
└───────────────────────┘     └─────────────────┘
```

## Install (host machine)

```bash
# One-line install
bash <(curl -sSL https://raw.githubusercontent.com/chandika/openclaw-cdp-bridge/main/install.sh)

# Or manual
pip3 install browser-use cdp-use httpx websockets
git clone https://github.com/chandika/openclaw-cdp-bridge
```

## Quick Start

### CLI — Type into X/Twitter

```bash
# Connect to OpenClaw's Chrome and type a tweet
python3 bridge.py type --text "Hello from CDP bridge" --tab-url "x.com" \
  --selector '[data-testid="tweetTextarea_0"]'
```

### CLI — Run a browser-use agent task

```bash
# AI-powered: describe what you want in natural language
python3 bridge.py agent --task "Reply to the top tweet with 'Great post!'" --tab-url "x.com"
```

### HTTP Server — For OpenClaw agent access

```bash
# Start server
python3 bridge.py serve --port 18850

# Agent calls via nodes.run or HTTP:
# POST /type   — raw CDP typing
# POST /agent  — AI-powered browser task
# POST /click  — CDP click at coordinates or selector
# POST /eval   — evaluate JavaScript
# GET  /tabs   — list browser tabs
# GET  /state  — get page DOM/accessibility tree
```

### Python — Connect to existing Chrome

```python
from browser_use import Browser

# Connect to OpenClaw's managed Chrome
browser = Browser(cdp_url="http://localhost:18800")
await browser.start()

# AI-powered element finding
page = await browser.get_current_page()
reply_box = await page.must_get_element_by_prompt("tweet reply textbox", llm=llm)
await reply_box.fill("Hello world")  # Uses CDP, not Playwright
```

## OpenClaw Skill

Install the skill so the agent knows when to use CDP bridge:

```bash
clawhub install chandika/cdp-bridge
```

The skill teaches the agent:
1. **When to use built-in browser** — reading, navigating, clicking buttons, screenshots
2. **When to use CDP bridge** — typing into editors, Shadow DOM, complex interactions
3. **How to call the bridge** — via `nodes.run` or HTTP API
4. **Auto-detection** — recognizes hostile editors by CSS selectors and routes accordingly

## What browser-use Gives Us

| Capability | Playwright (built-in) | CDP Bridge (browser-use) |
|---|---|---|
| Navigate / click | ✅ | ✅ |
| Read page / snapshot | ✅ | ✅ |
| Type into `<input>` | ✅ | ✅ |
| Type into DraftJS | ❌ | ✅ (`Input.dispatchKeyEvent`) |
| Type into TipTap/Slate | ❌ | ✅ |
| Shadow DOM | 🟡 (limited) | ✅ (full CDP DOM.getDocument with pierce) |
| AI element finding | ❌ | ✅ (`get_element_by_prompt`) |
| Cross-origin iframes | 🟡 | ✅ |
| Accessibility tree | 🟡 | ✅ (full AX tree via CDP) |
| Form automation | 🟡 | ✅ (multi-step, adaptive) |
| Event.isTrusted | ❌ (synthetic) | ✅ (native CDP events) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CDP_URL` | `http://localhost:18800` | Chrome CDP endpoint |
| `CDP_PORT` | `18800` | Chrome CDP port |
| `BROWSER_USE_API_KEY` | — | Optional: browser-use cloud API key |
| `OPENAI_API_KEY` | — | For AI element finding (optional) |
| `ANTHROPIC_API_KEY` | — | For AI element finding (optional) |

## License

MIT
