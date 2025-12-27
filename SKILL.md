---
name: react-native-debugger
description: Debug React Native apps by reading console logs and executing JavaScript in running apps via Metro. Use when debugging RN apps, reading app logs, inspecting app state, running diagnostic code, or troubleshooting React Native issues. Requires Metro bundler running (typically port 8081).
---

# React Native Debugger

Connect to running React Native apps via Metro bundler to read console logs and execute JavaScript.

## Prerequisites

Requires `websocket-client`: `pip install websocket-client`

## Usage

**Assume a single app is connected.** Just call `read_logs.py` or `execute_in_app.py` directly - they auto-select the app when only one is connected (the typical case).

```bash
# Read recent logs
python scripts/read_logs.py

# Execute JS in app
python scripts/execute_in_app.py "Date.now()"
```

Only use `discover_apps.py` or `--app-id` when you get an error about multiple apps being connected.

## Tools

### read_logs.py

Stream console logs from app.

```bash
python scripts/read_logs.py [--max-logs 100] [--filter "error|warn"] [--timeout 5]
```

- `--filter`: Regex to filter log messages
- `--timeout`: Seconds to collect logs (default: 5)
- `--app-id`: Only needed if multiple apps connected
- `--metro-url`: Override Metro URL (default: http://localhost:8081)

Errors and warnings include stack trace location.

### execute_in_app.py

Run JavaScript in the app's context (REPL-style).

```bash
python scripts/execute_in_app.py "expression" [--no-await] [--timeout 10]

# Or pipe expression
echo "globalThis.myVar" | python scripts/execute_in_app.py
```

- `--no-await`: Don't await Promise results
- `--app-id`: Only needed if multiple apps connected
- `--metro-url`: Override Metro URL (default: http://localhost:8081)
- Supports any JS: variable access, function calls, IIFEs, etc.

### discover_apps.py

Find React Native apps connected to Metro. **Only use this as a fallback** when `read_logs.py` or `execute_in_app.py` report multiple apps connected.

```bash
python scripts/discover_apps.py [--metro-url URL] [--json]
```

## Common Patterns

**Check component state:**
```bash
python scripts/execute_in_app.py "globalThis.__REDUX_DEVTOOLS_EXTENSION__ && globalThis.__REDUX_DEVTOOLS_EXTENSION__.getState()"
```

**Filter for errors:**
```bash
python scripts/read_logs.py --filter "error|Error|ERROR"
```

**Run diagnostic code:**
```bash
python scripts/execute_in_app.py "(async () => { const resp = await fetch('http://api.example.com/health'); return resp.status; })()"
```
