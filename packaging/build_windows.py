import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=root/'release')
args=parser.parse_args()
output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(root/'dist'),'--workpath',str(root/'build'),str(root/'packaging/app.spec')],cwd=root,check=True)
app=root/'dist/BaijiaObservatory'
(app/'uninstall.ps1').write_text((root/'packaging/uninstall.ps1').read_text(encoding='utf-8'),encoding='utf-8-sig',newline='\r\n')
stage=root/'build/installer';stage.mkdir(parents=True,exist_ok=True)
with ZipFile(stage/'payload.zip','w',ZIP_DEFLATED) as z:
    for file in app.rglob('*'):
        if file.is_file():z.write(file,file.relative_to(app))
for name in ['install.cmd','install.ps1']:
    text=(root/'packaging'/name).read_text(encoding='utf-8')
    (stage/name).write_text(text,encoding='utf-8-sig' if name.endswith('.ps1') else 'ascii',newline='\r\n')
# Use Windows' built-in IExpress to produce a self-contained per-user installer.
target=output/'BaijiaObservatory-1.1.0-Windows-x64-Setup.exe'
sed='''[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=Install Baijia Observatory 1.1.0?
DisplayLicense=
FinishMessage=Installation complete. Open Baijia Observatory from the desktop.
TargetName={target}
FriendlyName=Baijia Observatory Setup
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd
UserQuietInstCmd=install.cmd
SourceFiles=SourceFiles
[Strings]
FILE0="payload.zip"
FILE1="install.cmd"
FILE2="install.ps1"
[SourceFiles]
SourceFiles0={stage}\\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
'''.format(target=target,stage=stage)
spec=stage/'installer.sed';spec.write_text(sed,encoding='mbcs',newline='\r\n')
subprocess.run(['iexpress.exe','/N','/Q',str(spec)],cwd=stage,check=True)
if not target.is_file():raise RuntimeError('Installer was not produced')
print(target)
