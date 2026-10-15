"""Windows Actions smoke: verify official GGUF and demand an ACTUAL chat reply.

This is a CI-only validator; no account or MT5 login is used.
"""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from urllib.request import Request,urlopen

URL='https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf'
SHA='7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def get_model(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and sha256(path)==SHA:return path
    partial=path.with_suffix('.partial')
    partial.unlink(missing_ok=True)
    try:
        with urlopen(Request(URL,headers={'User-Agent':'AKIRA-CI/16.3.2'}),timeout=90) as r, partial.open('wb') as out:
            for chunk in iter(lambda:r.read(2*1024*1024),b''):out.write(chunk)
        if sha256(partial)!=SHA:raise ValueError('SHA256 incorrecto del GGUF oficial')
        partial.replace(path)
        return path
    finally:
        partial.unlink(missing_ok=True)

def smoke(exe,model):
    exe=Path(exe);model=Path(model)
    if not (exe.is_file() and model.is_file()):raise FileNotFoundError('Falta motor CPU o GGUF')
    cmd=[str(exe),'--model',str(model),'--host','127.0.0.1','--port','18988',
         '--ctx-size','1024','--n-gpu-layers','0','--threads','3','--parallel','1']
    with open(os.devnull,'wb') as sink:
        proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=sink,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+170
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('llama-server.exe finalizó antes de estar listo')
                try:
                    with urlopen('http://127.0.0.1:18988/health',timeout=2) as r:
                        if r.status==200:break
                except Exception:pass
                time.sleep(1)
            else:raise TimeoutError('llama-server.exe no respondió en 170 segundos')
            payload={'model':'Qwen3-4B-Q4_K_M.gguf','messages':[{'role':'user','content':'Responde solo: hola'}],
                     'temperature':0,'max_tokens':24,'stream':False}
            req=Request('http://127.0.0.1:18988/v1/chat/completions',
                        data=json.dumps(payload).encode('utf-8'),
                        headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=120) as r:response=json.load(r)
            msg=str(((response.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
            if not msg:raise RuntimeError('El modelo no generó respuesta visible')
            print('AKIRA local AI smoke OK. tokens:',len(msg.split()))
        finally:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    args=parser.parse_args()
    path=get_model(args.model)
    smoke(args.exe,path)

if __name__=='__main__':main()
