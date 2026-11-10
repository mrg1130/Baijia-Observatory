"""Baidu's official pages in the desktop application's own native browser window."""
import time
from urllib.parse import urlencode, urlparse, parse_qs

import webview

from .storage import set_cookie
from .desktop_js import read_snapshot


class NativeBaidu:
    def __init__(self):
        self.window = None
        self.navigated = False

    def _closed(self):
        self.window = None
        self.navigated = False

    def start(self, owner):
        if self.window is None:
            self.window = webview.create_window('百度账号连接', 'https://www.baidu.com/', width=1120, height=800,
                                                min_size=(850,650), text_select=True)
            self.window.events.closed += self._closed
        else:
            self.window.show()
            self.window.restore()
        return {'status':'waiting','message':'请在百度官方页面点击「登录」，选择页面提供的方式完成登录'}

    def status(self, owner):
        if self.window is None:
            return {'status':'closed','message':'点击打开百度登录窗口后完成登录'}
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
        if self.window is not None:
            self.window.clear_cookies()
        self.close(owner)
        set_cookie(owner,'')

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
