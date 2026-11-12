"""Baidu's official pages in the desktop application's own native browser window."""
import time
from urllib.parse import urlencode, urlparse, parse_qs

import webview

from .storage import DATA, set_cookie
from .desktop_js import read_snapshot


class NativeBaidu:
    def __init__(self):
        self.window = None
        self.navigated = False
        self.reset_owner = None
        self.reset_error = ''

    def _reset_marker(self, owner):
        return DATA / f'login-reset-{owner}.pending'

    def _request_reset(self, owner):
        DATA.mkdir(parents=True, exist_ok=True)
        self._reset_marker(owner).touch()
        self.reset_owner = owner
        self.reset_error = ''

    def _clear_pending_cookies(self):
        owner = self.reset_owner
        if not owner or self.window is None:
            return False
        try:
            self.window.clear_cookies()
            self._reset_marker(owner).unlink(missing_ok=True)
            self.reset_owner = None
            self.reset_error = ''
            self.navigated = False
            self.window.load_url('https://www.baidu.com/')
            return True
        except Exception:
            # Keep the marker so reopening the login window retries the reset.
            self.reset_error = '旧登录态暂未清理，请关闭百度登录窗口后重新打开'
            return False

    def _loaded(self):
        if self.reset_owner:
            self._clear_pending_cookies()

    def _closed(self):
        self.window = None
        self.navigated = False

    def start(self, owner, replace=False):
        if replace or self._reset_marker(owner).exists():
            set_cookie(owner, '')
            self._request_reset(owner)
        created = self.window is None
        if self.window is None:
            self.window = webview.create_window('百度账号连接', 'https://www.baidu.com/', width=1120, height=800,
                                                min_size=(850,650), text_select=True)
            self.window.events.closed += self._closed
            self.window.events.loaded += self._loaded
        else:
            self.window.show()
            self.window.restore()
        if self.reset_owner and not created:
            self._clear_pending_cookies()
        if self.reset_owner:
            return {'status':'waiting','message':'正在清理旧登录态，随后请在百度官方页面重新登录'}
        return {'status':'waiting','message':'请在百度官方页面点击「登录」，选择页面提供的方式完成登录'}

    def status(self, owner):
        if self.window is None:
            return {'status':'closed','message':'点击打开百度登录窗口后完成登录'}
        if self.reset_owner:
            return {'status':'waiting','message':self.reset_error or '正在清理旧登录态…'}
        try:
            url = self.window.get_current_url() or ''
            host = urlparse(url).hostname or ''
            if not (host == 'baidu.com' or host.endswith('.baidu.com')):
                return {'status':'waiting','message':'正在载入百度官方页面…'}
            values = {}
            for cookie in self.window.get_cookies():
                for name,morsel in cookie.items():
                    domain = morsel['domain'].lstrip('.')
                    if not domain or domain == 'baidu.com' or domain.endswith('.baidu.com'):
                        values[name] = morsel.value
            if not values.get('BDUSS'):
                return {'status':'waiting','message':'请在官方页面完成登录…'}
            if not values.get('Hmery-Time'):
                if not self.navigated and host != 'wappass.baidu.com':
                    self.window.load_url('https://author.baidu.com/home/1595713367276134')
                    self.navigated = True
                return {'status':'waiting','message':'正在连接百家号；页面显示验证时，请完成验证'}
            set_cookie(owner,'; '.join(f'{k}={v}' for k,v in values.items()))
            return {'status':'connected','message':'百度账号已连接'}
        except Exception:
            return {'status':'waiting','message':'正在读取百度登录状态…'}

    def close(self, owner):
        if self.window is not None:
            window,self.window=self.window,None
            window.destroy()

    def disconnect(self, owner):
        set_cookie(owner,'')
        self._request_reset(owner)
        if self.window is not None:
            self._clear_pending_cookies()
        self.close(owner)

    def search_page(self, owner, keyword, mode):
        query = f'site:baijiahao.baidu.com {keyword}'
        url = 'https://www.baidu.com/s?' + urlencode({'wd':query})
        self.start(owner)
        if parse_qs(urlparse(self.window.get_current_url() or '').query).get('wd') != [query]:
            self.window.load_url(url)
        snapshot={}
        for _ in range(70):
            snapshot=read_snapshot(self.window,'({title:document.title,html:document.documentElement.outerHTML,ready:document.readyState,url:location.href,results:document.querySelectorAll("#content_left .c-container,#content_left .result,.cosc-title").length})')
            host=urlparse(snapshot.get('url','')).hostname
            challenge='安全验证' in snapshot.get('title','') or host=='wappass.baidu.com'
            matches=parse_qs(urlparse(snapshot.get('url','')).query).get('wd')==[query]
            if challenge or matches and snapshot.get('ready')=='complete' and snapshot.get('results',0)>0:
                break
            time.sleep(.2)
        return snapshot.get('html',''),url,'安全验证' in snapshot.get('title','') or urlparse(snapshot.get('url','')).hostname=='wappass.baidu.com'
