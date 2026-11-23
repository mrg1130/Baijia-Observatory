"""Baidu's official pages in the desktop application's own native browser window."""
import time
from threading import Lock
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
        self._reset_lock = Lock()
        self._generation = 0

    def _reset_marker(self, owner):
        return DATA / f'login-reset-{owner}.pending'

    def _request_reset(self, owner, *, forget_credential=False):
        with self._reset_lock:
            DATA.mkdir(parents=True, exist_ok=True)
            self._reset_marker(owner).touch()
            self._generation += 1
            self.reset_owner = owner
            self.reset_error = ''
            if forget_credential:
                set_cookie(owner, '')

    def _clear_pending_cookies(self):
        with self._reset_lock:
            owner, window = self.reset_owner, self.window
            if not owner or window is None or not window.events.loaded.is_set():
                return False
            try:
                window.clear_cookies()
                window.load_url('https://www.baidu.com/')
                self._reset_marker(owner).unlink(missing_ok=True)
            except Exception:
                self.reset_error = '旧登录态暂未清理，可关闭百度登录窗口后重新打开'
                return False
            self.reset_owner = None
            self.reset_error = ''
            self.navigated = False
            return True

    def _loaded(self):
        if self.reset_owner:
            self._clear_pending_cookies()

    def _closed(self):
        self.window = None
        self.navigated = False

    def start(self, owner, replace=False):
        if replace:
            self._request_reset(owner, forget_credential=True)
        elif self.reset_owner != owner and self._reset_marker(owner).exists():
            self._request_reset(owner)
        if self.window is None:
            self.window = webview.create_window('百度账号连接', 'https://www.baidu.com/', width=1120, height=800,
                                                min_size=(850,650), text_select=True)
            self.window.events.closed += self._closed
            self.window.events.loaded += self._loaded
        else:
            self.window.show()
            self.window.restore()
        if self.reset_owner:
            # The first navigation can finish before create_window returns.
            self._clear_pending_cookies()
        if self.reset_owner:
            return {'status':'waiting','message':'正在清理旧登录态，随后请在百度官方页面重新登录'}
        return {'status':'waiting','message':'请在百度官方页面点击「登录」，选择页面提供的方式完成登录'}

    def status(self, owner):
        with self._reset_lock:
            window, generation, resetting = self.window, self._generation, self.reset_owner
        if window is None:
            return {'status':'closed','message':'点击打开百度登录窗口后完成登录'}
        if resetting:
            if not self._clear_pending_cookies() and self.reset_owner:
                return {'status':'waiting','message':self.reset_error or '正在清理旧登录态…'}
            return {'status':'waiting','message':'请在百度官方页面重新登录'}
        if not window.events.loaded.is_set():
            return {'status':'waiting','message':'正在载入百度官方页面…'}
        try:
            url = window.get_current_url() or ''
            host = urlparse(url).hostname or ''
            if not (host == 'baidu.com' or host.endswith('.baidu.com')):
                return {'status':'waiting','message':'正在载入百度官方页面…'}
            values = {}
            for cookie in window.get_cookies():
                for name,morsel in cookie.items():
                    domain = morsel['domain'].lstrip('.')
                    if not domain or domain == 'baidu.com' or domain.endswith('.baidu.com'):
                        values[name] = morsel.value
            if not values.get('BDUSS'):
                return {'status':'waiting','message':'请在官方页面完成登录…'}
            with self._reset_lock:
                if generation != self._generation or self.reset_owner or self.window is not window:
                    return {'status':'waiting','message':'正在检查当前登录窗口…'}
                if not values.get('Hmery-Time'):
                    if not self.navigated and host != 'wappass.baidu.com':
                        window.load_url('https://author.baidu.com/home/1595713367276134')
                        self.navigated = True
                    return {'status':'waiting','message':'百度已登录，正在连接百家号。如出现验证，请在官方窗口完成'}
                set_cookie(owner,'; '.join(f'{k}={v}' for k,v in values.items()))
            return {'status':'connected','message':'百度账号已连接'}
        except Exception:
            return {'status':'waiting','message':'正在读取百度登录状态…'}

    def close(self, owner):
        if self.window is not None:
            window,self.window=self.window,None
            window.destroy()

    def disconnect(self, owner):
        self._request_reset(owner, forget_credential=True)
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
