import base64
import ctypes
import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if getattr(sys, 'frozen', False):
    DEFAULT_DATA = (Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'BaijiaObservatory'
                    if os.name == 'nt' else Path.home() / 'Library/Application Support/BaijiaObservatory')
else:
    DEFAULT_DATA = ROOT / '.local'
DATA = Path(os.environ.get('BAIJIA_DATA_DIR', DEFAULT_DATA))


@contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / 'studio.sqlite3', timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, password TEXT NOT NULL, credential TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS authors(owner TEXT, source TEXT, id TEXT, name TEXT, url TEXT, fans INTEGER, likes INTEGER, total INTEGER, synced TEXT, complete INTEGER DEFAULT 0, PRIMARY KEY(owner,source,id));
        CREATE TABLE IF NOT EXISTS posts(owner TEXT, source TEXT, id TEXT, author_id TEXT, title TEXT, url TEXT, kind TEXT, published TEXT, views REAL, likes REAL, comments REAL, shares REAL, favorites REAL, live_views REAL, unread REAL, collected TEXT, raw TEXT, PRIMARY KEY(owner,source,id));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT, author_id TEXT, status TEXT, message TEXT, pages INTEGER DEFAULT 0, processed INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, created TEXT);
        CREATE TABLE IF NOT EXISTS calculators(id TEXT PRIMARY KEY, owner TEXT, name TEXT, expression TEXT, aggregation TEXT);
        CREATE INDEX IF NOT EXISTS posts_author ON posts(owner,source,author_id);
        CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        _workspace_id(c)
        c.execute("UPDATE jobs SET status='interrupted',message='软件重启，采集已中断；请重新同步' WHERE status IN ('running','queued')")


def _workspace_id(c):
    saved = c.execute("SELECT value FROM preferences WHERE key='workspace_owner'").fetchone()
    if saved and c.execute('SELECT 1 FROM accounts WHERE id=?', (saved[0],)).fetchone():
        return saved[0]
    # Retain the last-used workspace and its data during migration from account mode.
    prior = c.execute('''SELECT a.id FROM accounts a LEFT JOIN sessions s ON s.owner=a.id
                         GROUP BY a.id ORDER BY COALESCE(MAX(s.expires),0) DESC,
                         (a.credential IS NOT NULL) DESC,
                         (SELECT count(*) FROM posts p WHERE p.owner=a.id) DESC,a.rowid ASC LIMIT 1''').fetchone()
    uid = prior[0] if prior else secrets.token_hex(16)
    if not prior:
        c.execute('INSERT INTO accounts(id,name,password) VALUES (?,?,?)', (uid, '本地工作台', ''))
    c.execute("INSERT OR REPLACE INTO preferences VALUES ('workspace_owner',?)", (uid,))
    return uid


def workspace_id():
    with db() as c:
        return _workspace_id(c)


class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _protect(value, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('此版本使用 Windows 系统加密保存登录态，请在 Windows 运行。')
    data = base64.b64decode(value) if decrypt else value.encode()
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    # CRYPTPROTECT_UI_FORBIDDEN; Windows binds this blob to the current Windows user.
    ok = fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst))
    if not ok:
        raise ctypes.WinError()
    try:
        out = ctypes.string_at(dst.data, dst.size)
        return out.decode() if decrypt else base64.b64encode(out).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)


def set_cookie(owner, cookie):
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
        keyring = Keyring()
        if cookie:
            keyring.set_password('com.baijia.observatory', owner, cookie)
        elif keyring.get_password('com.baijia.observatory', owner):
            keyring.delete_password('com.baijia.observatory', owner)
        encrypted = 'macos-keychain' if cookie else None
    else:
        encrypted = _protect(cookie) if cookie else None
    with db() as c:
        c.execute('UPDATE accounts SET credential=? WHERE id=?', (encrypted, owner))


def get_cookie(owner):
    with db() as c:
        row = c.execute('SELECT credential FROM accounts WHERE id=?', (owner,)).fetchone()
    if not row or not row['credential']:
        return ''
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
        return Keyring().get_password('com.baijia.observatory', owner) or ''
    return _protect(row['credential'], True)
