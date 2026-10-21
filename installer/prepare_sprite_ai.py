"""Download immutable, integrity-checked local visual components for Windows CI."""
from pathlib import Path
from urllib.request import Request,urlopen
import argparse,hashlib,json

REVISION='6ef1ebc8b0766a7a8d11b146462c99cdf74dd22d'
BASE='https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/'+REVISION+'/'
FILES={
 'vision_model_quantized.onnx':('onnx/vision_model_quantized.onnx','583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299'),
 'text_model_quantized.onnx':('onnx/text_model_quantized.onnx','73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a'),
 'tokenizer.json':('tokenizer.json',None),
}

def prepare(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);report={}
    for name,(relative,expected) in FILES.items():
        target=folder/name;temporary=target.with_suffix('.part')
        try:
            request=Request(BASE+relative,headers={'User-Agent':'AKIRA-Studio-Build'})
            digest=hashlib.sha256();size=0
            with urlopen(request,timeout=90) as response,temporary.open('wb') as out:
                for chunk in iter(lambda:response.read(1024*1024),b''):
                    size+=len(chunk)
                    if size>400*1024*1024:raise ValueError('Componente visual demasiado grande')
                    out.write(chunk);digest.update(chunk)
            sha=digest.hexdigest()
            if expected and sha!=expected:raise ValueError('SHA256 incorrecto: '+name)
            if name=='tokenizer.json':
                data=json.loads(temporary.read_text(encoding='utf-8'))
                if (data.get('model') or {}).get('type')!='BPE':raise ValueError('Tokenizador visual no compatible')
            temporary.replace(target);report[name]={'sha256':sha,'bytes':size,'revision':REVISION}
        finally:temporary.unlink(missing_ok=True)
    (folder/'COMPONENTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dest',type=Path,required=True);args=parser.parse_args();print(json.dumps(prepare(args.dest),indent=2))
