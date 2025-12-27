#!/usr/bin/env python3
"""Read console logs from a connected React Native app."""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
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
        # Find specific app by ID
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

    # Multiple apps, no ID specified
    print("Error: Multiple apps connected. Specify --app-id.", file=sys.stderr)
    print("Available apps:", file=sys.stderr)
    for app in apps:
        print(f"  - {app.get('id')}: {app.get('title')}", file=sys.stderr)
    sys.exit(1)


def format_remote_object(obj: dict) -> str:
    """Format a Chrome DevTools Protocol RemoteObject."""
    obj_type = obj.get("type", "unknown")

    if obj_type == "undefined":
        return "undefined"
    if obj.get("subtype") == "null":
        return "null"
    if "description" in obj:
        return obj["description"]
    if "value" in obj:
        val = obj["value"]
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2)
        return str(val)
    if "unserializableValue" in obj:
        return obj["unserializableValue"]

    subtype = obj.get("subtype", "")
    return f"[{obj_type}{' ' + subtype if subtype else ''}]"


def read_logs(ws_url: str, max_logs: int = 100, pattern: Optional[str] = None, timeout: float = 5.0) -> list[dict]:
    """Connect to app and read console logs."""
    ensure_websocket()

    logs = []
    message_id = 1
    compiled_pattern = re.compile(pattern) if pattern else None

    UNSUPPORTED_MSG = "You are using an unsupported debugging client"

    def on_message(ws, message):
        nonlocal logs
        try:
            data = json.loads(message)
            if data.get("method") == "Runtime.consoleAPICalled":
                params = data.get("params", {})
                args = params.get("args", [])
                text = " ".join(format_remote_object(arg) for arg in args)

                # Skip unsupported client message
                if UNSUPPORTED_MSG in text:
                    return

                level = params.get("type", "log")

                # Apply filter if specified
                if compiled_pattern and not compiled_pattern.search(text):
                    return

                log_entry = {
                    "level": level,
                    "text": text,
                }

                # Include stack trace for errors/warnings
                if level in ("error", "warning") and "stackTrace" in params:
                    frames = params["stackTrace"].get("callFrames", [])
                    if frames:
                        top = frames[0]
                        log_entry["location"] = f"{top.get('functionName', 'anonymous')} (line {top.get('lineNumber', '?')})"

                logs.append(log_entry)

                if len(logs) >= max_logs:
                    ws.close()
        except json.JSONDecodeError:
            pass

    def on_open(ws):
        nonlocal message_id
        ws.send(json.dumps({"id": message_id, "method": "Runtime.enable"}))
        message_id += 1

    def on_error(ws, error):
        print(f"WebSocket error: {error}", file=sys.stderr)

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

    return logs


def main():
    parser = argparse.ArgumentParser(
        description="Read console logs from a connected React Native app"
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
        "--max-logs", "-n",
        type=int,
        default=100,
        help="Maximum logs to capture (default: 100)"
    )
    parser.add_argument(
        "--filter", "-f",
        help="Regex pattern to filter logs"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=5.0,
        help="Seconds to wait for logs (default: 5)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    args = parser.parse_args()

    app = resolve_app(args.app_id, args.metro_url)
    ws_url = app.get("webSocketDebuggerUrl")

    if not ws_url:
        print("Error: No WebSocket debugger URL for this app.", file=sys.stderr)
        sys.exit(1)

    logs = read_logs(ws_url, args.max_logs, args.filter, args.timeout)

    if args.json:
        print(json.dumps(logs, indent=2))
    else:
        if not logs:
            print("No logs received.")
        else:
            for log in logs:
                level = log["level"]
                text = log["text"]

                if level == "error":
                    prefix = "ERROR: "
                elif level == "warning":
                    prefix = "WARNING: "
                else:
                    prefix = ""

                print(f"{prefix}{text}")

                if "location" in log:
                    print(f"  at {log['location']}")


if __name__ == "__main__":
    main()
