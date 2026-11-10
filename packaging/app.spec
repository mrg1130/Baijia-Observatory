# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root=Path(SPECPATH).parent
datas=[(str(root/'studio/web'),'studio/web')]
if (root/'studio/manual.pdf').exists():
    datas.append((str(root/'studio/manual.pdf'),'studio'))
binaries=[]
hiddenimports=['uvicorn.logging','uvicorn.loops.asyncio','uvicorn.protocols.http.h11_impl','uvicorn.lifespan.on']
for package in ['curl_cffi','webview']:
    d,b,h=collect_all(package)
    datas+=d;binaries+=b;hiddenimports+=h
if sys.platform=='darwin':
    hiddenimports+=collect_submodules('keyring.backends.macOS')
a=Analysis([str(root/'desktop.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hiddenimports,
           excludes=['PyQt5','PyQt6','PySide2','PySide6','tkinter','matplotlib','scipy','pandas','numpy'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='BaijiaObservatory',console=False,debug=False,
        icon=str(root/'packaging'/('app.ico' if sys.platform=='win32' else 'app.icns')))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='BaijiaObservatory')
if sys.platform=='darwin':
    app=BUNDLE(coll,name='百家观测.app',icon=str(root/'packaging/app.icns'),bundle_identifier='com.baijia.observatory',
               info_plist={'CFBundleShortVersionString':'1.1.0','CFBundleVersion':'1.1.0','NSHighResolutionCapable':True,
                           'LSMinimumSystemVersion':'12.0','NSAppTransportSecurity':{'NSAllowsLocalNetworking':True,'NSAllowsArbitraryLoadsInWebContent':True}})
