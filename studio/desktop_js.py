"""Read native webview snapshots without using JavaScript eval."""
import json


def read_snapshot(window, expression):
    result = window.run_js(f'JSON.stringify({expression})')
    # Cocoa returns the JS string directly; WebView2 wraps it in JSON once more.
    for _ in range(2):
        if not isinstance(result, str):
            break
        result = json.loads(result)
    return result if isinstance(result, dict) else {}
