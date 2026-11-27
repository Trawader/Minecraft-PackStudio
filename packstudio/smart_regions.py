"""Conservative local material candidates; these are suggestions, not semantic truth."""
from collections import deque
from dataclasses import dataclass
import colorsys
from PySide6.QtGui import QImage,QRegion


@dataclass
class Candidate:
    label: str
    region: QRegion
    highlights: QRegion
    count: int
    reason: str
    score: float


def region_from_pixels(pixels,width):
    rows={}
    for index in pixels:rows.setdefault(index//width,[]).append(index%width)
    result=QRegion()
    for y,xs in rows.items():
        xs.sort();start=previous=xs[0]
        for x in xs[1:]:
            if x!=previous+1:result=result.united(QRegion(start,y,previous-start+1,1));start=x
            previous=x
        result=result.united(QRegion(start,y,previous-start+1,1))
    return result


def analyze(image):
    """Return independently selectable, connected hue families in view coordinates."""
    width,height=image.width(),image.height()
    if width*height>512*512:raise ValueError('当前视图超过 512×512，请先切到单帧或使用手动选区。')
    if image.isNull():return []
    image=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=image.constBits();stride=image.bytesPerLine()
    pixels={};families={}
    for y in range(height):
        for x in range(width):
            off=y*stride+x*4;r,g,b,a=raw[off:off+4]
            # Some packs contain almost invisible, full-canvas residue. It must
            # not dominate material inference. Manual selection remains exact.
            if a<16:continue
            h,s,v=colorsys.rgb_to_hsv(r/255,g/255,b/255)
            index=y*width+x;pixels[index]=(h,s,v,a/255)
            # Near-white remains a neutral candidate; it is not discarded.
            family=12 if s<.16 else int((h*12+.5)%12)
            families.setdefault(family,set()).add(index)
    def neighbors(i):
        x,y=i%width,i//width
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)):
            if 0<=x+dx<width and 0<=y+dy<height:yield (y+dy)*width+x+dx
    # Adjacent hue bins belong to one family when the hue gap is small.
    groups=[];remaining=set(families)-{12}
    while remaining:
        root=max(remaining,key=lambda k:(len(families[k]),-k));remaining.remove(root)
        group=set(families[root])
        for k in ((root-1)%12,(root+1)%12):
            if k in remaining:group.update(families[k]);remaining.remove(k)
        groups.append((root,group))
    if 12 in families:groups.append((12,families[12]))
    labels=('红','橙','黄','黄绿','绿','青绿','青','蓝青','蓝','蓝紫','紫','粉')
    output=[]
    for family,group in groups:
        # Dark silhouette pixels are a separate, conservative exclusion. Dark
        # interiors remain, so the mask can carry material shadows.
        core={i for i in group if not (pixels[i][2]<.22 and
              (i%width in (0,width-1) or i//width in (0,height-1) or any(n not in pixels for n in neighbors(i))))}
        unseen=set(core);components=[]
        while unseen:
            seed=min(unseen);unseen.remove(seed);component={seed};queue=deque([seed])
            while queue:
                for n in neighbors(queue.popleft()):
                    if n in unseen:unseen.remove(n);component.add(n);queue.append(n)
            components.append(component)
        components.sort(key=lambda c:(-len(c),min(c)))
        # All disconnected islands remain available together (armor UV layouts).
        options=[('整组',core)] if len(components)>1 else []
        options.extend((f'区域 {n+1}',part) for n,part in enumerate(components[:5]))
        for suffix,part in options:
            if not part:continue
            highlights=set()
            if family!=12:
                # Only near-white neighbors of this actual component may join.
                # Expansion is local and never floods the entire neutral handle.
                frontier=part
                for _ in range(max(1,min(3,min(width,height)//32))):
                    added={n for i in frontier for n in neighbors(i) if n in pixels and n not in part
                           and n not in highlights and pixels[n][1]<.16 and pixels[n][2]>.78}
                    highlights.update(added);frontier=added
            label=('中性色／白色材质' if family==12 else labels[family]+'色系')+' · '+suffix
            reason='颜色与连通形状候选；同色部件可能混入，请核对柄部、护手和描边。'
            if family==12:reason='白色可能是材质，也可能是高光；此候选不按白色一律排除，请人工确认。'
            score=sum(pixels[i][3]*(.2+.8*pixels[i][2])*(1 if family!=12 else .3+.7*pixels[i][2]) for i in part)
            output.append(Candidate(label,region_from_pixels(part,width),region_from_pixels(highlights,width),len(part),reason,score))
    # Prefer coherent colored material, but allow large white material to lead.
    output.sort(key=lambda c:(-c.score,c.label))
    return output[:32]
