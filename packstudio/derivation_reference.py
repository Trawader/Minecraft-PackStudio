"""Color-only and aligned-position references; source alpha and masks are authoritative."""
from collections import deque
from PySide6.QtGui import QImage
from .part_derivation import rgba,luminance

def aligned(source,target):
    if source.size()!=target.size():return False
    a,b=rgba(source),rgba(target);union=overlap=0
    for i in range(3,len(a),4):
        x=a[i]>0;y=b[i]>0;union+=x or y;overlap+=x and y
    return bool(union) and overlap/union>=.9

def reference_transfer(image,mask,target,target_mask,strength=100,mode='color',cancel=None):
    if mode not in ('color','position'):raise ValueError('未知参考模式')
    if mode=='position' and not aligned(image,target):raise ValueError('位置参考需要相同尺寸且轮廓对应的贴图，请改用颜色参考。')
    source,reference=rgba(image),rgba(target)
    if len(mask)!=image.width()*image.height() or len(target_mask)!=target.width()*target.height():raise ValueError('换色区域尺寸不匹配')
    total=0;sums=[0.,0.,0.]
    for i,selected in enumerate(target_mask):
        if selected:
            r,g,b,a=reference[i*4:i*4+4]
            total+=a
            for c,v in enumerate((r,g,b)):sums[c]+=v*a
    if not total:raise ValueError('目标参考没有可用的换色像素')
    mean=[v/total for v in sums];light=(54*mean[0]+183*mean[1]+19*mean[2])/256
    chroma=[v-light for v in mean];out=bytearray(source);w,h=image.width(),image.height()
    strength=max(0,min(100,strength))/100
    for p,selected in enumerate(mask):
        if p%4096==0 and cancel and cancel.is_set():raise InterruptedError()
        if not selected or not source[p*4+3]:continue
        old=list(source[p*4:p*4+3])
        if mode=='color':
            light=(54*old[0]+183*old[1]+19*old[2])/256
            scale=min([1.]+[(255-light)/v if v>0 else -light/v for v in chroma if v])
            color=[light+v*scale for v in chroma]
        else:
            if not reference[p*4+3]:continue
            # Target supplies position-dependent color; source supplies local detail.
            x,y=p%w,p//w;values=[]
            for yy in range(max(0,y-1),min(h,y+2)):
                for xx in range(max(0,x-1),min(w,x+2)):
                    n=yy*w+xx
                    if mask[n] and source[n*4+3]:values.append(luminance(*source[n*4:n*4+3]))
            base=sum(values)/max(1,len(values));detail=luminance(*old)/max(1,base)
            color=[min(255,v*detail) for v in reference[p*4:p*4+3]]
        for c in range(3):out[p*4+c]=max(0,min(255,round(old[c]+(color[c]-old[c])*strength)))
    return QImage(out,w,h,w*4,QImage.Format.Format_RGBA8888).copy()

def expand_mask(image,base,tolerance,protected=None,overrides=None):
    """Expand connected pixels against fixed seed colors, without color drift."""
    data=rgba(image);w,h=image.width(),image.height();result=bytearray(base);protected=bytearray(protected or bytes(len(base)))
    tolerance=max(0,min(255,int(tolerance)));overrides=overrides or {}
    for p,value in overrides.items():
        result[p]=int(value)
        if not value:protected[p]=1
    if not tolerance:return result
    def neighbors(p):
        if p%w:yield p-1
        if p%w+1<w:yield p+1
        if p>=w:yield p-w
        if p+w<len(base):yield p+w
    def eligible(p):return not result[p] and not protected[p] and data[p*4+3]>0
    queue=deque()
    for p,v in enumerate(result):
        if v and any(eligible(n) for n in neighbors(p)):queue.append((p,data[p*4:p*4+3]))
    while queue:
        p,color=queue.popleft()
        for n in neighbors(p):
            if eligible(n) and max(abs(data[n*4+c]-color[c]) for c in range(3))<=tolerance:
                result[n]=1;queue.append((n,color))
    return result


def material_ramp(image,mask):
    """Extract three weighted palette anchors, independent of reference resolution."""
    data=rgba(image);bins=[[] for _ in range(256)];total=0
    # Bounded samples for large references; alpha weights avoid transparent RGB.
    step=max(1,len(mask)//16384)
    for i in range(0,len(mask),step):
        r,g,b,a=data[i*4:i*4+4]
        if mask[i] and a:bins[luminance(r,g,b)].append((r,g,b,a));total+=a
    if not total:raise ValueError('目标参考没有可用的换色像素')
    result=[]
    for fraction in (.1,.5,.9):
        accumulated=0
        for rows in bins:
            weight=sum(row[3] for row in rows);accumulated+=weight
            if rows and accumulated>=total*fraction:
                result.append(tuple(round(sum(row[c]*row[3] for row in rows)/weight) for c in range(3)));break
    return tuple(result)


def ramp_transfer(image,mask,ramp,strength=100,source_histogram=None,cancel=None):
    from .part_derivation import histogram
    hist=source_histogram if source_histogram is not None else histogram(image,mask)
    total=sum(hist)
    if not total:raise ValueError('没有确认的换色部件像素；请调整部件区域或选择其他参考')
    points=[]
    for fraction in (.1,.5,.9):
        cumulative=0
        for value,count in enumerate(hist):
            cumulative+=count
            if cumulative>=total*fraction:points.append(value);break
    low,mid,high=points;table=[]
    for value in range(256):
        if low==high:color=ramp[1]
        elif value<=mid:
            t=max(0,min(1,(value-low)/max(1,mid-low)));color=[a+(b-a)*t for a,b in zip(ramp[0],ramp[1])]
        else:
            t=max(0,min(1,(value-mid)/max(1,high-mid)));color=[a+(b-a)*t for a,b in zip(ramp[1],ramp[2])]
        table.append(color)
    data=rgba(image);out=bytearray(data);strength=max(0,min(100,strength))/100
    for i,selected in enumerate(mask):
        if i%4096==0 and cancel and cancel.is_set():raise InterruptedError()
        if not selected or not data[i*4+3]:continue
        rgb=data[i*4:i*4+3];color=table[luminance(*rgb)]
        for c in range(3):out[i*4+c]=round(rgb[c]+(color[c]-rgb[c])*strength)
    return QImage(out,image.width(),image.height(),image.width()*4,QImage.Format.Format_RGBA8888).copy()
