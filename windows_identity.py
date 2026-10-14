"""Windows shell identity and mutable application root for packaged builds."""
from pathlib import Path
import os,sys

APP_ID='AKIRA.Desktop.16'

def asset_path(name,root=None):
 candidates=[]
 if root is not None:candidates.append(Path(root)/'assets'/name)
 if getattr(sys,'_MEIPASS',None):candidates.append(Path(sys._MEIPASS)/'assets'/name)
 candidates.append(Path(__file__).resolve().parent/'assets'/name)
 return next((p for p in candidates if p.is_file()),candidates[-1])

def apply_window_icon(window,root=None):
 """Set the shell/window icon and the default for future Tk dialogs."""
 ico=asset_path('akira.ico',root)
 if os.name=='nt':
  try:
   window.iconbitmap(default=str(ico));window._akira_icon_path=str(ico)
   return True
  except Exception:pass
 try:
  import tkinter as tk
  png=asset_path('akira.png',root);photo=tk.PhotoImage(master=window,file=str(png))
  photo=photo.subsample(max(1,photo.width()//96),max(1,photo.height()//96))
  window.iconphoto(True,photo);window._akira_icon_photo=photo
  return True
 except Exception:return False

def apply_dark_titlebar(window):
 """Request a matching dark native Windows caption without removing OS resizing."""
 if os.name!='nt':return False
 try:
  import ctypes
  from ctypes import wintypes
  window.update_idletasks()
  user32=ctypes.windll.user32
  user32.GetParent.argtypes=[wintypes.HWND];user32.GetParent.restype=wintypes.HWND
  hwnd=user32.GetParent(window.winfo_id()) or window.winfo_id()
  dwm=ctypes.windll.dwmapi.DwmSetWindowAttribute
  dwm.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
  dwm.restype=ctypes.c_long
  on=ctypes.c_int(1)
  dark=dwm(hwnd,20,ctypes.byref(on),ctypes.sizeof(on))
  if dark!=0:dark=dwm(hwnd,19,ctypes.byref(on),ctypes.sizeof(on))
  # DWMWA_CAPTION_COLOR and DWMWA_TEXT_COLOR are available on newer builds.
  cap=ctypes.c_uint32(0x001b0909)
  txt=ctypes.c_uint32(0x00faefe3)
  dwm(hwnd,35,ctypes.byref(cap),ctypes.sizeof(cap))
  dwm(hwnd,36,ctypes.byref(txt),ctypes.sizeof(txt))
  return dark==0
 except (AttributeError,OSError,ValueError,TypeError,RuntimeError):return False

def create_shortcut(path,executable,root):
 """The shortcut and process share the same explicit Windows taskbar identity."""
 import pythoncom
 from win32com.shell import shell
 from win32com.propsys import propsys,pscon
 pythoncom.CoInitialize()
 try:
  link=pythoncom.CoCreateInstance(shell.CLSID_ShellLink,None,pythoncom.CLSCTX_INPROC_SERVER,shell.IID_IShellLink)
  executable=Path(executable).resolve();root=Path(root).resolve()
  link.SetPath(str(executable));link.SetArguments('--app-root "'+str(root)+'"')
  link.SetWorkingDirectory(str(root));link.SetDescription('AKIRA · 16.2')
  link.SetIconLocation(str(asset_path('akira.ico',root)),0)
  properties=link.QueryInterface(propsys.IID_IPropertyStore)
  properties.SetValue(pscon.PKEY_AppUserModel_ID,propsys.PROPVARIANTType(APP_ID))
  properties.SetValue(pscon.PKEY_AppUserModel_RelaunchDisplayNameResource,propsys.PROPVARIANTType('AKIRA'))
  properties.SetValue(pscon.PKEY_AppUserModel_RelaunchIconResource,propsys.PROPVARIANTType(str(asset_path('akira.ico',root))+',0'))
  properties.SetValue(pscon.PKEY_AppUserModel_RelaunchCommand,propsys.PROPVARIANTType('"'+str(executable)+'" --app-root "'+str(root)+'"'))
  properties.Commit();link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path),1)
 finally:pythoncom.CoUninitialize()

def repair_akira_pins(new_shortcut,previous_root,diagnostic):
 """Replace only pins targeting the previous AKIRA installation; keep backups."""
 import json,shutil,pythoncom
 from win32com.shell import shell
 if not previous_root:return []
 previous=Path(previous_root).resolve();folder=Path(os.environ['APPDATA'])/'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar'
 repaired=[];pythoncom.CoInitialize()
 try:
  for pin in folder.glob('*.lnk'):
   link=pythoncom.CoCreateInstance(shell.CLSID_ShellLink,None,pythoncom.CLSCTX_INPROC_SERVER,shell.IID_IShellLink)
   try:
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(pin));target=Path(link.GetPath(0)[0]).resolve();args=link.GetArguments()
    native=target==previous/'native/AKIRA/AKIRA.exe'
    script='akira.py' in args.lower() and str(previous).lower() in args.lower()
    if not native and not script:continue
    backup=Path(diagnostic)/'anclajes_anteriores'/pin.name;backup.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(pin,backup);shutil.copy2(new_shortcut,pin);repaired.append(pin.name)
   except Exception:continue
 finally:pythoncom.CoUninitialize()
 (Path(diagnostic)/'TASKBAR_IDENTITY.json').write_text(json.dumps({'app_id':APP_ID,'repaired':repaired},indent=2),encoding='utf-8')
 try:
  import ctypes
  ctypes.windll.shell32.SHChangeNotify(0x08000000,0,None,None)
 except (AttributeError,OSError):pass
 return repaired

def set_identity():
 if os.name=='nt':
  try:
   import ctypes
   ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
  except (AttributeError,OSError):pass

def application_root():
 explicit=os.environ.get('AKIRA_APP_ROOT')
 if explicit:return Path(explicit).resolve()
 if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parents[2]
 return Path(__file__).resolve().parent

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--shortcut');parser.add_argument('--executable');parser.add_argument('--root');parser.add_argument('--repair-pins');parser.add_argument('--previous-root');parser.add_argument('--diagnostic');args=parser.parse_args()
 if args.shortcut:create_shortcut(args.shortcut,args.executable,args.root)
 if args.repair_pins:repair_akira_pins(args.repair_pins,args.previous_root,args.diagnostic)
