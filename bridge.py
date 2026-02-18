#!/usr/bin/env python3
"""
OpenClaw CDP Bridge — full browser automation via browser-use + cdp-use.

Connects to OpenClaw's managed Chrome via CDP for reliable browser interaction:
- Raw CDP keyboard events (isTrusted: true) for hostile editors
- Shadow DOM piercing via CDP DOM.getDocument
- AI-powered element finding via browser-use
- Full accessibility tree access
- Cross-origin iframe support

Usage:
  python3 bridge.py type --text "Hello" --tab-url "x.com"
  python3 bridge.py agent --task "Reply to the top tweet" --tab-url "x.com"
  python3 bridge.py tabs
  python3 bridge.py serve --port 18850

Environment:
  CDP_URL   Chrome CDP endpoint (default: http://localhost:18800)
  CDP_PORT  Chrome CDP port (default: 18800)
"""

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Optional

# --- CDP-level operations (minimal deps: httpx + websockets) ---

try:
    import httpx
    import websockets
except ImportError:
    print("Missing core dependencies. Install with:")
    print("  pip3 install httpx websockets")
    sys.exit(1)

CDP_BASE = os.environ.get("CDP_URL", f"http://localhost:{os.environ.get('CDP_PORT', '18800')}")


# ============================================================
# Low-level CDP operations (no browser-use dependency needed)
# ============================================================

async def get_targets():
    """List all CDP targets (tabs)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{CDP_BASE}/json")
        return resp.json()


async def get_ws_url(tab_url_filter: Optional[str] = None) -> tuple[str, str]:
    """Get CDP websocket URL for a tab."""
    targets = await get_targets()
    pages = [t for t in targets if t.get("type") == "page"]

    if tab_url_filter:
        matching = [t for t in pages if tab_url_filter.lower() in t.get("url", "").lower()]
        if not matching:
            urls = [t.get("url") for t in pages]
            raise RuntimeError(f"No tab matching '{tab_url_filter}'. Available: {urls}")
        target = matching[0]
    else:
        if not pages:
            raise RuntimeError("No page targets found")
        target = pages[0]

    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError(f"No webSocketDebuggerUrl for {target.get('url')}")
    return ws_url, target.get("url", "unknown")


async def cdp_send(ws, method: str, params: dict = None, session_id: str = None) -> dict:
    """Send CDP command and wait for response."""
    msg_id = int(time.time() * 1000000) % 10000000
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    while True:
        response = json.loads(await ws.recv())
        if response.get("id") == msg_id:
            if "error" in response:
                raise RuntimeError(f"CDP error: {response['error']}")
            return response.get("result", {})


# --- Keyboard input via CDP Input.dispatchKeyEvent ---

SPECIAL_KEYS = {
    '\n': ('Enter', 'Enter', 13),
    '\t': ('Tab', 'Tab', 9),
    '\r': ('Enter', 'Enter', 13),
}

async def dispatch_key(ws, char: str, session_id: str = None):
    """Dispatch a single key via raw CDP events."""
    if char in SPECIAL_KEYS:
        key, code, vk = SPECIAL_KEYS[char]
        for etype in ['rawKeyDown', 'char', 'keyUp']:
            params = {'type': etype, 'key': key, 'code': code,
                      'windowsVirtualKeyCode': vk, 'nativeVirtualKeyCode': vk}
            if etype == 'char':
                params['text'] = '\r' if char == '\n' else char
            await cdp_send(ws, 'Input.dispatchKeyEvent', params, session_id)
        await asyncio.sleep(0.05)  # Editors need time for block creation
    else:
        kc = ord(char)
        is_shifted = char.isupper() or char in '!@#$%^&*()_+{}|:"<>?~'
        mods = 8 if is_shifted else 0  # 8 = Shift

        code = ''
        if char.isalpha():
            code = f'Key{char.upper()}'
        elif char.isdigit():
            code = f'Digit{char}'

        for etype in ['keyDown', 'char', 'keyUp']:
            params = {'type': etype, 'key': char, 'code': code, 'text': char,
                      'windowsVirtualKeyCode': kc, 'nativeVirtualKeyCode': kc,
                      'modifiers': mods}
            await cdp_send(ws, 'Input.dispatchKeyEvent', params, session_id)
        await asyncio.sleep(0.008)


async def cdp_type(text: str, tab_url: Optional[str] = None,
                   selector: Optional[str] = None, clear: bool = False):
    """Type text using raw CDP key events. Passes isTrusted checks."""
    ws_url, url = await get_ws_url(tab_url)
    print(f"Connected: {url}")

    async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
        if selector:
            await cdp_send(ws, 'Runtime.evaluate', {
                'expression': f'document.querySelector(\'{selector}\').focus()',
            })
            await asyncio.sleep(0.1)

        if clear:
            # Cmd+A then Backspace
            await cdp_send(ws, 'Input.dispatchKeyEvent', {
                'type': 'keyDown', 'key': 'a', 'code': 'KeyA',
                'windowsVirtualKeyCode': 65, 'modifiers': 4  # Meta
            })
            await cdp_send(ws, 'Input.dispatchKeyEvent', {
                'type': 'keyUp', 'key': 'a', 'code': 'KeyA',
                'windowsVirtualKeyCode': 65, 'modifiers': 4
            })
            await asyncio.sleep(0.05)
            for et in ['rawKeyDown', 'keyUp']:
                await cdp_send(ws, 'Input.dispatchKeyEvent', {
                    'type': et, 'key': 'Backspace', 'code': 'Backspace',
                    'windowsVirtualKeyCode': 8
                })
            await asyncio.sleep(0.05)

        n = 0
        for c in text:
            await dispatch_key(ws, c)
            n += 1

        print(f"Typed {n} chars")
        return {"ok": True, "chars": n, "tab": url}


# --- CDP DOM operations ---

async def cdp_get_dom(tab_url: Optional[str] = None, depth: int = -1, pierce: bool = True):
    """Get full DOM tree including Shadow DOM."""
    ws_url, url = await get_ws_url(tab_url)
    async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
        await cdp_send(ws, 'DOM.enable')
        result = await cdp_send(ws, 'DOM.getDocument', {
            'depth': depth, 'pierce': pierce
        })
        return result


async def cdp_get_ax_tree(tab_url: Optional[str] = None):
    """Get full accessibility tree."""
    ws_url, url = await get_ws_url(tab_url)
    async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
        await cdp_send(ws, 'Accessibility.enable')
        result = await cdp_send(ws, 'Accessibility.getFullAXTree')
        return result


async def cdp_evaluate(expression: str, tab_url: Optional[str] = None):
    """Evaluate JavaScript in page context."""
    ws_url, url = await get_ws_url(tab_url)
    async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
        result = await cdp_send(ws, 'Runtime.evaluate', {
            'expression': expression, 'returnByValue': True
        })
        return result


async def cdp_click(x: int, y: int, tab_url: Optional[str] = None):
    """Click at coordinates via CDP Input.dispatchMouseEvent."""
    ws_url, url = await get_ws_url(tab_url)
    async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
        for etype in ['mousePressed', 'mouseReleased']:
            await cdp_send(ws, 'Input.dispatchMouseEvent', {
                'type': etype, 'x': x, 'y': y, 'button': 'left',
                'clickCount': 1
            })
            await asyncio.sleep(0.02)
        return {"ok": True, "x": x, "y": y}


# ============================================================
# browser-use integration (optional — for AI-powered features)
# ============================================================

async def browser_use_agent(task: str, tab_url: Optional[str] = None):
    """Run a browser-use agent task on the current page."""
    try:
        from browser_use import Agent, Browser
    except ImportError:
        return {"error": "browser-use not installed. Run: pip3 install browser-use"}

    # Try to get an LLM
    llm = None
    try:
        from browser_use import ChatBrowserUse
        llm = ChatBrowserUse()
    except Exception:
        try:
            from browser_use.llm.openai.chat import ChatOpenAI
            llm = ChatOpenAI()
        except Exception:
            pass

    if not llm:
        return {"error": "No LLM configured. Set BROWSER_USE_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY"}

    browser = Browser(cdp_url=CDP_BASE)
    agent = Agent(task=task, llm=llm, browser=browser)
    history = await agent.run(max_steps=20)

    return {
        "ok": True,
        "done": history.is_done(),
        "successful": history.is_successful(),
        "result": history.final_result(),
        "steps": history.number_of_steps(),
        "urls": history.urls(),
    }


async def browser_use_find_element(prompt: str, tab_url: Optional[str] = None):
    """Find an element using AI (browser-use's get_element_by_prompt)."""
    try:
        from browser_use import Browser
    except ImportError:
        return {"error": "browser-use not installed"}

    try:
        from browser_use import ChatBrowserUse
        llm = ChatBrowserUse()
    except Exception:
        try:
            from browser_use.llm.openai.chat import ChatOpenAI
            llm = ChatOpenAI()
        except Exception:
            return {"error": "No LLM configured"}

    browser = Browser(cdp_url=CDP_BASE)
    await browser.start()
    page = await browser.get_current_page()
    element = await page.get_element_by_prompt(prompt, llm=llm)

    if element:
        info = await element.get_basic_info()
        bbox = await element.get_bounding_box()
        return {"ok": True, "found": True, "info": str(info), "bbox": str(bbox)}
    else:
        return {"ok": True, "found": False}


# ============================================================
# HTTP Server
# ============================================================

async def handle_request(reader, writer):
    """HTTP request handler."""
    request = await reader.read(65536)
    request_str = request.decode()
    lines = request_str.split('\r\n')
    parts = lines[0].split(' ', 2)
    method = parts[0] if len(parts) > 0 else 'GET'
    path = parts[1] if len(parts) > 1 else '/'

    body = {}
    if method == 'POST' and '\r\n\r\n' in request_str:
        body_str = request_str.split('\r\n\r\n', 1)[1]
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            body = {}

    try:
        if path == '/health':
            result = {"ok": True, "cdp": CDP_BASE}

        elif path == '/tabs':
            targets = await get_targets()
            pages = [{"title": t.get("title", ""), "url": t.get("url", "")}
                     for t in targets if t.get("type") == "page"]
            result = {"ok": True, "tabs": pages}

        elif path == '/type' and method == 'POST':
            text = body.get('text', '').replace('\\n', '\n')
            r = await cdp_type(text, body.get('tabUrl'), body.get('selector'), body.get('clear', False))
            result = r

        elif path == '/click' and method == 'POST':
            r = await cdp_click(body['x'], body['y'], body.get('tabUrl'))
            result = r

        elif path == '/eval' and method == 'POST':
            r = await cdp_evaluate(body['expression'], body.get('tabUrl'))
            result = {"ok": True, "result": r}

        elif path == '/dom':
            r = await cdp_get_dom(body.get('tabUrl') if method == 'POST' else None)
            result = {"ok": True, "dom": "truncated (use CLI for full output)"}

        elif path == '/axtree':
            r = await cdp_get_ax_tree(body.get('tabUrl') if method == 'POST' else None)
            result = {"ok": True, "nodes": len(r.get("nodes", []))}

        elif path == '/agent' and method == 'POST':
            r = await browser_use_agent(body['task'], body.get('tabUrl'))
            result = r

        elif path == '/find' and method == 'POST':
            r = await browser_use_find_element(body['prompt'], body.get('tabUrl'))
            result = r

        else:
            result = {"error": f"Unknown: {method} {path}",
                      "endpoints": ["/health", "/tabs", "/type", "/click", "/eval",
                                    "/dom", "/axtree", "/agent", "/find"]}

    except Exception as e:
        result = {"error": str(e)}

    body_str = json.dumps(result, default=str)
    response = (f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body_str)}\r\n"
                f"Access-Control-Allow-Origin: *\r\n\r\n{body_str}")
    writer.write(response.encode())
    await writer.drain()
    writer.close()


async def serve(port: int = 18850):
    """Run HTTP server."""
    server = await asyncio.start_server(handle_request, '127.0.0.1', port)
    print(f"🔌 CDP Bridge on http://127.0.0.1:{port}")
    print(f"   CDP target: {CDP_BASE}")
    print(f"\n   Core (cdp-use):")
    print(f"   POST /type    — raw CDP keyboard input")
    print(f"   POST /click   — CDP mouse click (x, y)")
    print(f"   POST /eval    — evaluate JavaScript")
    print(f"   GET  /dom     — full DOM tree (Shadow DOM pierced)")
    print(f"   GET  /axtree  — full accessibility tree")
    print(f"   GET  /tabs    — list browser tabs")
    print(f"\n   AI (browser-use):")
    print(f"   POST /agent   — run browser-use agent task")
    print(f"   POST /find    — AI element finding")
    async with server:
        await server.serve_forever()


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='OpenClaw CDP Bridge')
    sub = parser.add_subparsers(dest='command')

    # type
    p = sub.add_parser('type', help='Type text via raw CDP events')
    p.add_argument('--text', '-t', required=True)
    p.add_argument('--tab-url', '-u')
    p.add_argument('--selector', '-s')
    p.add_argument('--clear', '-c', action='store_true')

    # click
    p = sub.add_parser('click', help='Click at coordinates')
    p.add_argument('--x', type=int, required=True)
    p.add_argument('--y', type=int, required=True)
    p.add_argument('--tab-url', '-u')

    # eval
    p = sub.add_parser('eval', help='Evaluate JavaScript')
    p.add_argument('--expr', '-e', required=True)
    p.add_argument('--tab-url', '-u')

    # dom
    p = sub.add_parser('dom', help='Get DOM tree (pierces Shadow DOM)')
    p.add_argument('--tab-url', '-u')

    # axtree
    p = sub.add_parser('axtree', help='Get accessibility tree')
    p.add_argument('--tab-url', '-u')

    # agent
    p = sub.add_parser('agent', help='Run browser-use agent task')
    p.add_argument('--task', '-t', required=True)
    p.add_argument('--tab-url', '-u')

    # find
    p = sub.add_parser('find', help='AI element finding')
    p.add_argument('--prompt', '-p', required=True)
    p.add_argument('--tab-url', '-u')

    # tabs
    sub.add_parser('tabs', help='List browser tabs')

    # serve
    p = sub.add_parser('serve', help='Run HTTP server')
    p.add_argument('--port', type=int, default=18850)

    args = parser.parse_args()

    if args.command == 'type':
        asyncio.run(cdp_type(args.text.replace('\\n', '\n'), args.tab_url, args.selector, args.clear))
    elif args.command == 'click':
        asyncio.run(cdp_click(args.x, args.y, args.tab_url))
    elif args.command == 'eval':
        r = asyncio.run(cdp_evaluate(args.expr, args.tab_url))
        print(json.dumps(r, indent=2))
    elif args.command == 'dom':
        r = asyncio.run(cdp_get_dom(args.tab_url))
        print(json.dumps(r, indent=2, default=str)[:5000])
    elif args.command == 'axtree':
        r = asyncio.run(cdp_get_ax_tree(args.tab_url))
        print(f"Accessibility tree: {len(r.get('nodes', []))} nodes")
    elif args.command == 'agent':
        r = asyncio.run(browser_use_agent(args.task, args.tab_url))
        print(json.dumps(r, indent=2, default=str))
    elif args.command == 'find':
        r = asyncio.run(browser_use_find_element(args.prompt, args.tab_url))
        print(json.dumps(r, indent=2))
    elif args.command == 'tabs':
        asyncio.run(list_tabs())
    elif args.command == 'serve':
        asyncio.run(serve(args.port))
    else:
        parser.print_help()


async def list_tabs():
    targets = await get_targets()
    pages = [t for t in targets if t.get("type") == "page"]
    for p in pages:
        print(f"  {p.get('title', 'untitled')[:60]}")
        print(f"    {p.get('url')}")
        print()


if __name__ == '__main__':
    main()
