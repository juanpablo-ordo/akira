"""Explicit, hash-verified recovery of the bundled AI. Custom files stay intact."""
from pathlib import Path,PurePosixPath
import hashlib,os,time,zipfile,tempfile,shutil
from urllib.request import Request
from network_tls import urlopen
from bundled_model import MODEL_NAME,MODEL_SHA,MODEL_SIZE,MODEL_URL
CPU_SHA='5488e6232c6114d81302adc616d6c7470a8c06e24140e1baf1d0a85e3b731adc'
CPU_URL='https://github.com/ggml-org/llama.cpp/releases/download/b10355/llama-b10355-bin-win-cpu-x64.zip'
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def download_verified(url,path,sha,limit,cancel=None,progress=lambda text:None,opener=urlopen,deadline=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);part=path.with_name(path.name+'.repair.part');part.unlink(missing_ok=True);h=hashlib.sha256();size=0;last=0;deadline=deadline or time.monotonic()+900
    try:
        with opener(Request(url,headers={'User-Agent':'AKIRA/16.4.2 Repair'}),timeout=30) as response,part.open('wb') as f:
            for b in iter(lambda:response.read(2*1024*1024),b''):
                if cancel is not None and cancel.is_set():raise RuntimeError('Reparación cancelada')
                if time.monotonic()>deadline:raise TimeoutError('La descarga no terminó a tiempo; vuelve a intentarlo')
                size+=len(b)
                if size>limit:raise ValueError('El componente excede el tamaño autorizado')
                h.update(b);f.write(b)
                if time.monotonic()-last>1:progress('Descargando componente verificado: '+str(round(size/1048576))+' MB');last=time.monotonic()
            f.flush();os.fsync(f.fileno())
        if h.hexdigest()!=sha:raise ValueError('La descarga no pasó su comprobación de integridad. Se conserva el archivo anterior.')
        if cancel is not None and cancel.is_set():raise RuntimeError('Reparación cancelada')
        part.replace(path);return path
    finally:part.unlink(missing_ok=True)
def extract_cpu(archive,target,cancel=None):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='AKIRA_CPU_',dir=target.parent) as temp:
        stage=Path(temp);names=set();size=0
        with zipfile.ZipFile(archive) as z:
            for e in z.infolist():
                name=PurePosixPath(e.filename.replace('\\','/'))
                if name.is_absolute() or '..' in name.parts or ':' in str(name) or (e.external_attr>>16)&0o170000==0o120000:raise ValueError('Ruta no permitida en el componente')
                if e.is_dir() or name.suffix.lower() not in ('.dll','.exe','.txt','.md'):continue
                if name.name.casefold() in names:raise ValueError('Nombre duplicado en el componente')
                names.add(name.name.casefold());size+=e.file_size
                if size>600*1024*1024:raise ValueError('Componente demasiado grande')
                if cancel is not None and cancel.is_set():raise RuntimeError('Reparación cancelada')
                with z.open(e) as src,(stage/name.name).open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
        if not (stage/'llama-server.exe').is_file():raise ValueError('Falta llama-server.exe en el componente')
        target.mkdir(parents=True,exist_ok=True)
        for src in sorted(stage.iterdir(),key=lambda p:p.name=='llama-server.exe'):
            part=target/(src.name+'.repair.part')
            try:shutil.copyfile(src,part);part.replace(target/src.name)
            finally:part.unlink(missing_ok=True)
def recover_bundled(app_dir,cancel=None,progress=lambda text:None,force_cpu=False):
    root=Path(app_dir);model=root/'local_ai/models'/MODEL_NAME;cpu=root/'local_ai/cpu';deadline=time.monotonic()+900;changed=[];progress('Comprobando los archivos de la IA incluida…')
    if not model.is_file() or model.stat().st_size!=MODEL_SIZE or digest(model)!=MODEL_SHA:download_verified(MODEL_URL,model,MODEL_SHA,MODEL_SIZE,cancel,progress,deadline=deadline);changed.append('modelo')
    if force_cpu or not (cpu/'llama-server.exe').is_file():
        with tempfile.TemporaryDirectory(prefix='AKIRA_REPAIR_') as temp:
            archive=download_verified(CPU_URL,Path(temp)/'cpu.zip',CPU_SHA,200*1024*1024,cancel,progress,deadline=deadline);extract_cpu(archive,cpu,cancel);changed.append('motor CPU')
    progress('Archivos comprobados. Probando una respuesta visible…');return changed
