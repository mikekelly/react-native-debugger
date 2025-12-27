#!/usr/bin/env python3
"""Execute JavaScript in a connected React Native app."""

import argparse
import json
import sys
import urllib.request
from typing import Optional

DEFAULT_METRO_URL = "http://localhost:8081"

# WebSocket library - will be imported dynamically
websocket = None


def ensure_websocket():
    """Ensure websocket-client is available."""
    global websocket
    if websocket is None:
        try:
            import websocket as ws
            websocket = ws
        except ImportError:
            print("Error: websocket-client not installed.", file=sys.stderr)
            print("Install with: pip install websocket-client", file=sys.stderr)
            sys.exit(1)


def discover_apps(metro_url: str = DEFAULT_METRO_URL) -> list[dict]:
    """Query Metro's /json endpoint to find connected apps."""
    url = f"{metro_url.rstrip('/')}/json"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            apps = json.loads(response.read().decode())
            return [app for app in apps if app.get("reactNative") or "React Native" in app.get("description", "")]
    except Exception:
        return []


def resolve_app(app_id: Optional[str], metro_url: str) -> dict:
    """Resolve app_id to a connected app. Auto-selects if only one app connected."""
    apps = discover_apps(metro_url)

    if not apps:
        print("Error: No React Native apps connected.", file=sys.stderr)
        print("Ensure your app is running and connected to Metro.", file=sys.stderr)
        sys.exit(1)

    if app_id:
        for app in apps:
            if app.get("id") == app_id:
                return app
        print(f"Error: App with ID '{app_id}' not found.", file=sys.stderr)
        print("Available apps:", file=sys.stderr)
        for app in apps:
            print(f"  - {app.get('id')}: {app.get('title')}", file=sys.stderr)
        sys.exit(1)

    if len(apps) == 1:
        return apps[0]

    print("Error: Multiple apps connected. Specify --app-id.", file=sys.stderr)
    print("Available apps:", file=sys.stderr)
    for app in apps:
        print(f"  - {app.get('id')}: {app.get('title')}", file=sys.stderr)
    sys.exit(1)


def format_result(result: dict) -> str:
    """Format a Chrome DevTools Protocol RemoteObject result."""
    obj_type = result.get("type", "unknown")

    if obj_type == "undefined":
        return "undefined"
    if result.get("subtype") == "null":
        return "null"

    # For objects/arrays with a value, stringify it
    if "value" in result:
        val = result["value"]
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2)
        return str(val)

    # Use description for complex objects
    if "description" in result:
        return result["description"]

    # Handle unserializable values (NaN, Infinity, etc.)
    if "unserializableValue" in result:
        return result["unserializableValue"]

    subtype = result.get("subtype", "")
    return f"[{obj_type}{' ' + subtype if subtype else ''}]"


def execute_in_app(ws_url: str, expression: str, await_promise: bool = True, timeout: float = 10.0) -> dict:
    """Execute JavaScript expression in the app and return result."""
    ensure_websocket()

    result = {"success": False, "output": None, "error": None}
    message_id = 1
    runtime_enabled = False

    def on_message(ws, message):
        nonlocal result, message_id, runtime_enabled
        try:
            data = json.loads(message)
            msg_id = data.get("id")

            # Runtime.enable response
            if msg_id == 1:
                runtime_enabled = True
                # Send the evaluate request
                ws.send(json.dumps({
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": await_promise,
                        "userGesture": True,
                        "generatePreview": True,
                    }
                }))

            # Runtime.evaluate response
            elif msg_id == 2:
                if "error" in data:
                    result["error"] = data["error"].get("message", "Unknown error")
                elif "result" in data:
                    eval_result = data["result"]
                    if "exceptionDetails" in eval_result:
                        exc = eval_result["exceptionDetails"]
                        exc_obj = exc.get("exception", {})
                        result["error"] = exc_obj.get("description") or exc.get("text", "Exception")
                    elif "result" in eval_result:
                        result["success"] = True
                        result["output"] = format_result(eval_result["result"])
                    else:
                        result["success"] = True
                        result["output"] = "undefined"
                ws.close()

        except json.JSONDecodeError:
            pass

    def on_open(ws):
        nonlocal message_id
        ws.send(json.dumps({"id": message_id, "method": "Runtime.enable"}))
        message_id += 1

    def on_error(ws, error):
        nonlocal result
        result["error"] = f"WebSocket error: {error}"

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
    )

    # Run with timeout
    import threading
    def run_ws():
        ws.run_forever()

    thread = threading.Thread(target=run_ws)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        ws.close()
        if not result["success"] and not result["error"]:
            result["error"] = "Timeout: Expression took too long to evaluate"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Execute JavaScript in a connected React Native app"
    )
    parser.add_argument(
        "expression",
        nargs="?",
        help="JavaScript expression to evaluate"
    )
    parser.add_argument(
        "--app-id",
        help="App ID to connect to (optional if only one app connected)"
    )
    parser.add_argument(
        "--metro-url",
        default=DEFAULT_METRO_URL,
        help=f"Metro server URL (default: {DEFAULT_METRO_URL})"
    )
    parser.add_argument(
        "--no-await",
        action="store_true",
        help="Don't await Promise results"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=10.0,
        help="Seconds to wait for result (default: 10)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    args = parser.parse_args()

    # Read expression from stdin if not provided
    if args.expression:
        expression = args.expression
    else:
        expression = sys.stdin.read().strip()

    if not expression:
        print("Error: No expression provided.", file=sys.stderr)
        print("Usage: execute_in_app.py 'expression' or pipe via stdin", file=sys.stderr)
        sys.exit(1)

    app = resolve_app(args.app_id, args.metro_url)
    ws_url = app.get("webSocketDebuggerUrl")

    if not ws_url:
        print("Error: No WebSocket debugger URL for this app.", file=sys.stderr)
        sys.exit(1)

    result = execute_in_app(ws_url, expression, not args.no_await, args.timeout)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print(result["output"])
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
