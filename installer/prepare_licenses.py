"""Collect the notices of the exact Python distributions used by this build."""
from importlib import metadata
from pathlib import Path
import argparse,json,subprocess

PACKAGES=('PySide6','PySide6-Essentials','PySide6-Addons','shiboken6','onnxruntime','tokenizers','imageio-ffmpeg','Pillow','numpy','psutil')

def prepare(dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);report={}
    for name in PACKAGES:
        distribution=metadata.distribution(name);saved=[]
        for file in distribution.files or []:
            relative=Path(str(file))
            if any(word in relative.name.lower() for word in ('license','copying','notice')) and '.dist-info' in str(relative):
                target=dest/name/relative.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(distribution.locate_file(file)).read_bytes());saved.append(str(target.relative_to(dest)))
        report[name]={'version':distribution.version,'notices':saved,'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License') or 'See accompanying notices'}
    import imageio_ffmpeg
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-L'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,check=True)
    (dest/'FFMPEG_LICENSE_AND_BUILD.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    (dest/'INSTALLED_LICENSES.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dest',type=Path,required=True);args=parser.parse_args();prepare(args.dest)
