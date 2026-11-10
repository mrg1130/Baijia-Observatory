import html
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs, urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests

from baidu_apis import BaiduApis
from utils.baidu_utils import get_common_headers, get_home_headers, get_detail_headers, trans_cookies

CN = timezone(timedelta(hours=8))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def user_id(url):
    p = urlparse(url.strip())
    if p.scheme != 'https' or p.hostname != 'author.baidu.com' or p.port not in (None, 443):
        raise ValueError('请输入 https://author.baidu.com/home/数字ID 格式的用户主页')
    m = re.fullmatch(r'/home/(\d+)/?', p.path)
    if not m:
        raise ValueError('无法识别用户主页地址')
    return m.group(1)


def number(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        text = str(value).replace(',', '').strip()
        # Rounded display values are not exact counts; keep them unavailable.
        return max(0, int(text)) if re.fullmatch(r'-?\d+', text) else None
    except (ValueError, TypeError):
        return None


def first(mapping, keys, default=None):
    return next((mapping[k] for k in keys if mapping.get(k) not in (None, '')), default)


def published(value):
    if not value:
        return None
    try:
        n = float(value)
        return datetime.fromtimestamp(n / 1000 if n > 1e12 else n, CN).isoformat(timespec='seconds')
    except (TypeError, ValueError, OSError):
        try:
            d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return (d if d.tzinfo else d.replace(tzinfo=CN)).astimezone(CN).isoformat(timespec='seconds')
        except ValueError:
            return None


def normalize_post(item, author):
    # Baidu has used both flat feed records and nested dynamic_content records.
    inner = first(item, ['itemData', 'dynamic_content', 'content', 'feed'], {})
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except (ValueError, TypeError):
            inner = {}
    record = {**item, **inner} if isinstance(inner, dict) else item.copy()
    identifier = first(record, ['feed_id', 'dynamic_id', 'id', 'nid', 'thread_id'])
    if identifier is None:
        raise ValueError('作品缺少 ID，不能可靠保存')
    title = html.unescape(str(first(record, ['title', 'dynamic_title', 'abstract', 'description', 'text'], '未命名作品')))
    title = BeautifulSoup(title, 'html.parser').get_text(' ', strip=True)[:600]
    date = first(record, ['publish_at', 'publish_time', 'pub_time', 'pubtime', 'dynamic_ctime', 'created_at', 'ctime', 'create_time', 'time'])
    url = first(record, ['url', 'link', 'content_url', 'source_url'], '')
    if not str(url).startswith('https://'):
        url = f'https://baijiahao.baidu.com/s?id={identifier}' if str(identifier).isdigit() else ''
    content_type = str(first(record, ['itemType', 'type', 'content_type', 'meta_type'], '')).lower()
    return {'id': str(identifier), 'author_id': author, 'title': title, 'url': str(url),
            'kind': '视频' if 'video' in content_type or content_type == '视频' else '图文',
            'published': published(date), 'raw': json.dumps(item, ensure_ascii=False)}


class Provider(BaiduApis):
    """Reuse the original API contract, with timeouts and explicit upstream failures."""
    def __init__(self):
        super().__init__()
        self._redirect_cache = {}

    def get(self, url, cookie='', params=None, headers=None):
        response = requests.get(url, params=params, headers=headers or get_common_headers(),
                                cookies=trans_cookies(cookie), impersonate='chrome101', timeout=25)
        response.raise_for_status()
        if any(t in response.text[:20000] for t in ('百度安全验证', '访问过于频繁')):
            raise ValueError('百度要求安全验证，请在官方登录窗口完成验证后重试')
        return response

    def profile(self, url, cookie):
        uid = user_id(url)
        text = self.get(f'https://author.baidu.com/home/{uid}', cookie).text
        m = re.search(r'window\.runtime\s*=\s*(.*?),\s*window\.runtime\.pageType', text, re.S)
        if not m:
            raise ValueError('未获取到用户资料；请检查登录态或在官方窗口完成验证')
        data = json.loads(m.group(1))
        u = data.get('user', {})
        version = data.get('staticMap', {}).get('version')
        if not u.get('nickname') or not version or not u.get('uk'):
            raise ValueError('百度返回了受限资料。请重新登录并完成官方安全验证，再同步该用户')
        return {'id': uid, 'name': u['nickname'], 'url': f'https://author.baidu.com/home/{uid}',
                'fans': number(u.get('fans_num')), 'likes': number(u.get('likes_num')),
                'total': number(u.get('content_num')), 'uk': u['uk'], 'version': version}

    def jsonp(self, cookie, params, detail=False):
        text = self.get('https://mbd.baidu.com/webpage', cookie, params,
                        get_detail_headers() if detail else get_home_headers()).text.strip()
        try:
            value = json.loads(text[text.index('(') + 1:text.rindex(')')]) if not text.startswith('{') else json.loads(text)
        except (ValueError, json.JSONDecodeError):
            raise ValueError('百度响应格式已变化或登录态失效，请重新登录后重试') from None
        if not isinstance(value, dict) or not isinstance(value.get('data'), dict):
            raise ValueError('百度未返回数据；可能需要重新登录或完成验证')
        return value['data']

    def page(self, profile, cookie, cursor=None):
        cookies = trans_cookies(cookie)
        if not cookies.get('Hmery-Time'):
            raise ValueError('登录态缺少 Hmery-Time，请在官方登录窗口访问用户主页后重新连接')
        params = {'tab': 'main', 'num': '10', 'uk': profile['uk'], 'source': 'pc', 'type': 'newhome',
                  'action': 'dynamic', 'format': 'jsonp', 'otherext': f"h5_{profile['version']}",
                  'Tenger-Mhor': cookies['Hmery-Time'], 'callback': '__jsonp01732944778793'}
        if cursor:
            params.update(top_dynamic_id=cursor[0], ctime=cursor[1])
        return self.jsonp(cookie, params)

    def detail(self, item, profile, cookie):
        cookies = trans_cookies(cookie)
        params = {'type': 'homepage', 'action': 'interact', 'format': 'jsonp', 'Tenger-Mhor': cookies['Hmery-Time'],
                  'params': json.dumps([item]), 'uk': profile['uk'], 'callback': '__jsonp31732960326835'}
        data = self.jsonp(cookie, params, True)
        users = data.get('user_list', {})
        if not isinstance(users, dict) or not users:
            raise ValueError('作品互动数据不可用')
        # A one-item request must have one result, otherwise avoid attaching the wrong metrics.
        if len(users) != 1:
            raise ValueError('互动响应无法唯一匹配作品')
        data = next(iter(users.values()))
        return {key: number(data.get(remote)) for key, remote in {
            'views': 'read_num', 'likes': 'praise_num', 'comments': 'comment_num', 'shares': 'forward_num',
            'favorites': 'collect', 'live_views': 'live_back_num', 'unread': 'unread'}.items()}

    def search(self, keyword, mode):
        site = 'author.baidu.com/home/' if mode == 'users' else 'baijiahao.baidu.com'
        query = f'site:{site} {keyword}'
        external = 'https://www.baidu.com/s?' + urlencode({'wd': query})
        text = self.get(external).text
        return self.parse_search(text, mode), external

    def resolve_search_url(self, url):
        """Resolve Baidu's indexed redirect without forwarding account cookies."""
        original = url
        if original in self._redirect_cache:
            return self._redirect_cache[original]
        url = url.replace('http://', 'https://', 1)
        for _ in range(3):
            p = urlparse(url)
            if p.hostname in ('author.baidu.com', 'baijiahao.baidu.com') and p.scheme == 'https':
                if len(self._redirect_cache) >= 256:
                    self._redirect_cache.pop(next(iter(self._redirect_cache)))
                self._redirect_cache[original] = url
                return url
            if p.hostname != 'www.baidu.com' or p.path != '/link' or p.port not in (None,443):
                return ''
            try:
                response = requests.get(url, headers=get_common_headers(), impersonate='chrome101',
                                        allow_redirects=False, timeout=10)
                location = response.headers.get('location', '')
                if not location:
                    return ''
                url = location.replace('http://', 'https://', 1)
            except Exception:
                return ''
        return ''

    def parse_search(self, text, mode, redirects=True):
        soup = BeautifulSoup(text, 'html.parser')
        results, seen = [], set()
        if mode == 'users':
            for anchor in soup.select('a[href]'):
                url = anchor.get('href', '').replace('http://', 'https://', 1)
                try:
                    uid = user_id(url)
                except ValueError:
                    continue
                name = anchor.get_text(' ', strip=True) or anchor.get('title', '')
                if not name or name in ('关注', '+关注', '加关注') or uid in seen:
                    continue
                results.append({'id': uid, 'name': name, 'url': f'https://author.baidu.com/home/{uid}', 'indexed': True})
                seen.add(uid)
        for block in soup.select('.result, .c-container, [tpl]'):
            a = block.select_one('h3 a, a:has(h3), .cos-title a')
            profile_card = block.select_one('a[class*="user-profile-bar"]') if mode == 'users' else None
            if profile_card:
                a = profile_card
            if not a:
                continue
            url = (a.get('href', '') if profile_card else block.get('mu')) or block.get('data-landurl') or a.get('data-landurl') or a.get('href', '')
            # Prefer the original indexed URL carried in result metadata.
            log = block.get('data-log', '')
            if urlparse(url).hostname == 'www.baidu.com':
                try:
                    url = json.loads(log).get('mu', url)
                except ValueError:
                    pass
            if redirects and urlparse(url).hostname == 'www.baidu.com' and urlparse(url).path == '/link':
                if mode == 'users' and not profile_card and '百家号' not in a.get_text():
                    continue
                url = self.resolve_search_url(url)
            parsed = urlparse(url)
            if parsed.hostname not in ('author.baidu.com', 'baijiahao.baidu.com'):
                continue
            if mode == 'users':
                try:
                    uid = user_id(url.replace('http://', 'https://', 1))
                except ValueError:
                    continue
            else:
                uid = parse_qs(parsed.query).get('id', [''])[0]
                if not uid:
                    continue
            if uid not in seen:
                heading = block.select_one('h3')
                label = heading.get_text(' ',strip=True) if profile_card and heading else a.get_text(' ',strip=True)
                if profile_card:
                    label = re.sub(r'\s*[-－–]\s*百家号.*$', '', label).strip()
                results.append({'id': uid, 'name' if mode == 'users' else 'title': label,
                                'url': url.replace('http://', 'https://', 1), 'indexed': True})
                seen.add(uid)
            if len(results) >= 10:
                break
        return results[:10]
