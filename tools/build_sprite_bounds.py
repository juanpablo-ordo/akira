"""Measure alpha gutters; save crop metadata without altering the artwork."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def bounds(path, columns, rows):
    image = Image.open(path).convert('RGBA')
    alpha = image.getchannel('A')
    # Split at actual gutters, since generated atlases aren't exact grids.
    def gutter(values, nominal, radius):
        candidates = range(max(1, int(nominal-radius)), min(len(values)-1, int(nominal+radius)))
        return min(candidates, key=lambda n: (sum(values[max(0,n-1):n+2]), abs(n-nominal)))
    count_x = [sum(v>180 for v in alpha.crop((x,0,x+1,image.height)).getdata()) for x in range(image.width)]
    edges_x = [0]+[gutter(count_x, image.width*c/columns, image.width/columns*.15) for c in range(1,columns)]+[image.width]
    result=[]
    for row in range(rows):
        for column in range(columns):
            left,right=edges_x[column:column+2]
            strip=alpha.crop((left,0,right,image.height))
            count_y=[sum(v>180 for v in strip.crop((0,y,strip.width,y+1)).getdata()) for y in range(image.height)]
            ys=[0]+[gutter(count_y,image.height*r/rows,image.height/rows*.18) for r in range(1,rows)]+[image.height]
            top,bottom=ys[row:row+2]
            strong=alpha.crop((left,top,right,bottom)).point(lambda v:255 if v>180 else 0)
            # Main component excludes isolated artifacts and the next dog's tail.
            w,h=strong.size;pixels=bytearray(strong.tobytes());best=[]
            for start in range(w*h):
                if not pixels[start]:continue
                stack=[start];pixels[start]=0;component=[]
                while stack:
                    i=stack.pop();component.append(i);x,y=i%w,i//w
                    for j in ([i-1] if x else [])+([i+1] if x<w-1 else [])+([i-w] if y else [])+([i+w] if y<h-1 else []):
                        if pixels[j]:pixels[j]=0;stack.append(j)
                if len(component)>len(best):best=component
            if not best:raise ValueError('Empty sprite: '+str(path))
            xs=[i%w for i in best];ys2=[i//w for i in best]
            result.append([max(left,left+min(xs)-3),max(top,top+min(ys2)-3),min(right,left+max(xs)+4),min(bottom,top+max(ys2)+4)])
    return result


if __name__=='__main__':
    folder=ROOT/'assets/expressions';catalog=json.loads((folder/'catalog.json').read_text(encoding='utf-8'))
    measured={p.name:bounds(p,3,3) for p in folder.glob('akira_*.png')}
    for entry in catalog['expressions']:entry['bounds']=measured[entry['atlas']][entry['row']*3+entry['column']]
    catalog['revision']='STUDIO_REV7_108'
    (folder/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    folder=ROOT/'assets/avatar_states'
    (folder/'motion_bounds.json').write_text(json.dumps({'schema':1,'atlas':'akira_rev6_motion.png','bounds':bounds(folder/'akira_rev6_motion.png',4,4)},indent=2)+'\n',encoding='utf-8')
