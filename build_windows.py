"""Build and self-check a windowed AKIRA.exe before activating its shortcut."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
from akira_version import BUILD_ID
from frozen_ui_contract import UI_MODULES,require_render_check
from native_studio_check import require_studio_check

def read_self_check_report(path,returncode,stderr=''):
 """Windowed executables write failures to JSON even when stderr is empty."""
 path=Path(path);report={};read_error=''
 try:
  report=json.loads(path.read_text(encoding='utf-8-sig'))
  if not isinstance(report,dict):raise ValueError('El diagnóstico no es un objeto JSON')
 except (OSError,ValueError) as error:
  report={};read_error='Diagnóstico ausente o ilegible: '+str(error)
 if returncode or report.get('status')!='PASSED':
  parts=['Código de salida: '+str(returncode)]
  if report.get('error'):parts.append(str(report['error']))
  detail=report.get('render_diagnostics')
  if isinstance(detail,dict) and detail.get('charts'):
   parts.append('Estado de gráficos: '+json.dumps(detail['charts'],ensure_ascii=True))
  if read_error:parts.append(read_error)
  if stderr.strip():parts.append(stderr.strip()[-1200:])
  raise RuntimeError('Falló la comprobación nativa: '+'; '.join(parts)+'. Revisa NATIVE_SELF_CHECK.json y NATIVE_SELF_CHECK_STDERR.log; no se activa.')
 return report

def build_command(source,destination,work):
 source=Path(source).resolve();destination=Path(destination).resolve();work=Path(work).resolve()
 command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','AKIRA',
  '--distpath',str(destination),'--workpath',str(work/'objects'),'--specpath',str(work),
  '--icon',str(source/'assets'/'akira.ico'),'--version-file',str(source/'windows_version.txt')]
 for filename in ('default_config.json','akira_config.json','selector_validation.json'):
  command+=['--add-data',str(source/filename)+os.pathsep+'.']
 command+=['--add-data',str(source/'assets')+os.pathsep+'assets']
 command+=['--add-data',str(source/'third_party')+os.pathsep+'licenses']
 for package in ('certifi','truststore','MetaTrader5','ctranslate2','faster_whisper','sounddevice','pyttsx3','piper','reportlab','PIL','imageio_ffmpeg','yt_dlp','yt_dlp_ejs','docx','tzdata','tzlocal','pypdf','onnxruntime','tokenizers'):
  command+=['--collect-all',package]
 for package in ('pyttsx3.drivers.sapi5','tests.fake_mt5','numpy','onnxruntime','av','win32com.propsys.propsys','win32com.propsys.pscon','win32com.shell.shell','pythoncom','win32crypt'):
  command+=['--hidden-import',package]
 for package in UI_MODULES:
  command+=['--hidden-import',package]
 command.append(str(source/'Akira.py'))
 return command

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--diagnostic',type=Path,required=True);args=parser.parse_args()
 if os.name!='nt':raise SystemExit('La aplicación de Windows se construye y verifica en Windows.')
 root=args.source.resolve();diag=args.diagnostic.resolve();diag.mkdir(parents=True,exist_ok=True)
 dist=root/'native';work=diag/'native_build';work.mkdir(parents=True,exist_ok=True)
 command=build_command(root,dist,work)
 with (diag/'NATIVE_BUILD.log').open('w',encoding='utf-8') as log:
  result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
 if result.returncode:raise RuntimeError('No se construyó AKIRA.exe. Se conserva la versión anterior. Consulta NATIVE_BUILD.log.')
 exe=dist/'AKIRA'/'AKIRA.exe'
 if not exe.is_file() or exe.read_bytes()[:2]!=b'MZ':raise RuntimeError('El constructor no produjo una aplicación de Windows válida')
 check=diag/'NATIVE_SELF_CHECK.json'
 try:
  result=subprocess.run([str(exe),'--self-check',str(check),'--app-root',str(root)],
                        cwd=root,timeout=90,capture_output=True,encoding='utf-8',errors='replace')
  (diag/'NATIVE_SELF_CHECK_STDOUT.log').write_text(result.stdout,encoding='utf-8')
  (diag/'NATIVE_SELF_CHECK_STDERR.log').write_text(result.stderr,encoding='utf-8')
 except subprocess.TimeoutExpired as error:
  (diag/'NATIVE_SELF_CHECK_TIMEOUT.txt').write_text(str(error),encoding='utf-8')
  raise RuntimeError('AKIRA.exe tardó más de 90 segundos en iniciar su autocomprobación; se conserva la versión anterior.') from error
 report=read_self_check_report(check,result.returncode,result.stderr)
 require_render_check(report)
 require_studio_check(report)
 if report.get('status')!='PASSED' or report.get('build')!=BUILD_ID or report.get('frozen') is not True or report.get('window_icon') is not True or report.get('app_id')!='AKIRA.Desktop.16':raise RuntimeError('La identidad o las dependencias de la aplicación no coinciden con el paquete')
 # A working --self-check is insufficient: launch from a genuinely empty
 # directory to reproduce the user's first-run FileNotFoundError.
 import tempfile
 with tempfile.TemporaryDirectory(prefix='akira-first-run-') as tempdir:
  first=diag/'NATIVE_FIRST_RUN.json'
  # No --app-root: this reproduces the user's double-click on a fresh ZIP.
  env=os.environ.copy()
  env.pop('AKIRA_APP_ROOT',None)
  env['LOCALAPPDATA']=str(Path(tempdir)/'LocalAppData')
  p=subprocess.run([str(exe),'--first-run-check',str(first)],
                   cwd=tempdir,env=env,timeout=90,capture_output=True,text=True,errors='replace')
  if p.returncode or not first.is_file():
   raise RuntimeError('Falló el primer inicio de AKIRA.exe sin configuración previa: '+p.stderr[-800:])
  first_result=json.loads(first.read_text(encoding='utf-8'))
  target=Path(env['LOCALAPPDATA'])/'AKIRA'/'akira_config.json'
  if first_result.get('status')!='PASSED' or not first_result.get('config_created') or not target.is_file():
   raise RuntimeError('AKIRA.exe no generó una configuración inicial segura en LocalAppData')
 (diag/'NATIVE_APPLICATION.json').write_text(json.dumps({'status':'PASSED','build':BUILD_ID,'executable':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'self_check':report},indent=2),encoding='utf-8')
 print(str(exe))

if __name__=='__main__':main()
