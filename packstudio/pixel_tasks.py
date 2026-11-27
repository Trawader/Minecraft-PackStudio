"""Cancelable, snapshot-only pixel operations; callers commit once on success."""
from collections import deque
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage,QColor,QRegion


def tick(cancel,progress,done,total):
    if cancel is not None and cancel.is_set():raise InterruptedError('已取消')
    if progress:progress(done,max(1,total))


def execute(parent,title,image,work):
    if image.width()*image.height()<=65536:return work(None,None)
    from .task_progress import run_progress
    return run_progress(parent,title,work)


def fill(image,point,allowed,target,weights=None,cancel=None,progress=None):
    result=QImage(image);width,height=image.width(),image.height();weights=weights or {}
    if not allowed.contains(QPoint(*point)):return result
    old=image.pixelColor(*point).rgba()
    if old==target.rgba() or not image.pixelColor(*point).alpha() and not target.alpha():return result
    visited=bytearray(width*height);seed=point[1]*width+point[0];queue=deque([seed]);visited[seed]=1;count=0
    while queue:
        i=queue.popleft();x,y=i%width,i//width;count+=1
        if count%1024==1:tick(cancel,progress,count,width*height)
        if not allowed.contains(QPoint(x,y)) or image.pixelColor(x,y).rgba()!=old:continue
        color=target;weight=weights.get((x,y),255)/255
        if weight<1:
            before=image.pixelColor(x,y);alpha=before.alphaF()*(1-weight)+target.alphaF()*weight
            rgb=[round((a*before.alphaF()*(1-weight)+b*target.alphaF()*weight)/alpha) if alpha else 0 for a,b in zip(before.getRgb()[:3],target.getRgb()[:3])]
            color=QColor(*rgb,round(alpha*255))
        result.setPixelColor(x,y,color)
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=nx<width and 0<=ny<height:
                n=ny*width+nx
                if not visited[n]:visited[n]=1;queue.append(n)
    tick(cancel,progress,width*height,width*height);return result


def opaque(image,allowed,cancel=None,progress=None):
    image=image.convertToFormat(QImage.Format.Format_RGBA8888);data=image.constBits();stride=image.bytesPerLine()
    bounds=allowed.boundingRect().intersected(image.rect());region=QRegion()
    for row,y in enumerate(range(bounds.top(),bounds.bottom()+1)):
        tick(cancel,progress,row,bounds.height());x=bounds.left()
        while x<=bounds.right():
            if not data[y*stride+x*4+3]:x+=1;continue
            start=x
            while x<=bounds.right() and data[y*stride+x*4+3]:x+=1
            region=region.united(QRegion(start,y,x-start,1))
    tick(cancel,progress,1,1);return region.intersected(allowed)


def background(image,allowed,cancel=None,progress=None):
    width,height=image.width(),image.height();valid=bytearray(width*height);edges=bytearray(width*height)
    bounds=allowed.boundingRect().intersected(image.rect());rows=max(1,bounds.height());total=rows*4
    for row,y in enumerate(range(bounds.top(),bounds.bottom()+1)):
        tick(cancel,progress,row,total)
        for x in range(bounds.left(),bounds.right()+1):
            if allowed.contains(QPoint(x,y)) and image.pixelColor(x,y).alpha():valid[y*width+x]=1
    for row,y in enumerate(range(bounds.top(),bounds.bottom()+1)):
        tick(cancel,progress,rows+row,total)
        for x in range(bounds.left(),bounds.right()+1):
            i=y*width+x
            if not valid[i]:continue
            color=image.pixelColor(x,y).getRgb()
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if not 0<=nx<width or not 0<=ny<height or not valid[ny*width+nx] or max(abs(a-b) for a,b in zip(color,image.pixelColor(nx,ny).getRgb()))>=22:
                    edges[i]=1;break
    protected=bytearray(edges)
    for row,y in enumerate(range(bounds.top(),bounds.bottom()+1)):
        tick(cancel,progress,2*rows+row,total)
        for x in range(bounds.left(),bounds.right()+1):
            if edges[y*width+x]:
                for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                    if 0<=nx<width and 0<=ny<height:protected[ny*width+nx]=1
    region=QRegion()
    for row,y in enumerate(range(bounds.top(),bounds.bottom()+1)):
        tick(cancel,progress,3*rows+row,total);x=bounds.left()
        while x<=bounds.right():
            if not valid[y*width+x] or protected[y*width+x]:x+=1;continue
            start=x
            while x<=bounds.right() and valid[y*width+x] and not protected[y*width+x]:x+=1
            region=region.united(QRegion(start,y,x-start,1))
    tick(cancel,progress,total,total);return region


def fill_selection(image,allowed,target,weights=None,cancel=None,progress=None):
    """Replace every selected pixel, including disconnected islands and transparency."""
    tick(cancel,progress,0,1)
    converted=image.convertToFormat(QImage.Format.Format_RGBA8888)
    data=bytearray(converted.constBits());stride=converted.bytesPerLine();pixel=bytes(target.getRgb())
    for rect in allowed.intersected(QRegion(image.rect())):
        row=pixel*rect.width()
        for y in range(rect.top(),rect.bottom()+1):
            if y%64==0:tick(cancel,progress,0,1)
            start=y*stride+rect.left()*4;data[start:start+len(row)]=row
    result=QImage(data,image.width(),image.height(),stride,QImage.Format.Format_RGBA8888).copy()
    for index,(point,value) in enumerate((weights or {}).items()):
        if index%1024==0:tick(cancel,progress,0,1)
        if not image.rect().contains(QPoint(*point)) or not allowed.contains(QPoint(*point)):continue
        weight=value/255;before=image.pixelColor(*point)
        alpha=before.alphaF()*(1-weight)+target.alphaF()*weight
        rgb=[round((a*before.alphaF()*(1-weight)+b*target.alphaF()*weight)/alpha) if alpha else 0 for a,b in zip(before.getRgb()[:3],target.getRgb()[:3])]
        result.setPixelColor(*point,QColor(*rgb,round(alpha*255)))
    tick(cancel,progress,1,1);return result
