"""Hand-drawn monochrome bitmap tools matching the existing 20px grid."""
from pathlib import Path
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import Qt
root=Path(__file__).resolve().parents[1]/'packstudio/assets'
patterns={
'picker':[
'           ++    ',
'          +##+   ',
'         +####+  ',
'        +####+   ',
'       ++###+    ',
'      +#++++     ',
'     +#++        ',
'    +#++         ',
'   +#++          ',
'  +#++           ',
' +#++            ',
' +++             ',
'++               '],
 'eraser':[
'        +++++    ',
'       +#####+   ',
'      +#######+  ',
'     +#########+ ',
'    +#########+  ',
'   +#########+   ',
'  ++++######+    ',
' +....+####+     ',
'+......+##+      ',
' +......++       ',
'  +....+         ',
'   ++++          '],
}
palette={'+':'#aaaaaa','#':'#cccccc','.':'#777777'}
def pixels(rows):return {(x,y):palette[c] for y,row in enumerate(rows) for x,c in enumerate(row) if c in palette}
def star(p,x,y):
 for dx,dy in ((0,-2),(0,-1),(0,0),(0,1),(0,2),(-2,0),(-1,0),(1,0),(2,0)):p[x+dx,y+dy]='#cccccc'
icons={k:pixels(v) for k,v in patterns.items()}
p=dict(icons['eraser']);star(p,16,1);icons['magic_eraser']=p
p={}
for x in range(2,17):p[x,1]=p[x,12]='#aaaaaa'
for y in range(1,13):p[2,y]=p[16,y]='#aaaaaa'
for x in range(7,12):p[x,15]='#aaaaaa'
p[9,13]=p[9,14]='#aaaaaa'
for (x,y),c in icons['picker'].items():
 if x<10 and y>4:p[x+7,y-1]=c
icons['screen_picker']=p
p={}
for i in range(2,17):
 if i%5<3:p[i,2]=p[i,16]=p[2,i]=p[16,i]='#aaaaaa'
for y in range(7,13):
 for x in range(5,11):
  if (x+y)%3:p[x,y]='#777777'
star(p,13,6);icons['magic_select']=p
for name,p in icons.items():
 left=min(x for x,y in p);top=min(y for x,y in p);w=max(x for x,y in p)-left+1;h=max(y for x,y in p)-top+1
 assert max(w,h)<=20
 image=QImage(20,20,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
 for (x,y),c in p.items():image.setPixelColor((20-w)//2+x-left,(20-h)//2+y-top,QColor(c))
 for size in (20,30,40,60):assert image.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation).save(str(root/f'tool-{name}-{size}.png'))
print('Generated five icon families')
