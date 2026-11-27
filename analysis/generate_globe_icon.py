"""Rasterize a circular monochrome globe at native menu/DPI sizes."""
from math import hypot,sqrt
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
assets=Path(__file__).resolve().parents[1]/'packstudio/assets'
for size in (16,24,32,48):
    image=QImage(size,size,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    for y in range(size):
        for x in range(size):
            coverage=0
            for sy in range(4):
                for sx in range(4):
                    dx=(x+(sx+.5)/4)*16/size-8;dy=(y+(sy+.5)/4)*16/size-8
                    radius=hypot(dx,dy);a,b=3.1,6.5
                    gradient=hypot(2*dx/a**2,2*dy/b**2)
                    meridian=abs((dx/a)**2+(dy/b)**2-1)/gradient if gradient else 99
                    if abs(radius-6.5)<=.5 or radius<=6.5 and (abs(dy)<=.45 or meridian<=.45):coverage+=1
            if coverage:image.setPixelColor(x,y,QColor(204,204,204,round(255*coverage/16)))
    assert image.save(str(assets/f'globe-{size}.png'))
