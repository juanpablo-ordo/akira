"""Install Rev18, then update it and verify shortcuts and real saved data.

Uses a new owned test folder and private application data. Never opens MT5.
"""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,traceback
from pathlib import Path


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install(setup,root,log,tasks):
    command=[str(Path(setup).resolve()),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
        '/DIR='+str(root),'/TASKS='+tasks,'/LOG='+str(log)]
    result=subprocess.run(command,timeout=600,check=False)
    if result.returncode:raise RuntimeError('La actualización del instalador terminó con código '+str(result.returncode))


def verify(previous_setup,setup,root,report,previous_source,remove_previous_setup=False):
    if os.name!='nt':raise RuntimeError('La actualización del instalador se comprueba en Windows.')
    import pythoncom
    from win32com.client import Dispatch
    from win32com.shell import shell,shellcon
    from win32api import GetFileVersionInfo,HIWORD,LOWORD
    from settings import DEFAULT,load_config,save_config
    from chat_store import ChatStore
    from akira_version import BUILD_ID
    from installer.check_installed_ai import validate_installed_payload
    from PIL import Image
    from installer.summarize_revision import verify_manifest
    from bundled_model import MODEL_NAME,MODEL_PATH,LEGACY_MODEL_NAME,LEGACY_MODEL_PATH

    root=Path(root).resolve();report=Path(report).resolve();report.parent.mkdir(parents=True,exist_ok=True)
    if root.exists():raise FileExistsError('La comprobación requiere una carpeta de prueba nueva: '+str(root))
    root.mkdir(parents=True);(root/'AKIRA_UPGRADE_TEST.txt').write_text('Owned installer test',encoding='utf-8')
    previous_source=Path(previous_source).resolve()
    source_commit=subprocess.run(['git','-C',str(previous_source),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    checks={'previous_source_commit_verified':source_commit=='de98b491fdb67ca0e207b0bca379e77da5f1df51',
        'previous_source_manifest_verified':verify_manifest(previous_source)==470}
    if not all(checks.values()):raise RuntimeError('La fuente de referencia Rev18 no coincide con la revisión verificada.')
    pythoncom.CoInitialize();wscript=None
    def version(exe):
        data=GetFileVersionInfo(str(exe),'\\');return (HIWORD(data['FileVersionMS']),LOWORD(data['FileVersionMS']),HIWORD(data['FileVersionLS']),LOWORD(data['FileVersionLS']))
    try:
        wscript=Dispatch('WScript.Shell');desktop=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_DESKTOPDIRECTORY,None,0))/'AKIRA.lnk'
        def shortcut(target,arguments):
            link=wscript.CreateShortcut(str(desktop));link.TargetPath=str(target);link.Arguments=arguments;link.WorkingDirectory=str(root);link.Save();del link
        def read_shortcut(path=desktop):
            link=wscript.CreateShortcut(str(path));result=(Path(link.TargetPath).resolve(),str(link.Arguments));del link;return result
        install(previous_setup,root,report.with_suffix('.previous.log'),'desktopicon')
        checks['previous_installer_is_rev18']=version(root/'AKIRA.exe')==(16,5,3,0)
        if not checks['previous_installer_is_rev18']:raise RuntimeError('El instalador de referencia no es Rev18.')
        if remove_previous_setup:
            previous=Path(previous_setup).resolve()
            if not previous.is_relative_to(previous_source/'dist_installer'):raise ValueError('Solo se elimina el instalador reconstruido en la carpeta de prueba.')
            previous.unlink()
        legacy_program=root.parent/(root.name+'_previous_program');legacy_program.mkdir();old_exe=legacy_program/'AKIRA.exe';shutil.copy2(root/'AKIRA.exe',old_exe)
        with tempfile.TemporaryDirectory(prefix='AKIRA_UPGRADE_DATA_') as personal:
            private_local=Path(personal)/'Local';private_local.mkdir()
            probe_env={**os.environ,'LOCALAPPDATA':str(private_local)};probe_env.pop('AKIRA_APP_ROOT',None)
            for name,explicit in [('canonical',False),('legacy_argument',True)]:
                data_root=(Path(personal)/'previous_saved_data') if explicit else private_local/'AKIRA';data_root.mkdir()
                wallpaper=data_root/'background.png';Image.new('RGB',(12,12),'#97c5dd').save(wallpaper)
                cfg=load_config(DEFAULT);cfg['risk'].update(max_trade_money=3.5,max_trade_pct=30,portfolio_money_cap=12,portfolio_capital_pct=40)
                cfg['assistant'].update(local_model=LEGACY_MODEL_NAME,local_model_lite=LEGACY_MODEL_NAME,fast_chat_model=LEGACY_MODEL_NAME,local_runtime_model=LEGACY_MODEL_PATH)
                cfg['desktop']['memory_budget_mb']=3072
                cfg['desktop']['privacy']=True;cfg['studio']['brand_name']='AKIRA guardada'
                cfg['studio']['wallpaper'].update(enabled=True,kind='image',file=str(wallpaper))
                save_config(cfg,data_root/'akira_config.json');store=ChatStore(data_root)
                store.append('user','Conversación que debe conservarse');store.append('assistant','Historial conservado para la prueba.');store.remember('Preferencia conservada')
                paths=[data_root/'akira_config.json',data_root/'state/chats.sqlite',wallpaper]
                before={str(p.relative_to(data_root)):digest(p) for p in paths}
                arguments='--app-root "'+str(data_root)+'"' if explicit else ''
                shortcut(old_exe,arguments)
                install(setup,root,report.with_suffix('.'+name+'.log'),'')
                target,saved_arguments=read_shortcut()
                checks[name+'_shortcut_targets_new_executable']=target==(root/'AKIRA.exe').resolve() and version(target)==(16,5,4,0)
                checks[name+'_shortcut_keeps_data_arguments']=saved_arguments==arguments
                menu=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_PROGRAMS,None,0))/'AKIRA.lnk'
                menu_target,menu_arguments=read_shortcut(menu)
                checks[name+'_start_menu_keeps_executable_and_data']=menu_target==target and menu_arguments==arguments
                info_path=report.with_suffix('.'+name+'.info.json')
                command=[str(target),'--installation-info',str(info_path)]
                if explicit:command+=['--app-root',str(data_root)]
                subprocess.run(command,env=probe_env,timeout=60,check=True)
                info=json.loads(info_path.read_text(encoding='utf-8'))
                checks[name+'_actual_application_reads_same_data']=info['build']==BUILD_ID and Path(info['application_data_root'])==data_root.resolve() and info['preferences']['risk']=={k:cfg['risk'][k] for k in ('max_trade_money','max_trade_pct','portfolio_money_cap','portfolio_capital_pct')}
                checks[name+'_bundled_model_migrates_without_rewriting_settings']=info['preferences']['local_ai']['local_model']==MODEL_NAME and info['preferences']['local_ai']['local_runtime_model']==MODEL_PATH
                checks[name+'_configuration_chat_and_background_unchanged']=before=={str(p.relative_to(data_root)):digest(p) for p in paths}
                checks[name+'_no_broker_or_model_started']=not info['broker_started'] and not info['model_started']
            files=validate_installed_payload(root)
            checks['bundled_model_and_components_survive_upgrade']=all(p.is_file() for p in files.values())
        if not all(checks.values()):raise RuntimeError('Upgrade verification failed: '+json.dumps(checks,ensure_ascii=False))
        return {'status':'PASSED','build':BUILD_ID,'checks':checks,'previous_version':'16.5.3 Studio Rev18','previous_source_commit':source_commit,
            'live_account_used':False,'private_application_data':True,'model_downloaded_by_check':False}
    finally:
        wscript=None;pythoncom.CoUninitialize()


def main():
    p=argparse.ArgumentParser();p.add_argument('--previous-setup',type=Path,required=True);p.add_argument('--setup',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--previous-source',type=Path,required=True);p.add_argument('--remove-previous-setup',action='store_true');args=p.parse_args()
    try:result=verify(args.previous_setup,args.setup,args.root,args.report,args.previous_source,args.remove_previous_setup)
    except Exception as error:result={'status':'FAILED','error':type(error).__name__+': '+str(error),'traceback':traceback.format_exc()}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0 if result['status']=='PASSED' else 1


if __name__=='__main__':raise SystemExit(main())
