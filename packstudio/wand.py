"""Local color-distance selection, returned in view coordinates without editing PNGs."""
from collections import deque
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage,QRegion


def select(image,point,valid_region,tolerance=32,contiguous=True,antialias=False,cancel=None,progress=None):
    from .pixel_tasks import tick
    image=image.convertToFormat(QImage.Format.Format_RGBA8888)
    width,height=image.width(),image.height();stride=image.bytesPerLine();data=image.constBits()
    x,y=point
    if not valid_region.contains(QPoint(x,y)):return QRegion(),{}
    def rgba(x,y):
        i=y*stride+x*4
        return tuple(data[i:i+4])
    seed=rgba(x,y)
    def matches(x,y):
        if not valid_region.contains(QPoint(x,y)):return False
        color=rgba(x,y)
        # Invisible RGB is irrelevant; alpha differences remain significant.
        distance=max(abs(color[3]-seed[3]),*(abs(color[i]*color[3]-seed[i]*seed[3])/255 for i in range(3)))
        return distance<=tolerance
    selected=bytearray(width*height)
    if contiguous:
        visited=bytearray(width*height);queue=deque([(x,y)]);visited[y*width+x]=1
        processed=0
        while queue:
            processed+=1
            if processed%1024==1:tick(cancel,progress,processed,width*height*2)
            x,y=queue.popleft()
            if not matches(x,y):continue
            selected[y*width+x]=1
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0<=nx<width and 0<=ny<height and not visited[ny*width+nx]:
                    visited[ny*width+nx]=1;queue.append((nx,ny))
    else:
        for y in range(height):
            tick(cancel,progress,y*width,width*height*2)
            for x in range(width):
                if matches(x,y):selected[y*width+x]=1
    region=QRegion();weights={}
    for y in range(height):
        tick(cancel,progress,width*height+y*width,width*height*2)
        x=0
        while x<width:
            if not selected[y*width+x]:x+=1;continue
            start=x
            while x<width and selected[y*width+x]:
                if antialias:
                    # Partial coverage only on selected edge pixels; never grow into
                    # unrelated colors or the padding between atlas components.
                    neighbors=[selected[ny*width+nx] for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)) if 0<=nx<width and 0<=ny<height and valid_region.contains(QPoint(nx,ny))]
                    if neighbors and not all(neighbors):weights[(x,y)]=round(255*(.5+.5*sum(neighbors)/len(neighbors)))
                x+=1
            region=region.united(QRegion(start,y,x-start,1))
    tick(cancel,progress,1,1)
    return region,weights
