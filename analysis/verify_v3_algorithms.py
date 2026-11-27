"""Additional V3 algorithm boundaries; no external resource packs required."""
import sys,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtGui import QImage,QColor
from packstudio.part_derivation import transfer,rgba,luminance
from packstudio.texture_animation import timeline
from packstudio.resource_graph import ResourceGraph
from packstudio.sky_view import thumbnail,render,oversized
from packstudio.core import png,safe_path
im=QImage(4,1,QImage.Format.Format_ARGB32)
for x,c in enumerate(['#302010','#205080','#80a0c0','#ffffff']):im.setPixelColor(x,0,QColor(c))
im.setPixelColor(2,0,QColor(128,160,192,97))
target=QImage(2,1,QImage.Format.Format_ARGB32);target.setPixelColor(0,0,QColor('#604000'));target.setPixelColor(1,0,QColor('#ffe080'))
changed=transfer(im,[0,1,1,0],target,[1,1]);a,b=rgba(im),rgba(changed)
assert a[:4]==b[:4] and a[12:]==b[12:] and a[3::4]==b[3::4]
assert luminance(*b[4:7])<luminance(*b[8:11]) and rgba(transfer(im,[0,1,1,0],target,[1,1],0))==a
frames,interp=timeline(b'{"animation":{"frames":[1,{"index":0,"time":3}],"interpolate":true}}',16,32)
assert frames==[(1,(0,16,16,16),1),(0,(0,0,16,16),3)] and interp
for bad in [{'frames':[2]},{'frametime':True},{'frames':[{'index':0,'time':0}]},{'width':3}]:
 try:timeline(json.dumps({'animation':bad}).encode(),16,32)
 except ValueError:pass
 else:raise AssertionError(bad)
base='assets/minecraft/'
files={base+'blockstates/demo.json':b'{"variants":{"normal":{"model":"demo"}}}',base+'models/block/demo.json':b'{"textures":{"all":"blocks/demo"}}',base+'textures/blocks/demo.png':png(im)}
g=ResourceGraph(files).parse();selected,missing=g.closure([base+'blockstates/demo.json'],include_callers=False)
assert selected==set(files) and not missing
sky=QImage(60,40,QImage.Format.Format_ARGB32);sky.fill(QColor('cyan'))
assert thumbnail(png(sky),24).width()==24
assert not render(sky,'cube',0,0,1,80,60).isNull()
header=b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',20000,1);assert oversized(header)
try:thumbnail(header[:16]+struct.pack('>II',20000,20000))
except ValueError:pass
else:raise AssertionError('Huge image should reject before decode')
for unsafe in ('../x.png','C:/x.png','/x.png','a/../../x.png'):
 try:safe_path(unsafe)
 except ValueError:pass
 else:raise AssertionError(unsafe)
print('PASS material mask/alpha/luminance, animation bounds, legacy model closure, sky projection/limits, archive path safety')
