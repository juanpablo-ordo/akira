"""Desactiva el controlador anterior si existe; no instala ni ejecuta ningún EA."""
from pathlib import Path
import os,re,time
from execution import Blocked,REJECTED

STATUS=('protocol','login','server','symbol','updated_ms','boot','ready','tradable','busy','closing','positions','last_code','dispatch_us','roundtrip_ms','ticks','tick_us','last_id','state','end')
ACK=('protocol','session','id','symbol','updated_ms','state','retcode','order','deal','request_id','position_id','campaign_id','reason','dispatch_us','roundtrip_ms','end')

def safe(value):return re.sub(r'[^A-Za-z0-9_-]','_',str(value))

def unpack(path,fields,protocol):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>16384:return None
        parts=raw.decode('utf-8-sig').strip().split('|')
        if len(parts)!=len(fields) or parts[0]!=protocol or parts[-1]!='END':return None
        return dict(zip(fields,parts))
    except (OSError,UnicodeError):return None

def retire(g):
    if g.cfg['mode']!='trade':return
    snap=g.snapshot();common=getattr(snap.terminal,'commondata_path','')
    if not common:return
    root=Path(common)/'Files'/'AkiraNativeV3'/f'{int(snap.account.login)}_{safe(snap.account.server)}'
    if not root.is_dir():return
    for symbol in g.cfg['symbols']:
        folder=root/safe(symbol);control=folder/'control.txt'
        if not control.is_file():
            state=unpack(folder/'status.txt',STATUS,'AKIRA_STATUS_V3')
            if state and 0<=g.clock()*1000-int(state['updated_ms'])<=4000 and state['state']!='OBSERVE':
                raise Blocked('Controlador anterior activo sin archivo de control; retira ese EA de MT5')
            continue
        try:
            raw=control.read_text(encoding='utf-8-sig').strip().split('|')
            if len(raw)!=37 or raw[0]!='AKIRA_NATIVE_V3' or raw[-1]!='END':raise Blocked('Controlador anterior con protocolo inesperado')
            if raw[2]!=str(snap.account.login) or raw[3]!=str(snap.account.server) or raw[4]!=symbol:raise Blocked('Controlador anterior de cuenta distinta')
            if raw[6]!='0' or raw[7]!='0':
                raw[5]=str(int(g.clock()*1000));raw[6]=raw[7]='0'
                temp=control.with_suffix('.retire.tmp')
                with temp.open('w',encoding='utf-8') as f:f.write('|'.join(raw)+'\n');f.flush();os.fsync(f.fileno())
                temp.replace(control)
        except OSError as e:raise Blocked('No se pudo pausar el controlador anterior: '+str(e))
        intent=g.journal.data['intents'].get(symbol)
        if intent and intent.get('native_id'):
            ack=unpack(folder/'ack.txt',ACK,'AKIRA_ACK_V3')
            if ack and ack['id']==str(intent['native_id']) and ack['session']==str(intent.get('native_session','')):
                code=int(ack['retcode'] or 0)
                if ack['state'] in ('BLOCKED','EXPIRED','REJECTED','NOT_SENT') or code in REJECTED:
                    g.journal.data['intents'].pop(symbol,None)
                else:intent.update(order=int(ack['order'] or 0),deal=int(ack['deal'] or 0),retcode=code)
                g.journal.save()
        state=unpack(folder/'status.txt',STATUS,'AKIRA_STATUS_V3')
        if state and 0<=g.clock()*1000-int(state['updated_ms'])<=4000:
            if state['state']!='OBSERVE' or int(state['busy']) or int(state['closing']):raise Blocked('Esperando pausa confirmada del controlador anterior de '+symbol)
