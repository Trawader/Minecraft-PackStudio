"""Read-only audit: distinguish transparent unused space from occupied unmapped pixels."""
import os,sys,json
from pathlib import Path
from collections import deque
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor
from packstudio.core import Vanilla,decode,pixel_rect,ROOT
from packstudio.semantics import parts,variant_id
from packstudio.versions import VERSIONS,records
app=QApplication([]);vanilla=Vanilla();rows=[];tiles=[]
for version in VERSIONS:
 for path in ['assets/minecraft/textures/gui/icons.png','assets/minecraft/textures/particle/particles.png']:
  raw=vanilla.get(version,path)
  if not raw:continue
  im=decode(raw);covered=set()
  for part in parts(path,version):
   for r in part['regions']:
    x,y,w,h=pixel_rect(r,im);covered.update((X,Y) for X in range(x,x+w) for Y in range(y,y+h))
  remaining={(x,y) for y in range(im.height()) for x in range(im.width()) if im.pixelColor(x,y).alpha() and (x,y) not in covered}
  boxes=[]
  while remaining:
   seed=remaining.pop();todo=[seed];component=[seed]
   while todo:
    x,y=todo.pop()
    for pt in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
     if pt in remaining:remaining.remove(pt);todo.append(pt);component.append(pt)
   x=min(p[0] for p in component);y=min(p[1] for p in component);w=max(p[0] for p in component)-x+1;h=max(p[1] for p in component)-y+1
   boxes.append([x,y,w,h])
  rows.append({'version':version,'path':path,'unmapped_opaque_boxes':sorted(boxes),'known_parts':len(parts(path,version))})
  tiles.append((version+' '+Path(path).name,im,covered))
entities=[]
for old,new in zip(VERSIONS,VERSIONS[1:]):
 for path,a in records(old).items():
  b=records(new).get(path)
  if '/textures/entity/' not in path or not path.endswith('.png') or not b:continue
  if a['sha256']!=b['sha256']:entities.append({'source':old,'target':new,'path':path,'source_size':a.get('size'),'target_size':b.get('size'),'layout_changes':variant_id(path,old)!=variant_id(path,new)})
output=ROOT/'analysis'/'unmapped-assets.json';output.write_text(json.dumps({'atlases':rows,'entity_changes':entities},ensure_ascii=False,indent=2),'utf8')
sheet=QImage(4*280,((len(tiles)+3)//4)*290,QImage.Format.Format_ARGB32);sheet.fill(QColor('#303030'));p=QPainter(sheet)
for i,(label,im,covered) in enumerate(tiles):
 x=(i%4)*280;y=(i//4)*290;p.setPen(QColor('white'));p.drawText(x+4,y+18,label)
 view=im.copy()
 for X,Y in covered:view.setPixelColor(X,Y,QColor(0,0,0,0))
 p.drawImage(x+4,y+28,view.scaled(256,256))
p.end();sheet.save(str(ROOT/'.tmp/unmapped-atlases.png'))
print('Audited',len(rows),'atlases;',sum(bool(r['unmapped_opaque_boxes']) for r in rows),'with occupied unmatched pixels;',len(entities),'entity artwork changes')
for r in rows:
 if r['version'] in ('1.8.9','1.13.2','1.20.1'):print(r['version'],Path(r['path']).name,r['unmapped_opaque_boxes'])
