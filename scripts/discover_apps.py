#!/usr/bin/env python3
"""Discover React Native apps connected to Metro bundler."""

import argparse
import json
import sys
import urllib.request
import urllib.error

DEFAULT_METRO_URL = "http://localhost:8081"


def discover_apps(metro_url: str = DEFAULT_METRO_URL) -> list[dict]:
    """Query Metro's /json endpoint to find connected apps."""
    url = f"{metro_url.rstrip('/')}/json"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            apps = json.loads(response.read().decode())
            # Filter to React Native apps (have reactNative metadata)
            rn_apps = [
                app for app in apps
                if app.get("reactNative") or "React Native" in app.get("description", "")
            ]
            return rn_apps
    except urllib.error.URLError as e:
        print(f"Error: Cannot connect to Metro at {metro_url}. Is Metro running?", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid response from Metro: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Discover React Native apps connected to Metro bundler"
    )
    parser.add_argument(
        "--metro-url",
        default=DEFAULT_METRO_URL,
        help=f"Metro server URL (default: {DEFAULT_METRO_URL})"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    args = parser.parse_args()

    apps = discover_apps(args.metro_url)

    if not apps:
        print("No React Native apps connected.", file=sys.stderr)
        print("Ensure your app is running and connected to Metro.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(apps, indent=2))
    else:
        print(f"Found {len(apps)} connected app(s):\n")
        for i, app in enumerate(apps, 1):
            app_id = app.get("id", "unknown")
            title = app.get("title", "Unknown")
            device = app.get("deviceName", "Unknown device")
            ws_url = app.get("webSocketDebuggerUrl", "")
            print(f"{i}. {title}")
            print(f"   ID: {app_id}")
            print(f"   Device: {device}")
            print(f"   WebSocket: {ws_url}")
            print()


if __name__ == "__main__":
    main()
