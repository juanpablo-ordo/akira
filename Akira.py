"""Entrada única de AKIRA Studio y proceso de voz empaquetable."""
import argparse
from pathlib import Path
import os,sys
from windows_identity import set_identity,application_root

if __name__=='__main__':
    set_identity()
    parser=argparse.ArgumentParser();parser.add_argument('--sources-check');parser.add_argument('--low-resource-check');parser.add_argument('--https-check');parser.add_argument('--prepare-uninstall',action='store_true');parser.add_argument('--preview',action='store_true');parser.add_argument('--speech-worker');parser.add_argument('--app-root');parser.add_argument('--self-check');parser.add_argument('--first-run-check');parser.add_argument('--local-components-check');parser.add_argument('--sprite-ai-check');parser.add_argument('--installation-info');parser.add_argument('--legacy-ui',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    if args.sources_check:
        import json
        from qa_sources_rev10 import run
        try:result=run(args.sources_check)
        except Exception as error:
            result={'status':'FAILED','error':type(error).__name__+': '+str(error)}
            Path(args.sources_check).write_text(json.dumps(result,indent=2),encoding='utf-8')
        sys.exit(0 if result['status']=='PASSED' else 1)
    if args.low_resource_check:
        import json
        from qa_low_resource_rev7 import run
        try:result=run(args.low_resource_check)
        except Exception as error:
            result={'status':'FAILED','error':type(error).__name__+': '+str(error)}
            Path(args.low_resource_check).write_text(json.dumps(result,indent=2),encoding='utf-8')
        sys.exit(0 if result['status']=='PASSED' else 1)
    if args.https_check:
        import json
        from network_tls import check_packaged_https
        try:result=check_packaged_https()
        except Exception as error:result={'status':'FAILED','error':type(error).__name__+': '+str(error)}
        Path(args.https_check).write_text(json.dumps(result,indent=2),encoding='utf-8');sys.exit(0 if result['status']=='PASSED' else 1)
    if args.prepare_uninstall:
        from application_management import prepare_native_uninstall
        sys.exit(0 if prepare_native_uninstall(Path(sys.executable).parent)['status']=='READY' else 1)
    if args.app_root:os.environ['AKIRA_APP_ROOT']=str(Path(args.app_root).resolve())
    if args.installation_info:
        import json
        from installation_info import describe_installation
        result=describe_installation();output=Path(args.installation_info);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');sys.exit(0)
    if args.local_components_check:
        from local_components import check_components
        sys.exit(check_components(args.local_components_check,application_root()))
    if args.sprite_ai_check:
        import json
        from sprite_recognition import check_visual_component
        try:result=check_visual_component()
        except Exception as error:result={'status':'FAILED','error':type(error).__name__+': '+str(error)}
        Path(args.sprite_ai_check).write_text(json.dumps(result,indent=2),encoding='utf-8');sys.exit(0 if result['status']=='PASSED' else 1)
    if args.first_run_check:
        # Non-interactive installed-application smoke test, also used in CI.
        import json
        from settings import ensure_user_config,load_config
        folder=application_root()
        config=ensure_user_config(folder)
        loaded=load_config(config)
        result={'status':'PASSED' if loaded['mode']=='observe' and loaded['expected_login']==0 else 'FAILED',
                'config_created':config.is_file(),'mode':loaded.get('mode'),
                'expected_login':loaded.get('expected_login')}
        Path(args.first_run_check).write_text(json.dumps(result,indent=2),encoding='utf-8')
        sys.exit(0 if result['status']=='PASSED' else 1)
    if args.speech_worker:
        from voice_session import speech_worker
        speech_worker(args.speech_worker);sys.exit(0)
    if args.self_check:
        import importlib,json
        from akira_version import BUILD_ID
        result={'build':BUILD_ID,'frozen':bool(getattr(sys,'frozen',False)),'status':'PASSED','modules':[]}
        try:
            for name in ('MetaTrader5','faster_whisper','sounddevice','pyttsx3','piper','reportlab','PIL','pypdf','docx','settings','desktop_qt','PySide6.QtWidgets','onnxruntime','tokenizers'):
                importlib.import_module(name);result['modules'].append(name)
            if sys.platform=='win32':
                import win32crypt
                probe=b'AKIRA credential protection self-check'
                sealed=win32crypt.CryptProtectData(probe,'AKIRA',None,None,None,1)
                opened=win32crypt.CryptUnprotectData(sealed,None,None,None,1)[1]
                if sealed==probe or opened!=probe:raise RuntimeError('La protección de credenciales de Windows no pasó su autocomprobación')
                result['credential_protection']='DPAPI round-trip PASSED'
            import tkinter as tk
            from tk_runtime import create_root
            from windows_identity import apply_window_icon,APP_ID
            window=create_root();window.withdraw();result['tk_bootstrap']=window._akira_tk_bootstrap;result['window_icon']=apply_window_icon(window,application_root());result['app_id']=APP_ID;window.destroy()
            if not result['window_icon']:raise RuntimeError('No se pudo aplicar el icono de AKIRA a la ventana nativa')
            from frozen_ui_contract import UI_MODULES,require_render_check
            for name in UI_MODULES:
                importlib.import_module(name)
                if name not in result['modules']:result['modules'].append(name)
            from native_ui_check import run_ui_check
            window=create_root();window.withdraw()
            result['render_check']=run_ui_check(window)
            require_render_check(result)
            from native_studio_check import run_studio_check,require_studio_check
            result['studio_check']=run_studio_check(screenshot_dir=Path(args.self_check).parent/'studio_pages');require_studio_check(result)
        except Exception as exc:
            import traceback
            result.update(status='FAILED',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
            diagnostics=getattr(exc,'render_diagnostics',None)
            if isinstance(diagnostics,dict):result['render_diagnostics']=diagnostics
        Path(args.self_check).write_text(json.dumps(result,indent=2),encoding='utf-8');sys.exit(0 if result['status']=='PASSED' else 1)
    try:
        if args.legacy_ui:
            from desktop import main
        else:
            from desktop_qt import main
        sys.exit(main(args.preview) or 0)
    except Exception:
        import traceback
        folder=application_root()/'logs';folder.mkdir(parents=True,exist_ok=True)
        (folder/'inicio_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        try:
            from tkinter import messagebox
            messagebox.showerror('Akira',traceback.format_exc())
        except Exception:raise
