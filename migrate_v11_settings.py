"""Recupera Akira completa sin sustituir la cuenta, riesgo o diario actuales."""
import argparse,json,shutil,sqlite3
from contextlib import closing
from pathlib import Path
from settings import load_config,save_config

AI_SECTIONS=('assistant','desktop','knowledge','final_v6')
RECOVERABLE_STATE=('knowledge.sqlite3','daily_learning.json','transcript_analyses')

def read_config(root):
    return json.loads((Path(root)/'akira_config.json').read_text(encoding='utf-8-sig'))

def find_restore_root(current,search_root=None):
    current=Path(current) if current else None
    if current:
        try:
            cfg=read_config(current)
            if isinstance(cfg.get('assistant'),dict) and cfg['assistant']:return current
        except (OSError,ValueError):pass
    parent=Path(search_root) if search_root else current.parent if current else None
    if parent is None or not parent.is_dir():return None
    candidates=[]
    for path in parent.iterdir():
        if not path.is_dir() or not (path.name.lower().startswith('akira.backup.') or path.name.upper().startswith(('AKIRA_FINAL','AKIRA_V'))):continue
        try:
            cfg=read_config(path)
            if isinstance(cfg.get('assistant'),dict) and cfg['assistant']:candidates.append(path)
        except (OSError,ValueError):pass
    return max(candidates,key=lambda p:p.stat().st_mtime) if candidates else None

def migrate(raw,restored=None):
    merged=dict(raw or restored or {})
    if isinstance(restored,dict):
        for key in AI_SECTIONS:
            if key not in merged and key in restored:merged[key]=restored[key]
        # V10 conservó esta sección, pero no la estaba usando: recuperar preferencias.
        if 'assistant' not in raw and 'knowledge' in restored:merged['knowledge']=restored['knowledge']
    cfg=load_config(merged)
    if not raw and not restored:
        # Conservative onboarding applies ONLY to a genuinely fresh profile.
        # A reinstall never silently modifies a subscriber's configured risk.
        cfg['risk'].update(max_trade_pct=2.0, max_trade_money=15.0,
                           portfolio_capital_pct=5.0, daily_loss_pct=4.0)
        # Solo instalaciones nuevas: habilitar lotaje proporcional, nunca multiplicar
        # riesgo para forzar el mínimo del bróker en una cuenta pequeña.
        cfg['sizing'].update(enabled=True,scale_pending=True,boost_score=85.0,
                             boost_quality=85.0,risk_utilization=0.75)
        cfg['risk']['min_lot_structural_override_enabled']=False
        cfg['mode']='observe'  # explicit opt-in to live trading is required
    return cfg

def copy_missing(source,destination):
    if not source.exists():return
    if source.is_dir():
        destination.mkdir(parents=True,exist_ok=True)
        for item in source.iterdir():copy_missing(item,destination/item.name)
    elif not destination.exists():
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)

def merge_memory(source,destination):
    if not source.is_file():return {'sources':0,'turns':0}
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        # sqlite3's own context manager commits/rolls back but does not close.
        # Release both handles before Windows removes or renames staged files.
        with closing(sqlite3.connect(source,timeout=10)) as src,closing(sqlite3.connect(destination,timeout=10)) as dest:
            with dest:src.backup(dest)
        return {'copied':True}
    if source.resolve()==destination.resolve():return {'copied':False}
    with closing(sqlite3.connect(source,timeout=10)) as src,closing(sqlite3.connect(destination,timeout=10)) as dest:
        with dest:
            tables={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            own={r[0] for r in dest.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            turns=0;sources=0
            if 'conversation' in tables and 'conversation' in own:
                for at,role,body in src.execute('SELECT at,role,body FROM conversation ORDER BY at,id'):
                    if not dest.execute('SELECT 1 FROM conversation WHERE at=? AND role=? AND body=?',(at,role,body)).fetchone():
                        dest.execute('INSERT INTO conversation(at,role,body) VALUES (?,?,?)',(at,role,body));turns+=1
                # ID es distinto al fusionar dos memorias; mantener la cronología real.
                rows=dest.execute('SELECT at,role,body FROM conversation ORDER BY at,id').fetchall()
                dest.execute('DELETE FROM conversation')
                dest.executemany('INSERT INTO conversation(at,role,body) VALUES (?,?,?)',rows)
            if 'sources' in tables and 'sources' in own:
                for row in src.execute('SELECT * FROM sources'):
                    old=dest.execute('SELECT fetched FROM sources WHERE url=?',(row[0],)).fetchone()
                    if old is None or float(row[5] or 0)>float(old[0] or 0):
                        dest.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)',row);sources+=1
    return {'sources':sources,'turns':turns}

def restore_user_data(current,restored,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    current=Path(current) if current else None;restored=Path(restored) if restored else None
    if current and current.is_dir():
        for name in ('state','logs','exports','studio','AKIRA_SECRETS.json'):
            source=current/name;target=destination/name
            if name=='state' and source.is_dir():
                target.mkdir(exist_ok=True)
                for item in source.iterdir():
                    if item.name.startswith('knowledge.sqlite3'):continue
                    if item.is_dir():shutil.copytree(item,target/item.name,dirs_exist_ok=True)
                    else:shutil.copy2(item,target/item.name)
            elif source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True)
            elif source.is_file():shutil.copy2(source,target)
        merge_memory(current/'state'/'knowledge.sqlite3',destination/'state'/'knowledge.sqlite3')
    if restored and restored.is_dir() and (not current or restored.resolve()!=current.resolve()):
        # Nunca resucitar intents/diarios antiguos de órdenes: manda el estado actual.
        for name in RECOVERABLE_STATE:
            if name=='knowledge.sqlite3':merge_memory(restored/'state'/name,destination/'state'/name)
            else:copy_missing(restored/'state'/name,destination/'state'/name)
        copy_missing(restored/'exports',destination/'exports')
        copy_missing(restored/'studio',destination/'studio')
        copy_missing(restored/'AKIRA_SECRETS.json',destination/'AKIRA_SECRETS.json')
    # Studio assets reside under a versioned release. Rebase their safe,
    # app-owned paths before an updater may delete the inactive release.
    # Never rewrite or import paths outside the previous Studio directories.
    cfgpath=destination/'akira_config.json'
    if cfgpath.is_file():
        raw=json.loads(cfgpath.read_text(encoding='utf-8-sig'))
        studio=raw.get('studio') if isinstance(raw,dict) else None
        changed=False
        if isinstance(studio,dict):
            def rebase(location):
                nonlocal changed
                if not location:return location
                try:
                    path=Path(location).resolve()
                    for previous in (current,restored):
                        if previous and path.is_relative_to((previous/'studio').resolve()):
                            target=destination/'studio'/path.relative_to((previous/'studio').resolve())
                            if target.is_file():
                                changed=True
                                # Preserve the destination spelling supplied by the updater.
                                # Windows may resolve 8.3 aliases (RUNNER~1) to a different
                                # long path (runneradmin). Both refer to the same file, but
                                # the saved setting should follow the new installation root
                                # rather than embed a different OS-specific spelling.
                                return str(target)
                except (ValueError,TypeError,OSError):pass
                return location
            studio['language_pack']=rebase(studio.get('language_pack',''))
            wallpaper=studio.get('wallpaper') or {}
            if isinstance(wallpaper,dict):
                wallpaper['file']=rebase(wallpaper.get('file'))
            avatar=studio.get('avatar') or {}
            if isinstance(avatar,dict):
                for row in avatar.get('entries') or []:
                    if isinstance(row,dict):row['path']=rebase(row.get('path'))
            if changed:
                temp=cfgpath.with_suffix('.studio.tmp')
                temp.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                temp.replace(cfgpath)
    return {'current':str(current or ''),'restored':str(restored or ''),'destination':str(destination)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('target');parser.add_argument('--search-root');parser.add_argument('--restore-file');parser.add_argument('--copy-data-to');args=parser.parse_args()
    current=None if args.source in ('__NONE__','-') else Path(args.source).parent
    raw=read_config(current) if current else {};restored=find_restore_root(current,args.search_root)
    if args.copy_data_to:
        if args.restore_file and Path(args.restore_file).is_file():
            info=json.loads(Path(args.restore_file).read_text(encoding='utf-8'));restored=Path(info['restored']) if info.get('restored') else None
        report=restore_user_data(current,restored,args.copy_data_to)
        (Path(args.copy_data_to)/'RECUPERACION_AKIRA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        save_config(migrate(raw,read_config(restored) if restored else None),args.target)
        if args.restore_file:Path(args.restore_file).write_text(json.dumps({'restored':str(restored or '')}),encoding='utf-8')
    print('Akira completa recuperada; cuenta, límites y diario vigentes conservados. '+('Preferencias previas: '+str(restored) if restored else 'Sin copia previa de preferencias; funciones completas incluidas.'))

if __name__=='__main__':main()
