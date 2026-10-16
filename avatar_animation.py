"""Small shared state atlas; runtime loading rings use Canvas primitives."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=2)
def _atlas(path,stamp):
    from PIL import Image
    with Image.open(path) as source:return source.convert('RGBA')


class StateSprites:
    def __init__(self,root):
        folder=Path(root)/'assets/avatar_states'
        data=json.loads((folder/'states.json').read_text(encoding='utf-8'))
        if data.get('schema')!=1 or data.get('grid')!=[4,2]:raise ValueError('Atlas de animación incompatible')
        self.path=folder/data['atlas'];self.stamp=self.path.stat().st_mtime_ns

    def image(self,index,width,height):
        from PIL import Image
        source=_atlas(str(self.path),self.stamp);sw,sh=source.size
        column,row=int(index)%4,int(index)//4
        cell=source.crop((round(column*sw/4),round(row*sh/2),round((column+1)*sw/4),round((row+1)*sh/2)))
        ratio=min(width*.94/cell.width,height*.94/cell.height)
        size=(max(1,round(cell.width*ratio)),max(1,round(cell.height*ratio)))
        resized=cell.convert('RGBa').resize(size,Image.Resampling.NEAREST).convert('RGBA')
        canvas=Image.new('RGBA',(max(1,width),max(1,height)))
        canvas.paste(resized,((width-size[0])//2,(height-size[1])//2))
        return canvas
