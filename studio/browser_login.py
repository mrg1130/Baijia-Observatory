import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlencode, urlparse, parse_qs
from pathlib import Path

import websocket

from .storage import DATA, set_cookie

_sessions = {}
_lock = threading.Lock()
native_client = None


def recover(owner):
    if owner in _sessions:
        return _sessions[owner]
    try:
        saved = json.loads((DATA / 'browser' / owner / 'login-port.json').read_text(encoding='utf-8'))
        age = max(0, time.time() - saved['started'])
        session = {'port': int(saved['port']), 'started': time.monotonic() - age, 'navigated': False}
        _sessions[owner] = session
        return session
    except (OSError, ValueError, KeyError, TypeError):
        return None


def find_browser():
    candidates = [Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
                  Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Microsoft/Edge/Application/msedge.exe',
                  Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
                  Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe']
    candidates += [Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                   Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')]
    for p in candidates:
        if p.is_file():
            return str(p)
    return shutil.which('msedge') or shutil.which('chrome')


def start(owner, replace=False):
    if native_client is not None:
        return native_client.start(owner, replace=replace)
    if replace:
        disconnect(owner)
    with _lock:
        old = recover(owner)
        if old:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{old['port']}/json/version", timeout=1):
                    return {'status': 'waiting', 'message': '官方登录窗口已打开，请切换到该窗口点击「登录」完成验证'}
            except OSError:
                pass
        browser = find_browser()
        if not browser:
            raise ValueError('没有找到 Edge 或 Chrome，请安装其中一个浏览器，或使用 Cookie 连接')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        profile = DATA / 'browser' / owner
        profile.mkdir(parents=True, exist_ok=True)
        # Launch the public homepage: legacy Passport deep links may return 404.
        # Its own Login control exposes the currently supported official methods.
        url = 'https://www.baidu.com/'
        process = subprocess.Popen([browser, '--new-window', '--no-first-run', '--remote-debugging-address=127.0.0.1',
                                    f'--remote-debugging-port={port}', f'--user-data-dir={profile}', url],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _sessions[owner] = {'process': process, 'port': port, 'started': time.monotonic(), 'navigated': False}
        (profile / 'login-port.json').write_text(json.dumps({'port': port, 'started': time.time()}), encoding='utf-8')
    return {'status': 'waiting', 'message': '请在百度官方窗口点击右上角「登录」，选择页面提供的方式完成登录'}


def command(ws_url, method, params=None):
    ws = websocket.create_connection(ws_url, timeout=4, suppress_origin=True)
    try:
        ws.send(json.dumps({'id': 1, 'method': method, 'params': params or {}}))
        while True:
            reply = json.loads(ws.recv())
            if reply.get('id') == 1:
                if reply.get('error'):
                    raise ValueError('无法读取官方窗口登录状态')
                return reply.get('result', {})
    finally:
        ws.close()


def status(owner):
    if native_client is not None:
        return native_client.status(owner)
    session = recover(owner)
    if not session:
        return {'status': 'idle', 'message': '尚未打开登录窗口'}
    if time.monotonic() - session['started'] > 900:
        return {'status': 'expired', 'message': '登录等待已超时，请关闭该窗口后重新打开'}
    ready = False
    try:
        base = f"http://127.0.0.1:{session['port']}"
        with urllib.request.urlopen(base + '/json/version', timeout=3) as r:
            version = json.load(r)
        ready = True
        cookies = command(version['webSocketDebuggerUrl'], 'Storage.getCookies').get('cookies', [])
        cookies = [c for c in cookies if c['domain'].lstrip('.') in ('baidu.com', 'author.baidu.com', 'passport.baidu.com', 'mbd.baidu.com')]
        # Prefer author.baidu.com scoped entries when duplicate names exist.
        cookies.sort(key=lambda c: c['domain'] == 'author.baidu.com')
        values = {c['name']: c['value'] for c in cookies}
        if not values.get('BDUSS'):
            return {'status': 'waiting', 'message': '等待百度官方窗口完成登录…'}
        if not values.get('Hmery-Time'):
            if not session['navigated']:
                with urllib.request.urlopen(base + '/json', timeout=3) as r:
                    tabs = json.load(r)
                page = next((t for t in tabs if t.get('type') == 'page'), None)
                if page:
                    command(page['webSocketDebuggerUrl'], 'Page.navigate', {'url': 'https://author.baidu.com/home/1812506351533473'})
                    session['navigated'] = True
            return {'status': 'waiting', 'message': '已识别账号登录，正在等待百家号页面生成 Hmery-Time；如出现验证，请在窗口完成'}
        set_cookie(owner, '; '.join(f'{k}={v}' for k, v in values.items()))
        return {'status': 'connected', 'message': '百度登录态已连接，实际数据访问权限将在同步时检测'}
    except Exception:
        # Edge's launcher process can exit before the actual browser is ready.
        # Its process handle is not proof that the login window has closed.
        waiting = ready or time.monotonic() - session['started'] < 30
        return {'status': 'waiting' if waiting else 'closed',
                'message': '等待官方登录窗口就绪…' if waiting else '登录窗口未连接，可重新打开'}


def close(owner):
    if native_client is not None:
        return native_client.close(owner)
    session = recover(owner)
    _sessions.pop(owner, None)
    try:
        (DATA / 'browser' / owner / 'login-port.json').unlink(missing_ok=True)
    except OSError:
        pass
    if session:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{session['port']}/json/version", timeout=2) as r:
                version = json.load(r)
            command(version['webSocketDebuggerUrl'], 'Browser.close')
        except Exception:
            pass


def disconnect(owner):
    if native_client is not None:
        return native_client.disconnect(owner)
    close(owner)
    set_cookie(owner, '')
    # Dedicated profile contains only this app's Baidu session. Remove it on disconnect.
    target = (DATA / 'browser' / owner).resolve()
    parent = (DATA / 'browser').resolve()
    if target.parent != parent:
        raise ValueError('登录窗口目录无效')
    for _ in range(10):
        try:
            if target.exists():
                shutil.rmtree(target)
            return
        except OSError:
            time.sleep(.25)
    raise ValueError('本软件登录态已清除；请关闭专用百度窗口后再次断开连接以清除窗口缓存')


def search_page(owner, keyword, mode):
    """Run search in this app's dedicated, signed-in browser, never the daily profile."""
    if native_client is not None:
        return native_client.search_page(owner,keyword,mode)
    session = recover(owner)
    if not session:
        start(owner)
        session = recover(owner)
    query = f'{keyword} 百家号' if mode == 'users' else f'site:baijiahao.baidu.com {keyword}'
    url = 'https://www.baidu.com/s?' + urlencode({'wd': query})
    base = f"http://127.0.0.1:{session['port']}"
    version = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(base + '/json/version', timeout=.7) as r:
                version = json.load(r)
            break
        except OSError:
            time.sleep(.3)
    if not version:
        _sessions.pop(owner, None)
        (DATA / 'browser' / owner / 'login-port.json').unlink(missing_ok=True)
        start(owner)
        session = recover(owner)
        base = f"http://127.0.0.1:{session['port']}"
        for _ in range(20):
            try:
                with urllib.request.urlopen(base + '/json/version', timeout=.7) as r:
                    version = json.load(r)
                break
            except OSError:
                time.sleep(.3)
        if not version:
            raise ValueError('专用百度窗口尚未就绪，请稍后重新搜索')
    with urllib.request.urlopen(base + '/json', timeout=3) as r:
        tabs = json.load(r)
    saved = session.get('search')
    tab = next((t for t in tabs if saved and saved['query'] == query and t['id'] == saved['target']), None)
    if not tab:
        tab = next((t for t in tabs if t.get('type') == 'page' and urlparse(t.get('url','')).hostname == 'www.baidu.com'
                    and parse_qs(urlparse(t.get('url','')).query).get('wd') == [query]), None)
    if not tab:
        target = command(version['webSocketDebuggerUrl'], 'Target.createTarget', {'url': url})['targetId']
        session['search'] = {'query': query, 'target': target}
        for _ in range(20):
            with urllib.request.urlopen(base + '/json', timeout=3) as r:
                tabs = json.load(r)
            tab = next((t for t in tabs if t['id'] == target), None)
            if tab:
                break
            time.sleep(.2)
    if not tab:
        raise ValueError('无法打开百度搜索页，请重新打开官方窗口后重试')
    snapshot = {}
    for _ in range(25):
        result = command(tab['webSocketDebuggerUrl'], 'Runtime.evaluate', {
            'expression': '({title:document.title,html:document.documentElement.outerHTML,ready:document.readyState,url:location.href,results:document.querySelectorAll("#content_left .c-container,#content_left .result,.cosc-title").length})',
            'returnByValue': True})
        snapshot = result.get('result', {}).get('value', {})
        challenge = '安全验证' in snapshot.get('title','') or urlparse(snapshot.get('url','')).hostname == 'wappass.baidu.com'
        matches = parse_qs(urlparse(snapshot.get('url','')).query).get('wd') == [query]
        if challenge or (snapshot.get('ready') == 'complete' and matches and
                         (snapshot.get('results',0) > 0 or '没有找到' in snapshot.get('html',''))):
            break
        time.sleep(.25)
    verification = '安全验证' in snapshot.get('title', '') or 'wappass.baidu.com' in snapshot.get('url', '')
    return snapshot.get('html', ''), url, verification
