"""Read vanilla PNG animation timelines without rewriting source metadata."""
import json


def timeline(raw,width,height):
    if raw is None:return [],False
    if type(width) is not int or type(height) is not int or width<=0 or height<=0:raise ValueError('PNG 尺寸无效')
    metadata=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(metadata,dict):raise ValueError('动画元数据必须是对象')
    animation=metadata.get('animation')
    if 'animation' not in metadata:return [],False
    if not isinstance(animation,dict):raise ValueError('animation 必须是对象')
    def positive(value,label,limit=21474836):
        if type(value) is not int or not 0<value<=limit:raise ValueError(label+' 不是可支持的正整数')
        return value
    if 'width' not in animation and 'height' not in animation:fw=fh=min(width,height)
    else:
        fw=positive(animation.get('width',width),'帧宽')
        fh=positive(animation.get('height',height),'帧高')
    if width%fw or height%fh:raise ValueError('帧尺寸无法整除贴图，保留整图编辑')
    count=(width//fw)*(height//fh)
    if not 0<count<=65536:raise ValueError('动画帧数量超出支持范围')
    default=positive(animation.get('frametime',1),'默认帧时长')
    entries=animation.get('frames')
    if entries is None or entries==[]:entries=range(count)
    elif not isinstance(entries,list):raise ValueError('frames 必须是数组')
    if len(entries)>65536:raise ValueError('动画序列过长')
    result=[]
    for entry in entries:
        index=entry.get('index') if isinstance(entry,dict) else entry
        duration=entry.get('time',default) if isinstance(entry,dict) else default
        if type(index) is not int or not 0<=index<count:raise ValueError('动画帧索引越界')
        result.append((index,(index%(width//fw)*fw,index//(width//fw)*fh,fw,fh),positive(duration,'帧时长')))
    interpolate=animation.get('interpolate',False)
    if type(interpolate) is not bool:raise ValueError('interpolate 必须是布尔值')
    return result,interpolate
