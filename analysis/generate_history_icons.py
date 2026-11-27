"""Author history PNGs from explicit pixel runs, without vector paths/arcs."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor

ROOT=Path(__file__).resolve().parents[1]
rows={3:[(8,9)],4:[(7,8)],5:[(6,7)],6:[(5,6)],7:[(4,15)],8:[(3,18)],
      9:[(4,6),(15,19)],10:[(5,7),(18,20)],11:[(6,8),(19,21)],
      12:[(7,9),(20,21)],13:[(8,9),(20,21)],14:[(20,21)],15:[(20,21)],
      16:[(19,21)],17:[(18,20)],18:[(16,19)],19:[(13,17)],20:[(10,14)]}
image=QImage(24,24,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
reverse=QImage(image)
for y,runs in rows.items():
    for first,last in runs:
        for x in range(first,last+1):
            image.setPixelColor(x,y,QColor('#cccccc'));reverse.setPixelColor(23-x,y,QColor('#cccccc'))
for name,bitmap in [('undo',image),('redo',reverse)]:
    for scale in (1,2,3):
        target=ROOT/'packstudio/assets'/f'{name}-{24*scale}.png'
        assert bitmap.scaled(24*scale,24*scale,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation).save(str(target))
