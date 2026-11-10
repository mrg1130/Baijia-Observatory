"""Native Windows/macOS entry point; the packaged app includes its Python runtime."""
import argparse
import ctypes
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import uvicorn
import webview

from studio.storage import DATA
from studio.server import app
from studio import browser_login
from studio.native_login import NativeBaidu


class DesktopApi:
    def open_manual(self):
        manual=Path(__file__).parent/'studio'/'manual.pdf'
        if not manual.exists():
            return {'ok':False,'message':'使用说明正在准备中'}
        if os.name=='nt':
            os.startfile(str(manual))
        else:
            subprocess.Popen(['open',str(manual)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'ok':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--ui-smoke-test',action='store_true')
    args=parser.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=DATA/'desktop.log',level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    lock=None
    if os.name=='nt':
        lock=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\BaijiaObservatoryDesktop')
        if ctypes.windll.kernel32.GetLastError()==183:
            window=ctypes.windll.user32.FindWindowW(None,'百家观测')
            if window:
                ctypes.windll.user32.ShowWindow(window,9)
                ctypes.windll.user32.SetForegroundWindow(window)
            return
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    config=uvicorn.Config(app,host='127.0.0.1',port=port,log_config=None,access_log=False,loop='asyncio',http='h11')
    server=uvicorn.Server(config)
    thread=threading.Thread(target=server.run,daemon=True)
    thread.start()
    url=f'http://127.0.0.1:{port}'
    for _ in range(100):
        try:
            with urllib.request.urlopen(url+'/api/workspace',timeout=.5) as r:
                workspace=json.load(r)
            break
        except OSError:
            time.sleep(.1)
    else:
        raise RuntimeError('工作台启动超时，请重新打开软件')
    if args.smoke_test:
        (DATA/'smoke-test.json').write_text(json.dumps({'status':'ok','workspace':workspace,'url':url}),encoding='utf-8')
        server.should_exit=True
        thread.join(5)
        return
    browser_login.native_client=NativeBaidu()
    webview.settings['ALLOW_DOWNLOADS']=True
    main_window=webview.create_window('百家观测',url,js_api=DesktopApi(),width=1440,height=960,min_size=(1000,700),
                                     text_select=True,background_color='#f5f6f3')
    def close():
        browser_login.native_client.close(workspace['id'])
        server.should_exit=True
    main_window.events.closed+=close
    def verify_ui():
        report={'status':'failed'}
        try:
            if not main_window.events.loaded.wait(30):
                raise RuntimeError('Desktop document did not load')
            for _ in range(100):
                body=main_window.evaluate_js('document.body.innerText') or ''
                if all(label in body for label in ['数据概览','添加监控账号','连接与设置']):
                    report={'status':'ok','title':main_window.evaluate_js('document.title'),'workspace_rendered':True}
                    break
                time.sleep(.1)
        except Exception as exc:
            report['error']=str(exc)
        finally:
            (DATA/'ui-smoke-test.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
            main_window.destroy()
    try:
        webview.start(func=verify_ui if args.ui_smoke_test else None,gui='edgechromium' if os.name=='nt' else 'cocoa',
                      private_mode=False,storage_path=str(DATA/'webview'))
    finally:
        server.should_exit=True
        thread.join(4)
        if lock:
            ctypes.windll.kernel32.CloseHandle(lock)


if __name__=='__main__':
    main()
