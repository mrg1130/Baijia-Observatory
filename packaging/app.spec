# -*- mode: python ; coding: utf-8 -*-
import sys
import runpy
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root=Path(SPECPATH).parent
identity=runpy.run_path(str(root/'studio/version.py'))
version=identity['APP_VERSION']
windows_version=None
if sys.platform=='win32':
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo,
        StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct)
    version_tuple=tuple(map(int,version.split('.')))+(0,)
    windows_version=VSVersionInfo(ffi=FixedFileInfo(filevers=version_tuple,prodvers=version_tuple),kids=[
        StringFileInfo([StringTable('080404B0',[
            StringStruct('CompanyName',identity['APP_PUBLISHER']),
            StringStruct('FileDescription',identity['APP_NAME']),
            StringStruct('FileVersion',version),
            StringStruct('ProductName',identity['APP_NAME']),
            StringStruct('ProductVersion',version),
            StringStruct('OriginalFilename','BaijiaObservatory.exe')])]),
        VarFileInfo([VarStruct('Translation',[2052,1200])])])
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
        version=windows_version,
        icon=str(root/'packaging'/('app.ico' if sys.platform=='win32' else 'app.icns')))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='BaijiaObservatory')
if sys.platform=='darwin':
    app=BUNDLE(coll,name='百家观测.app',icon=str(root/'packaging/app.icns'),bundle_identifier='com.baijia.observatory',
               info_plist={'CFBundleShortVersionString':version,'CFBundleVersion':version,'NSHighResolutionCapable':True,
                           'LSMinimumSystemVersion':'12.0','NSAppTransportSecurity':{'NSAllowsLocalNetworking':True,'NSAllowsArbitraryLoadsInWebContent':True}})
