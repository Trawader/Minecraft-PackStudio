import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor,QPainter,QImage
from packstudio.core import Layer,Vanilla,decode,png
from packstudio.layouts import confirm_layout,inspect_atlases
from packstudio.adaptation import export_composition
from packstudio.export_priority import visible_files,missing_atlases
app=QApplication([]);v=Vanilla();icons='assets/minecraft/textures/gui/icons.png'
raw=v.get('1.8.9',icons);c=decode(raw)
p=QPainter(c);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(52,0,9,9,QColor(0,0,0,0));p.end()
def pack(name,im):
 layer=Layer(name,{icons:png(im)},source_version='1.8.9');confirm_layout(layer,icons,'1.8.9');return layer
red=decode(raw);red.fill(QColor('red'));green=decode(raw);green.fill(QColor('green'))
C,D,E=pack('c',c),pack('d',red),pack('e',green)
def cross(name,color):
 im=QImage(30,30,QImage.Format.Format_ARGB32);im.fill(QColor(color))
 return Layer(name,{'0':png(im)},'component',icons,[(0,0,15/256,15/256)],source_version='1.8.9')
A,B=cross('a','yellow'),cross('b','blue');layers=[A,B,C,D,E]
assert [l.name for l in visible_files(layers)]==['a','b','c']
assert missing_atlases(layers,'1.8.9','1.8.9')
for target in ['1.8.9','1.21.11']:
 for mode in ['vanilla','lower','keep']:
  result,_=export_composition(layers,v,target,'1.8.9',mode)
  if target=='1.8.9':
   im=decode(result[icons]);s=im.width()/256;heart=im.copy(round(52*s),0,round(9*s),round(9*s));aim=im.pixelColor(1,1)
  else:heart=decode(result['assets/minecraft/textures/gui/sprites/hud/heart/full.png']);aim=decode(result['assets/minecraft/textures/gui/sprites/hud/crosshair.png']).pixelColor(1,1)
  assert aim==QColor('yellow'),(target,mode,'priority')
  if mode=='lower':assert heart.pixelColor(1,1)==QColor('red'),(target,mode)
  elif mode=='keep':assert not any(heart.pixelColor(x,y).alpha() for y in range(heart.height()) for x in range(heart.width())),(target,mode)
  else:assert any(heart.pixelColor(x,y).alpha() for y in range(heart.height()) for x in range(heart.width())),(target,mode)
 assert decode(result[icons]).width()==512 if target=='1.8.9' else True
# A mere painting edit retains the confirmed layout tag.
C.files[icons]=png(red);assert inspect_atlases(C)[0]['chosen']=='1.8.9'
from packstudio.semantics import parts
atlas='assets/minecraft/textures/particle/particles.png'
assert len([p for p in parts(atlas,'1.13.2') if 'bubble_pop_' in p['code']])==5
assert not any('bubble_pop_' in p['code'] for p in parts(atlas,'1.8.9'))
particle=Layer('particles',{atlas:v.get('1.13.2',atlas)},source_version='1.13.2')
result,_=export_composition([particle],v,'1.16.5','1.13.2','keep')
assert all('assets/minecraft/textures/particle/bubble_pop_'+str(i)+'.png' in result for i in range(5))
assert 'assets/minecraft/textures/entity/fishing_hook.png' in result
print('PASS a/b/c/d/e precedence; A vanilla, B lower, C transparent; atlas-to-sprites; high resolution; stable layout tags')
