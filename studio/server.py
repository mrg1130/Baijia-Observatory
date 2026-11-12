import argparse
import csv
import io
import json
import os
import random
import secrets
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urlencode

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .storage import db, initialize, workspace_id, get_cookie, set_cookie
from .provider import Provider, user_id, normalize_post, now
from .metrics import METRICS, enrich, summarize, parse_formula, calculate
from . import browser_login

WEB = Path(__file__).parent / 'web'
provider = Provider()
job_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title='百家观测', lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])


@app.middleware('http')
async def local_only(request, call_next):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        return JSONResponse({'detail': '请求来源不受信任'}, status_code=403)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.url.path.startswith('/api/'):
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': '请使用 JSON 请求'}, status_code=415)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


def owner():
    return {'id': workspace_id()}


@app.get('/api/workspace')
def workspace(user=Depends(owner)):
    with db() as c:
        connected = bool(c.execute('SELECT credential FROM accounts WHERE id=?', (user['id'],)).fetchone()[0])
    return {**user, 'connected': connected}


@app.get('/api/manual')
def manual():
    target = Path(__file__).parent / 'manual.pdf'
    if not target.exists():
        raise HTTPException(404, '使用说明正在准备中')
    return FileResponse(target, media_type='application/pdf', filename='百家观测使用说明.pdf')


@app.post('/api/manual/open')
def open_manual():
    opener = getattr(app.state, 'open_manual', None)
    return {'desktop': True, **opener()} if opener else {'desktop': False}


class CookieBody(BaseModel):
    cookie: str = Field(min_length=1, max_length=50000)


@app.post('/api/platform/cookie')
def cookie(body: CookieBody, user=Depends(owner)):
    from utils.baidu_utils import trans_cookies
    values = trans_cookies(body.cookie)
    if not values.get('Hmery-Time') or not values.get('BDUSS'):
        raise ValueError('Cookie 需要包含 BDUSS 和 Hmery-Time，请登录百度后从用户主页请求中复制')
    if '\n' in body.cookie or '\r' in body.cookie:
        raise ValueError('Cookie 必须为一行请求头字段值')
    set_cookie(user['id'], body.cookie.strip())
    return {'ok': True, 'message': '已加密保存，实际有效性将在同步时验证'}


@app.post('/api/platform/login')
def platform_login(user=Depends(owner)):
    # Pressing “switch or sign in again” must replace both the saved credential
    # and the browser profile's cookies. Otherwise a stale session is captured
    # again immediately after an application restart.
    return browser_login.start(user['id'], replace=bool(get_cookie(user['id'])))


@app.get('/api/platform/login/status')
def platform_status(user=Depends(owner)):
    return browser_login.status(user['id'])


@app.delete('/api/platform')
def disconnect(user=Depends(owner)):
    with db() as c:
        running = c.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('running','queued')", (user['id'],)).fetchone()
    if running:
        raise ValueError('请先停止当前采集任务，再断开百度连接')
    browser_login.disconnect(user['id'])
    return {'ok': True}


def seed_demo(uid):
    rng = random.Random(621)
    date = datetime.now(timezone(timedelta(hours=8))).replace(hour=10, minute=0, second=0, microsecond=0)
    authors = [('demo-01', '科技新知局', 286400, 1926800), ('demo-02', '城市漫游指南', 97600, 582400), ('demo-03', '生活实验室', 153200, 913600)]
    titles = ['这一次，AI 真的走进了我们的日常生活', '把复杂的事讲清楚：值得收藏的实用指南', '一个被忽略的细节，正在悄悄改变体验', '亲测一周之后，我整理了这份真实记录', '从零开始了解：十个你关心的问题', '为什么越来越多人开始关注这个趋势', '周末观察：让生活更有意思的小发现', '深度体验：那些参数之外的真实感受', '别急着做决定，先看完这组对比', '从想法到实践，一次完整的探索记录', '年度回顾：我们见证的那些微小进步', '值得反复看的三个案例与五条建议']
    with db() as c:
        if c.execute("SELECT 1 FROM authors WHERE owner=? AND source='demo'", (uid,)).fetchone():
            return
        for index, (aid, name, fans, likes) in enumerate(authors):
            c.execute('INSERT INTO authors VALUES (?,?,?,?,?,?,?,?,?,?)', (uid, 'demo', aid, name, '', fans, likes, 48, now(), 1))
            for i in range(48):
                views = rng.randint(700, 21000) + (88000 if i % 17 == 0 else 0)
                vals = [views, int(views * rng.uniform(.015, .047)), rng.randint(3, 240), rng.randint(5, 130), rng.randint(2, 310), None, None]
                post = [uid, 'demo', f'{aid}-{i}', aid, titles[i % len(titles)] + (' · 实测' if i >= 12 else ''), '', '视频' if i % 4 == 0 else '图文', (date - timedelta(days=i * 2, hours=rng.randint(0, 12))).isoformat(), *vals, now(), '{}']
                c.execute('INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', post)


@app.post('/api/demo')
def demo(user=Depends(owner)):
    seed_demo(user['id'])
    return {'ok': True}


@app.get('/api/authors')
def authors(source: Literal['live', 'demo'] = 'live', user=Depends(owner)):
    with db() as c:
        rows = c.execute('SELECT a.*,(SELECT count(*) FROM posts p WHERE p.owner=a.owner AND p.source=a.source AND p.author_id=a.id) AS cached FROM authors a WHERE owner=? AND source=? ORDER BY name', (user['id'], source)).fetchall()
    return [dict(r) for r in rows]


class AuthorBody(BaseModel):
    url: str = Field(min_length=1, max_length=500)


@app.post('/api/authors')
def add_author(body: AuthorBody, user=Depends(owner)):
    aid = user_id(body.url)
    with db() as c:
        existing = c.execute("SELECT * FROM authors WHERE owner=? AND source='live' AND id=?", (user['id'], aid)).fetchone()
    if existing:
        return {**dict(existing), 'existing': True}
    cookie = get_cookie(user['id'])
    if not cookie:
        raise ValueError('请先连接百度账号，再添加监控主页')
    try:
        profile = provider.profile(f'https://author.baidu.com/home/{aid}', cookie)
    except ValueError:
        raise
    except Exception:
        raise ValueError('暂时无法读取该主页，请检查网络或登录态后重试') from None
    with db() as c:
        c.execute('''INSERT INTO authors VALUES (?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(owner,source,id) DO UPDATE SET name=excluded.name,url=excluded.url,
                     fans=excluded.fans,likes=excluded.likes,total=excluded.total''',
                  (user['id'], 'live', aid, profile['name'], profile['url'], profile['fans'], profile['likes'], profile['total'], None, 0))
        author = c.execute("SELECT * FROM authors WHERE owner=? AND source='live' AND id=?", (user['id'], aid)).fetchone()
    return {**dict(author), 'existing': False}


@app.get('/api/search')
def search(q: str = '', mode: Literal['content'] = 'content', source: Literal['live', 'demo'] = 'live', online: bool = False, user=Depends(owner)):
    q = q.strip()[:160]
    with db() as c:
        cached = [dict(r) for r in c.execute('SELECT p.*, a.name AS author_name FROM posts p LEFT JOIN authors a ON a.owner=p.owner AND a.source=p.source AND a.id=p.author_id WHERE p.owner=? AND p.source=? ORDER BY published DESC', (user['id'], source)) if q.casefold() in r['title'].casefold()][:100]
    results, warning, external = [], '', ''
    if q.startswith('https://author.baidu.com/home/'):
        warning = '这是用户主页链接，请使用「添加监控账号」填写。'
    elif online and source == 'live' and q:
        try:
            if get_cookie(user['id']):
                text, external, verification = browser_login.search_page(user['id'], q, mode)
                if verification:
                    warning = '百度要求安全验证。请在专用百度窗口中自行完成验证，再点击本软件的搜索按钮。'
                else:
                    results = provider.parse_search(text, mode)
            else:
                results, external = provider.search(q, mode)
            if not results and not warning:
                warning = '百度未返回可解析的内容结果，请调整关键词或稍后重试。'
        except ValueError as exc:
            warning = str(exc)
        except Exception:
            warning = '暂时无法读取百度公开内容搜索结果，请稍后重试。'
            external = 'https://www.baidu.com/s?' + urlencode({'wd': 'site:baijiahao.baidu.com ' + q})
    return {'cached': cached, 'online': results, 'warning': warning, 'external': external}


def job_update(jid, **values):
    with db() as c:
        c.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?', (*values.values(), jid))


def cancelled(jid):
    with db() as c:
        return c.execute('SELECT status FROM jobs WHERE id=?', (jid,)).fetchone()[0] == 'cancelled'


def sync_author(jid, uid, url, max_posts=0):
    pages = processed = failed = 0
    aid = user_id(url)
    try:
        if cancelled(jid):
            return
        job_update(jid, status='running', message='正在读取用户资料…')
        cookie = get_cookie(uid)
        profile = provider.profile(url, cookie)
        with db() as c:
            c.execute('INSERT INTO authors VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,source,id) DO UPDATE SET name=excluded.name,fans=excluded.fans,likes=excluded.likes,total=excluded.total,complete=0',
                      (uid, 'live', aid, profile['name'], profile['url'], profile['fans'], profile['likes'], profile['total'], None, 0))
        cursor, seen_cursors, seen_posts = None, set(), set()
        limited = False
        while True:
            if cancelled(jid):
                return
            data = provider.page(profile, cookie, cursor)
            items = data.get('list')
            if not isinstance(items, list):
                raise ValueError('作品列表结构无法识别，已保留当前采集结果')
            has_more = data.get('hasMore', data.get('has_more'))
            if has_more is None:
                raise ValueError('响应缺少分页完成标识，无法确认已获取全部作品')
            if not items and str(has_more) not in ('0', 'False', 'false'):
                raise ValueError('百度返回空列表但提示仍有下一页，请稍后重新同步')
            pages += 1
            for item in items:
                if max_posts and processed >= max_posts:
                    limited = True
                    break
                if cancelled(jid):
                    return
                try:
                    post = normalize_post(item, aid)
                except (ValueError, TypeError):
                    failed += 1
                    continue
                if post['id'] in seen_posts:
                    continue
                seen_posts.add(post['id'])
                try:
                    metrics = provider.detail(item, profile, cookie)
                    if any(metrics[k] is None for k in ('views', 'likes', 'comments', 'shares', 'favorites')):
                        failed += 1
                except Exception:
                    metrics = {k: None for k in METRICS}
                    failed += 1
                with db() as c:
                    c.execute('INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (uid, 'live', post['id'], aid, post['title'], post['url'], post['kind'], post['published'],
                               *(metrics.get(k) for k in METRICS), now(), post['raw']))
                processed += 1
                job_update(jid, pages=pages, processed=processed, failed=failed, message=f'已扫描 {pages} 页 · {processed} 件作品 · {failed} 件数据不完整')
                time.sleep(.35)
            if limited or (max_posts and processed >= max_posts and str(has_more) not in ('0', 'False', 'false')):
                limited = True
                break
            if str(has_more) in ('0', 'False', 'false'):
                break
            query = data.get('query') or {}
            next_cursor = (str(first_dynamic_id(items)), str(query.get('ctime', '')))
            if not all(next_cursor) or next_cursor in seen_cursors:
                raise ValueError('分页游标缺失或重复，已停止以避免遗漏被误报为完整')
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            time.sleep(.8)
        with db() as c:
            c.execute("UPDATE authors SET synced=?,complete=? WHERE owner=? AND source='live' AND id=?", (now(), int(failed == 0 and not limited), uid, aid))
        job_update(jid, status='partial' if failed else 'sampled' if limited else 'completed', pages=pages, processed=processed, failed=failed,
                   message=(f'已完成指定范围：{processed} 件作品；历史作品尚未全部扫描' if limited else f'已遍历全部分页，共处理 {processed} 件作品')
                   + (f'；{failed} 件数据不完整，请重新同步' if failed else '，同步完成'))
    except ValueError as exc:
        if not cancelled(jid):
            job_update(jid, status='failed', message=str(exc), pages=pages, processed=processed, failed=failed)
    except Exception:
        if not cancelled(jid):
            job_update(jid, status='failed', message='网络或百度接口异常，已保留采集结果。请检查登录状态后重试', pages=pages, processed=processed, failed=failed)


def first_dynamic_id(items):
    # Upstream README specifies the first dynamic ID of the preceding page.
    return items[0].get('dynamic_id', '') if items else ''


class SyncBody(BaseModel):
    url: str = Field(max_length=500)
    max_posts: int = Field(default=0, ge=0, le=100000)


@app.post('/api/sync')
def sync(body: SyncBody, user=Depends(owner)):
    aid = user_id(body.url)
    if not get_cookie(user['id']):
        raise ValueError('请先连接百度账号')
    with job_lock:
        with db() as c:
            if c.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('running','queued')", (user['id'],)).fetchone():
                raise ValueError('已有任务正在同步，请等待完成或先停止该任务')
            jid = secrets.token_hex(12)
            c.execute('INSERT INTO jobs(id,owner,author_id,status,message,created) VALUES (?,?,?,?,?,?)', (jid, user['id'], aid, 'queued', '等待同步…', now()))
        threading.Thread(target=sync_author, args=(jid, user['id'], f'https://author.baidu.com/home/{aid}', body.max_posts), daemon=True).start()
    return {'id': jid}


@app.get('/api/jobs')
def jobs(user=Depends(owner)):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 20', (user['id'],))]


@app.post('/api/jobs/{jid}/cancel')
def cancel(jid: str, user=Depends(owner)):
    with db() as c:
        c.execute("UPDATE jobs SET status='cancelled',message='用户已停止，已采集结果保留' WHERE id=? AND owner=? AND status IN ('running','queued')", (jid, user['id']))
    return {'ok': True}


class Query(BaseModel):
    source: Literal['live', 'demo'] = 'live'
    author: str = ''
    start: str = ''
    end: str = ''
    keyword: str = Field(default='', max_length=200)
    kind: str = ''
    selected: list[str] | None = Field(default=None, max_length=100000)
    sort: str = 'published'
    direction: Literal['asc', 'desc'] = 'desc'


def fetch_posts(query, uid):
    for d in (query.start, query.end):
        if d:
            try:
                datetime.strptime(d, '%Y-%m-%d')
            except ValueError:
                raise ValueError('日期格式应为 YYYY-MM-DD') from None
    if query.start and query.end and query.start > query.end:
        raise ValueError('开始日期不能晚于结束日期')
    with db() as c:
        rows = [dict(r) for r in c.execute('SELECT p.*, a.name AS author_name FROM posts p JOIN authors a ON a.owner=p.owner AND a.source=p.source AND a.id=p.author_id WHERE p.owner=? AND p.source=?', (uid, query.source))]
        calculators = [dict(r) for r in c.execute('SELECT id,name,expression,aggregation FROM calculators WHERE owner=? ORDER BY rowid', (uid,))]
    rows = [enrich(r) for r in rows if (not query.author or r['author_id'] == query.author)
            and (not query.keyword or query.keyword.casefold() in r['title'].casefold())
            and (not query.kind or r['kind'] == query.kind)]
    undated = sum(not r['published'] for r in rows)
    rows = [r for r in rows if (not query.start or r['published'] and r['published'][:10] >= query.start)
            and (not query.end or r['published'] and r['published'][:10] <= query.end)]
    if query.selected is not None:
        selected = set(query.selected)
        rows = [r for r in rows if r['id'] in selected]
    for r in rows:
        for calc in calculators:
            r['calc_' + calc['id']] = calculate(calc['expression'], r)
        for k in ('raw', 'owner'):
            r.pop(k, None)
    key = query.sort
    allowed = set(METRICS + ['title', 'published', 'interactions', 'engagement']) | {'calc_' + c['id'] for c in calculators}
    if key not in allowed:
        raise ValueError('不支持该排序字段')
    present = sorted([r for r in rows if r.get(key) is not None], key=lambda r: r[key], reverse=query.direction == 'desc')
    rows = present + [r for r in rows if r.get(key) is None]
    trend = {}
    for r in rows:
        if r['published']:
            day = r['published'][:10]
            point = trend.setdefault(day, {'date': day, 'posts': 0, 'views': None, 'interactions': None})
            point['posts'] += 1
            for key in ('views', 'interactions'):
                if r[key] is not None:
                    point[key] = (point[key] or 0) + r[key]
    return {'posts': rows, 'summary': summarize(rows, calculators), 'trend': sorted(trend.values(), key=lambda p: p['date']), 'undated': undated}


@app.post('/api/posts/query')
def posts(query: Query, user=Depends(owner)):
    return fetch_posts(query, user['id'])


@app.post('/api/export')
def export(query: Query, user=Depends(owner)):
    result = fetch_posts(query, user['id'])
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    keys = ['author_name', 'title', 'kind', 'published', *METRICS, 'interactions', 'engagement', 'collected', 'url']
    headers = ['作者', '作品标题', '类型', '发布时间(北京时间)', '阅读/播放', '点赞', '评论', '转发', '收藏', '直播回放', '未读', '互动合计', '互动率(%)', '采集时间(UTC)', '作品链接']
    with db() as c:
        calcs = c.execute('SELECT id,name FROM calculators WHERE owner=?', (user['id'],)).fetchall()
    keys.extend('calc_' + r['id'] for r in calcs)
    headers.extend(r['name'] + '(逐作品)' for r in calcs)
    writer.writerow(headers)
    for r in result['posts']:
        cells = []
        for k in keys:
            v = r.get(k)
            # Prevent spreadsheet formula interpretation of untrusted titles/names.
            cells.append("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v)
        writer.writerow(cells)
    return Response('\ufeff' + stream.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="baijia-works.csv"'})


class Calculator(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    expression: str = Field(min_length=1, max_length=300)
    aggregation: Literal['totals', 'sum', 'average', 'max', 'min'] = 'totals'


@app.get('/api/calculators')
def calculators(user=Depends(owner)):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT id,name,expression,aggregation FROM calculators WHERE owner=?', (user['id'],))]


@app.post('/api/calculators')
def save_calc(body: Calculator, user=Depends(owner)):
    parse_formula(body.expression)
    cid = secrets.token_hex(6)
    with db() as c:
        count = c.execute('SELECT count(*) FROM calculators WHERE owner=?', (user['id'],)).fetchone()[0]
        if count >= 30:
            raise ValueError('最多可保存 30 个统计器，请删除不再使用的项目')
        c.execute('INSERT INTO calculators VALUES (?,?,?,?,?)', (cid, user['id'], body.name, body.expression, body.aggregation))
    return {'id': cid}


@app.delete('/api/calculators/{cid}')
def delete_calc(cid: str, user=Depends(owner)):
    with db() as c:
        c.execute('DELETE FROM calculators WHERE id=? AND owner=?', (cid, user['id']))
    return {'ok': True}


@app.put('/api/calculators/{cid}')
def update_calc(cid: str, body: Calculator, user=Depends(owner)):
    parse_formula(body.expression)
    with db() as c:
        result = c.execute('UPDATE calculators SET name=?,expression=?,aggregation=? WHERE id=? AND owner=?',
                           (body.name, body.expression, body.aggregation, cid, user['id']))
        if not result.rowcount:
            raise HTTPException(404, '未找到该统计器')
    return {'id': cid}


app.mount('/assets', StaticFiles(directory=WEB), name='assets')


@app.get('/')
def index():
    return FileResponse(WEB / 'index.html')


@app.get('/api/health')
def health():
    return {'application': 'baijia-observatory', 'status': 'ok', 'version': '1.1.0'}


if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    if args.open:
        # Reopening the launcher should bring back the running app.
        import urllib.request
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/health', timeout=1) as r:
                existing = json.load(r)
            if existing.get('application') == 'baijia-observatory':
                webbrowser.open(f'http://127.0.0.1:{args.port}')
                raise SystemExit(0)
        except (OSError, ValueError):
            pass
    if args.open:
        threading.Timer(1.3, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
