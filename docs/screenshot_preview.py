"""Render real workspace screens with identifiers blurred for documentation."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn
from fastapi.responses import FileResponse, HTMLResponse
from studio.server import app, WEB


@app.get('/_screenshots', include_in_schema=False)
def preview():
    html = (WEB / 'index.html').read_text(encoding='utf-8')
    html = html.replace('<html lang="zh-CN">', '<html lang="zh-CN" class="screenshot-privacy">')
    html = html.replace('</head>', '<link rel="stylesheet" href="/_screenshots/privacy.css"></head>')
    return HTMLResponse(html)


@app.get('/_screenshots/privacy.css', include_in_schema=False)
def privacy_styles():
    return FileResponse(Path(__file__).with_name('screenshot-privacy.css'), media_type='text/css')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
