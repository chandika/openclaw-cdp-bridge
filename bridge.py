#!/usr/bin/env python3
"""
OpenClaw CDP Bridge — reliable keyboard input for hostile editors.

Connects to Chrome via CDP and dispatches raw keyboard events that pass
isTrusted checks in DraftJS, TipTap, ProseMirror, Slate, etc.

Usage:
  # Type text into the focused element of a specific tab
  python3 bridge.py type --text "Hello world" --tab-url "x.com"

  # Type with newlines (Enter key)
  python3 bridge.py type --text "Line 1\nLine 2\nLine 3" --tab-url "x.com"

  # Run as HTTP server (for OpenClaw agent access)
  python3 bridge.py serve --port 18850

  # List available tabs
  python3 bridge.py tabs

Environment:
  CDP_URL     Chrome CDP endpoint (default: http://localhost:18800)
  CDP_PORT    Chrome CDP port (default: 18800)
"""

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Optional

try:
    import httpx
    import websockets
except ImportError:
    print("Missing dependencies. Install with: pip3 install httpx websockets")
    print("Or: pip3 install cdp-use")
    sys.exit(1)


CDP_BASE = os.environ.get("CDP_URL", f"http://localhost:{os.environ.get('CDP_PORT', '18800')}")


async def get_ws_url(tab_url_filter: Optional[str] = None) -> tuple[str, str]:
    """Get the CDP websocket URL for a tab, optionally filtering by URL."""
    async with httpx.AsyncClient() as client:
        # Try /json first (page-level), then /json/version (browser-level)
        resp = await client.get(f"{CDP_BASE}/json")
        targets = resp.json()

        if tab_url_filter:
            matching = [t for t in targets if tab_url_filter.lower() in t.get("url", "").lower() and t.get("type") == "page"]
            if not matching:
                raise RuntimeError(f"No tab found matching '{tab_url_filter}'. Available: {[t.get('url') for t in targets if t.get('type') == 'page']}")
            target = matching[0]
        else:
            pages = [t for t in targets if t.get("type") == "page"]
            if not pages:
                raise RuntimeError("No page targets found")
            target = pages[0]

        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError(f"No webSocketDebuggerUrl for target {target.get('url')}")

        return ws_url, target.get("url", "unknown")


async def cdp_send(ws, method: str, params: dict = None, session_id: str = None) -> dict:
    """Send a CDP command and wait for response."""
    msg_id = int(time.time() * 1000) % 1000000
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


async def dispatch_key(ws, char: str, session_id: str = None):
    """Dispatch a single key event via CDP Input.dispatchKeyEvent."""
    if char == '\n':
        # Enter key - full keydown/char/keyup cycle
        for event_type in ['rawKeyDown', 'char', 'keyUp']:
            params = {
                'type': event_type,
                'key': 'Enter',
                'code': 'Enter',
                'windowsVirtualKeyCode': 13,
                'nativeVirtualKeyCode': 13,
            }
            if event_type == 'char':
                params['text'] = '\r'
            await cdp_send(ws, 'Input.dispatchKeyEvent', params, session_id)
        await asyncio.sleep(0.05)  # DraftJS needs time to create new block
    elif char == '\t':
        for event_type in ['rawKeyDown', 'char', 'keyUp']:
            params = {
                'type': event_type,
                'key': 'Tab',
                'code': 'Tab',
                'windowsVirtualKeyCode': 9,
                'nativeVirtualKeyCode': 9,
            }
            if event_type == 'char':
                params['text'] = '\t'
            await cdp_send(ws, 'Input.dispatchKeyEvent', params, session_id)
    else:
        key_code = ord(char)
        # Determine if shift is needed
        is_upper = char.isupper()
        is_symbol = char in '!@#$%^&*()_+{}|:"<>?~'

        modifiers = 8 if (is_upper or is_symbol) else 0  # 8 = shift

        # keyDown
        await cdp_send(ws, 'Input.dispatchKeyEvent', {
            'type': 'keyDown',
            'key': char,
            'code': f'Key{char.upper()}' if char.isalpha() else f'Digit{char}' if char.isdigit() else '',
            'text': char,
            'windowsVirtualKeyCode': key_code,
            'nativeVirtualKeyCode': key_code,
            'modifiers': modifiers,
        }, session_id)

        # char
        await cdp_send(ws, 'Input.dispatchKeyEvent', {
            'type': 'char',
            'key': char,
            'text': char,
            'windowsVirtualKeyCode': key_code,
            'nativeVirtualKeyCode': key_code,
            'modifiers': modifiers,
        }, session_id)

        # keyUp
        await cdp_send(ws, 'Input.dispatchKeyEvent', {
            'type': 'keyUp',
            'key': char,
            'code': f'Key{char.upper()}' if char.isalpha() else f'Digit{char}' if char.isdigit() else '',
            'windowsVirtualKeyCode': key_code,
            'nativeVirtualKeyCode': key_code,
            'modifiers': modifiers,
        }, session_id)

    await asyncio.sleep(0.008)  # 8ms between chars — fast but not overwhelming


async def type_text(text: str, tab_url_filter: Optional[str] = None, focus_selector: Optional[str] = None):
    """Type text into the focused element using raw CDP key events."""
    ws_url, tab_url = await get_ws_url(tab_url_filter)
    print(f"Connected to: {tab_url}")

    async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
        # If a selector is provided, focus it first
        if focus_selector:
            await cdp_send(ws, 'Runtime.evaluate', {
                'expression': f'document.querySelector(\'{focus_selector}\').focus()',
                'awaitPromise': False,
            })
            await asyncio.sleep(0.1)

        # Type each character
        chars_typed = 0
        for char in text:
            await dispatch_key(ws, char)
            chars_typed += 1

        print(f"Typed {chars_typed} characters")
        return {"ok": True, "chars": chars_typed, "tab": tab_url}


async def select_all_delete(ws, session_id: str = None):
    """Select all text and delete it (Cmd+A, Backspace)."""
    # Cmd+A (Meta+A)
    await cdp_send(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyDown', 'key': 'a', 'code': 'KeyA',
        'windowsVirtualKeyCode': 65, 'nativeVirtualKeyCode': 65,
        'modifiers': 4,  # 4 = Meta/Cmd
    }, session_id)
    await cdp_send(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyUp', 'key': 'a', 'code': 'KeyA',
        'windowsVirtualKeyCode': 65, 'nativeVirtualKeyCode': 65,
        'modifiers': 4,
    }, session_id)
    await asyncio.sleep(0.05)

    # Backspace
    for event_type in ['rawKeyDown', 'keyUp']:
        await cdp_send(ws, 'Input.dispatchKeyEvent', {
            'type': event_type, 'key': 'Backspace', 'code': 'Backspace',
            'windowsVirtualKeyCode': 8, 'nativeVirtualKeyCode': 8,
        }, session_id)
    await asyncio.sleep(0.05)


async def clear_and_type(text: str, tab_url_filter: Optional[str] = None, focus_selector: Optional[str] = None):
    """Clear focused element and type new text."""
    ws_url, tab_url = await get_ws_url(tab_url_filter)
    print(f"Connected to: {tab_url}")

    async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
        if focus_selector:
            await cdp_send(ws, 'Runtime.evaluate', {
                'expression': f'document.querySelector(\'{focus_selector}\').focus()',
                'awaitPromise': False,
            })
            await asyncio.sleep(0.1)

        await select_all_delete(ws)

        chars_typed = 0
        for char in text:
            await dispatch_key(ws, char)
            chars_typed += 1

        print(f"Typed {chars_typed} characters")
        return {"ok": True, "chars": chars_typed, "tab": tab_url}


async def list_tabs():
    """List all available browser tabs."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{CDP_BASE}/json")
        targets = resp.json()
        pages = [t for t in targets if t.get("type") == "page"]
        for p in pages:
            print(f"  {p.get('title', 'untitled')[:60]}")
            print(f"    URL: {p.get('url')}")
            print(f"    WS:  {p.get('webSocketDebuggerUrl', 'n/a')}")
            print()
        return pages


# --- HTTP Server mode for OpenClaw agent access ---

async def handle_http(reader, writer):
    """Simple HTTP handler for agent requests."""
    request = await reader.read(65536)
    request_str = request.decode()

    # Parse basic HTTP
    lines = request_str.split('\r\n')
    method, path, _ = lines[0].split(' ', 2)

    # Parse body for POST
    body = {}
    if method == 'POST':
        body_str = request_str.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request_str else '{}'
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            body = {}

    try:
        if path == '/tabs':
            result = await list_tabs()
            response_body = json.dumps({"ok": True, "tabs": result})

        elif path == '/type' and method == 'POST':
            text = body.get('text', '')
            tab_url = body.get('tabUrl')
            selector = body.get('selector')
            clear = body.get('clear', False)

            if clear:
                result = await clear_and_type(text, tab_url, selector)
            else:
                result = await type_text(text, tab_url, selector)
            response_body = json.dumps(result)

        elif path == '/health':
            response_body = json.dumps({"ok": True, "cdp": CDP_BASE})

        else:
            response_body = json.dumps({"error": f"Unknown path: {path}"})

    except Exception as e:
        response_body = json.dumps({"error": str(e)})

    response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(response_body)}\r\nAccess-Control-Allow-Origin: *\r\n\r\n{response_body}"
    writer.write(response.encode())
    await writer.drain()
    writer.close()


async def serve(port: int = 18850):
    """Run HTTP server for agent access."""
    server = await asyncio.start_server(handle_http, '127.0.0.1', port)
    print(f"CDP Bridge server running on http://127.0.0.1:{port}")
    print(f"  POST /type  — type text (body: {{text, tabUrl?, selector?, clear?}})")
    print(f"  GET  /tabs  — list browser tabs")
    print(f"  GET  /health — health check")
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='OpenClaw CDP Bridge')
    sub = parser.add_subparsers(dest='command')

    # type command
    type_cmd = sub.add_parser('type', help='Type text into focused element')
    type_cmd.add_argument('--text', '-t', required=True, help='Text to type (use \\n for newlines)')
    type_cmd.add_argument('--tab-url', '-u', help='Filter tab by URL substring')
    type_cmd.add_argument('--selector', '-s', help='CSS selector to focus before typing')
    type_cmd.add_argument('--clear', '-c', action='store_true', help='Clear existing text first')

    # tabs command
    sub.add_parser('tabs', help='List browser tabs')

    # serve command
    serve_cmd = sub.add_parser('serve', help='Run HTTP server')
    serve_cmd.add_argument('--port', '-p', type=int, default=18850, help='Port (default: 18850)')

    args = parser.parse_args()

    if args.command == 'type':
        text = args.text.replace('\\n', '\n')
        if args.clear:
            asyncio.run(clear_and_type(text, args.tab_url, args.selector))
        else:
            asyncio.run(type_text(text, args.tab_url, args.selector))
    elif args.command == 'tabs':
        asyncio.run(list_tabs())
    elif args.command == 'serve':
        asyncio.run(serve(args.port))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
