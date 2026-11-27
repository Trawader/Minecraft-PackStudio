"""Selection-local tonal mapping. No file IO and no source mutation."""
import colorsys
from dataclasses import dataclass
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage,QColor,QRegion
from .smart_regions import analyze
from .gradient_transition import transition_value


@dataclass
class Settings:
    mode: str='middle'
    first: str='#AA96F8'
    last: str='#eee6ff'
    direction: str='down'
    smooth: int=100
    saturation: int=0
    contrast: int=0
    brightness: int=0
    opacity: int=100
    color_kind: str='balance'
    red: int=0
    green: int=0
    blue: int=0
    color_band: int=0
    hue_shift: int=0
    band_saturation: int=0
    band_lightness: int=0
    start: tuple | None=None
    end: tuple | None=None
    midpoint: int=50
    transition: str='linear'
    steps: int=8
    curve: tuple=((0.,0.),(1.,1.))


def points(image,region):
    bounds=region.boundingRect().intersected(image.rect())
    for y in range(bounds.top(),bounds.bottom()+1):
        for x in range(bounds.left(),bounds.right()+1):
            if region.contains(QPoint(x,y)) and image.pixelColor(x,y).alpha():yield x,y


def anchor_level(colors,mode):
    values=sorted(set(round(colorsys.rgb_to_hls(*rgb)[1]*255) for rgb in colors))
    groups=[]
    for value in values:
        if groups and value-groups[-1][0]<=2:groups[-1].append(value)
        else:groups.append([value])
    levels=[sum(g)/len(g)/255 for g in groups]
    if not levels:return .5,0,1
    if mode=='average':
        average=tuple(sum(c[i] for c in colors)/len(colors) for i in range(3))
        anchor=colorsys.rgb_to_hls(*average)[1]
    elif mode=='dark':anchor=levels[0]
    elif mode=='light':anchor=levels[-1]
    else:anchor=(levels[(len(levels)-1)//2]+levels[len(levels)//2])/2
    return anchor,levels[0],levels[-1]


def render(image,region,settings,weights=None,cancel=None,progress=None):
    from .core import IMAGE_PIXEL_LIMIT
    if image.width()*image.height()>IMAGE_PIXEL_LIMIT:raise ValueError('图片超出可编辑内存范围；原图未修改。')
    if settings.mode=='opacity' and not weights and region==QRegion(image.rect()):
        if cancel and cancel.is_set():raise InterruptedError('已取消，原图未修改。')
        if settings.opacity==100:
            if progress:progress(1,1)
            return QImage(image)
        # Work by scanline: bounded temporary storage, no per-pixel QColor calls.
        result=image.convertToFormat(QImage.Format.Format_RGBA8888)
        table=bytes(round(a*settings.opacity/100) for a in range(256))
        data=result.bits();stride=result.bytesPerLine();width=result.width()*4
        for y in range(result.height()):
            if cancel and cancel.is_set():raise InterruptedError('已取消，原图未修改。')
            alpha=data[y*stride+3:y*stride+width:4]
            alpha[:]=bytes(alpha).translate(table)
            if progress:progress(y+1,result.height())
        return result
    result=QImage(image);weights=weights or {}
    bounds=region.boundingRect().intersected(image.rect())
    rows=max(1,bounds.height());needs_anchor=settings.mode in ('middle','average','dark','light','range')
    total=rows*(2 if needs_anchor else 1)
    def report(row):
        if cancel and cancel.is_set():raise InterruptedError('已取消，原图未修改。')
        if progress:progress(row,total)
    # A compact histogram avoids millions of Python coordinate/color objects.
    anchor,low,high=.5,0,1
    if needs_anchor:
        levels=set();sums=[0.,0.,0.];count=0
        for y in range(bounds.top(),bounds.bottom()+1):
            report(y-bounds.top())
            for x in range(bounds.left(),bounds.right()+1):
                if not region.contains(QPoint(x,y)):continue
                c=image.pixelColor(x,y)
                if not c.alpha():continue
                rgb=c.getRgbF()[:3];levels.add(round(colorsys.rgb_to_hls(*rgb)[1]*255));count+=1
                for i in range(3):sums[i]+=rgb[i]
        groups=[]
        for value in sorted(levels):
            if groups and value-groups[-1][0]<=2:groups[-1].append(value)
            else:groups.append([value])
        levels=[sum(g)/len(g)/255 for g in groups]
        if levels:
            low,high=levels[0],levels[-1]
            anchor=(levels[(len(levels)-1)//2]+levels[len(levels)//2])/2
            if settings.mode=='average':anchor=colorsys.rgb_to_hls(*(v/count for v in sums))[1]
            elif settings.mode=='dark':anchor=low
            elif settings.mode=='light':anchor=high
    a=QColor(settings.first).getRgbF()[:3];b=QColor(settings.last).getRgbF()[:3]
    hue,target_light,sat=colorsys.rgb_to_hls(*a)
    bounds=region.boundingRect();clamp=lambda v:max(0.,min(1.,v))
    def pixels():
        clipped=bounds.intersected(image.rect())
        for y in range(clipped.top(),clipped.bottom()+1):
            report((rows if needs_anchor else 0)+y-clipped.top())
            for x in range(clipped.left(),clipped.right()+1):
                if region.contains(QPoint(x,y)) and image.pixelColor(x,y).alpha():yield x,y
    for x,y in pixels():
        rgb=image.pixelColor(x,y).getRgbF()[:3]
        h,l,s=colorsys.rgb_to_hls(*rgb);original=image.pixelColor(x,y)
        if settings.mode in ('middle','average','dark','light'):
            light=target_light*l/anchor if l<=anchor and anchor>0 else target_light+(1-target_light)*(l-anchor)/(1-anchor) if anchor<1 else target_light
            mapped=colorsys.hls_to_rgb(hue,clamp(light),sat)
        elif settings.mode in ('range','spatial'):
            if settings.mode=='range':t=(l-low)/(high-low) if high>low else .5
            else:
                u=(x-bounds.left())/max(1,bounds.width()-1);v=(y-bounds.top())/max(1,bounds.height()-1)
                if settings.start is not None and settings.end is not None:
                    sx,sy=settings.start;ex,ey=settings.end;dx,dy=ex-sx,ey-sy
                    t=((x-sx)*dx+(y-sy)*dy)/(dx*dx+dy*dy) if dx or dy else 0
                else:t={'down':v,'up':1-v,'right':u,'left':1-u,'diagonal':(u+v)/2,'reverse_diagonal':(1-u+v)/2}[settings.direction]
                t=transition_value(t,settings.midpoint,settings.smooth,settings.transition,settings.steps,settings.curve)
            mapped=tuple(a[i]*(1-clamp(t))+b[i]*clamp(t) for i in range(3))
        elif settings.mode=='color':
            if settings.color_kind=='balance':
                mapped=tuple(clamp(v+amount/100*(1-v if amount>=0 else v)) for v,amount in zip(rgb,(settings.red,settings.green,settings.blue)))
            else:
                # Circular, feathered hue bands; neutral pixels are unaffected.
                distance=abs((h-settings.color_band/6+.5)%1-.5)*360
                weight=max(0.,min(1.,(60-distance)/30))*min(1.,s*4)
                mapped=colorsys.hls_to_rgb((h+settings.hue_shift/360*weight)%1,
                    clamp(l+settings.band_lightness/100*weight),clamp(s*(1+settings.band_saturation/100*weight)))
        else:mapped=rgb
        if settings.mode!='opacity':
            mh,ml,ms=colorsys.rgb_to_hls(*mapped)
            ml=clamp((ml-.5)*(1+settings.contrast/100)+.5+settings.brightness/100)
            ms=clamp(ms*(1+settings.saturation/100))
            mapped=colorsys.hls_to_rgb(mh,ml,ms)
        coverage=weights.get((x,y),255)/255
        out=QColor.fromRgbF(*(clamp(rgb[i]+(mapped[i]-rgb[i])*coverage) for i in range(3)))
        alpha=original.alpha()
        if settings.mode=='opacity':alpha=round(alpha*(1-coverage+coverage*settings.opacity/100))
        out.setAlpha(alpha);result.setPixelColor(x,y,out)
    report(total)
    return result


def gui_background(image,region,cancel=None,progress=None):
    from .pixel_tasks import background
    return background(image,region,cancel,progress)


def signature(image,region):
    colors=[image.pixelColor(x,y).getRgbF()[:3] for x,y in points(image,region)]
    if not colors:return None
    # Saturation/chromaticity descriptors do not depend on the region's position.
    mean=tuple(sum(c[i] for c in colors)/len(colors) for i in range(3))
    return colorsys.rgb_to_hls(*mean)


def match_region(image,reference):
    candidates=analyze(image)
    if reference is None:return QRegion(),False
    ranked=[]
    for candidate in candidates:
        feature=signature(image,candidate.region)
        if feature is None:continue
        h,l,s=feature;rh,rl,rs=reference
        hue=min(abs(h-rh),1-abs(h-rh)) if min(s,rs)>.12 else 0
        distance=hue*2+abs(s-rs)*.55+abs(l-rl)*.2
        ranked.append((distance,-candidate.count,candidate.region))
    ranked.sort(key=lambda value:value[:2])
    if not ranked:return QRegion(),False
    # Close alternatives or a different material are explicitly marked unsure.
    confident=ranked[0][0]<.22 and (len(ranked)==1 or ranked[1][0]-ranked[0][0]>.035)
    return QRegion(ranked[0][2]),confident
