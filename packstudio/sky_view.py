"""Full-resolution sky editing with a separate lightweight skybox preview."""
import math
import struct
from PySide6.QtCore import Qt,QByteArray,QBuffer,QIODevice,QSize
from PySide6.QtGui import QImage,QImageReader
from .core import decode
from PySide6.QtWidgets import QAbstractButton,QComboBox,QSlider


def dimensions(raw):
    return struct.unpack('>II',raw[16:24]) if len(raw)>=24 and raw.startswith(b'\x89PNG\r\n\x1a\n') else (0,0)


def oversized(raw):
    w,h=dimensions(raw)
    return w>16384 or h>16384 or w*h>32*1024*1024


def thumbnail(raw,edge=2048):
    w,h=dimensions(raw)
    if w<=0 or h<=0:raise ValueError('无效 PNG 尺寸')
    if w*h>128*1024*1024:raise ValueError('图片超出当前只读解码内存上限（128 Mi 像素）')
    buffer=QBuffer();buffer.setData(QByteArray(raw));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer)
    size=QSize(w,h);size.scale(edge,edge,Qt.AspectRatioMode.KeepAspectRatio);reader.setScaledSize(size)
    previous=QImageReader.allocationLimit()
    try:
        QImageReader.setAllocationLimit(max(previous,640));image=reader.read()
    finally:QImageReader.setAllocationLimit(previous)
    if image.isNull():raise ValueError('无法读取 PNG：'+reader.errorString())
    return image.convertToFormat(QImage.Format.Format_ARGB32)


def set_locked(window,locked):
    window.large_view_only=locked
    panel=window.docks['editor'].widget()
    if locked:
        strip=getattr(getattr(window,'resource_editors',None),'dock',None)
        window._viewer_controls=[(widget,widget.isEnabled()) for widget in panel.findChildren(QAbstractButton)+panel.findChildren(QComboBox)+panel.findChildren(QSlider) if strip is None or not strip.isAncestorOf(widget)]
        for widget,_ in window._viewer_controls:widget.setEnabled(False)
        window.canvas.set_tool('mouse');window.canvas.read_only=True
    else:
        for widget,enabled in getattr(window,'_viewer_controls',[]):widget.setEnabled(enabled)
        window._viewer_controls=[]


def open_view(window,descriptor):
    if descriptor.get('kind')!='png':
        if descriptor.get('kind')=='component':window.sky_edit_key=None
        return False
    owner=window.source(descriptor['origin'])
    if owner is None:return False
    path=descriptor['path'];raw=owner.files.get(path)
    if raw is None:return False
    sky=any(folder in path for folder in ('/optifine/sky/','/mcpatcher/sky/'))
    if not sky:
        from .resource_graph import properties,sky_texture
        sky=any(sky_texture(config,properties(data).get('source'))==path for config,data in owner.files.items()
                if config.endswith('.properties') and any(folder in config for folder in ('/optifine/sky/','/mcpatcher/sky/')))
    if not sky and not oversized(raw):
        window.sky_edit_key=None
        return False
    w,h=dimensions(raw)
    from .task_progress import run_progress
    image=run_progress(window,'正在载入原图',lambda cancel,progress:decode(raw)) if w*h>1024*1024 else decode(raw)
    window.selection_timer.stop();window.pending_resource=None
    if hasattr(window,'texture_timer'):window.texture_timer.stop()
    window.current_source=descriptor['origin'];window.current=(path,None);window.edit_bindings=None
    if hasattr(window,'animation_editor'):window.animation_editor.reset()
    set_locked(window,False)
    window.canvas.set_image(image);window.canvas.read_only=window.is_builtin(descriptor)
    window.sky_edit_key=(descriptor['origin'],path) if sky else None
    window.edit_parts=[];window.atlas_size=(w,h)
    window.edit_layer=owner if descriptor['origin'].startswith('stage:') else None
    source='原版只读 · 加入项目后编辑' if window.canvas.read_only else '项目副本' if descriptor['origin'].startswith('stage:') else '素材库本体'
    window.caption.setText(f'{source} · {path} · {w} × {h}')
    window.preview.clear_model();window.model_key=None
    if sky and (w*2==h*3 or w==h*2):
        window.preview.sky_image=preview_image(image);window.preview.sky_layout='cube' if w*2==h*3 else 'panorama'
        window.preview.sky_cache=None;window.preview.yaw=0;window.preview.pitch=0;window.preview.zoom=1
        window.model_info.setText(window.tr('天空单层预览 · 左键拖动环视／Alt+滚轮缩放；不模拟天气、时段及多层混合。','Single-layer sky preview · Drag to look around / Alt+wheel to zoom; weather, time and multi-layer blending are not simulated.'))
    else:
        window.preview.flat_image=preview_image(image);window.model_info.setText('平面预览；未确认天空布局，仍可编辑原图。' if sky else '平面预览；编辑保持原始分辨率。')
    window.preview.update();window.docks['render'].show()
    if hasattr(window,'resource_rules'):window.resource_rules.inspect(descriptor)
    if hasattr(window,'resource_editors'):window.resource_editors.show_resources(descriptor)
    return True


def preview_image(image):
    if max(image.width(),image.height())<=2048:return QImage(image)
    return image.scaled(2048,2048,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)


def sync_preview(window,image=None):
    key=getattr(window,'sky_edit_key',None)
    if key is None or not window.current or key!=(window.current_source,window.current[0]):return False
    image=window.canvas.image if image is None else image
    preview=window.preview;small=preview_image(image)
    if preview.sky_image is not None:preview.sky_image=small;preview.sky_cache=None
    else:preview.flat_image=small
    preview.update();return True


def render(image,layout,yaw,pitch,zoom,width,height):
    factor=min(1,360/max(1,width),220/max(1,height))
    width=max(1,round(width*factor));height=max(1,round(height*factor))
    source=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=bytes(source.constBits());sw,sh=source.width(),source.height()
    output=bytearray(width*height*4);cy,sy=math.cos(yaw),math.sin(yaw);cp,sp=math.cos(pitch),math.sin(pitch)
    scale=math.tan(math.radians(80)/2)/max(.2,zoom)
    for py in range(height):
        yy=(1-2*(py+.5)/height)*scale
        for px in range(width):
            xx=(2*(px+.5)/width-1)*scale*width/height
            y=yy*cp+sp;z=yy*sp-cp;x=xx*cy-z*sy;z=xx*sy+z*cy
            if layout=='panorama':
                u=(math.atan2(x,-z)/(2*math.pi)+.5)%1;v=.5-math.atan2(y,math.hypot(x,z))/math.pi
            else:
                ax,ay,az=abs(x),abs(y),abs(z)
                if ay>=ax and ay>=az:
                    tile=1 if y>0 else 0;u=(x/ay+1)/2;v=((z if y>0 else -z)/ay+1)/2
                elif ax>=az:
                    tile=5 if x>0 else 3;u=((z if x>0 else -z)/ax+1)/2;v=(1-y/ax)/2
                else:
                    tile=2 if z>0 else 4;u=((-x if z>0 else x)/az+1)/2;v=(1-y/az)/2
                u=(tile%3+max(0,min(.999999,u)))/3;v=(tile//3+max(0,min(.999999,v)))/2
            sx=min(sw-1,max(0,int(u*sw)));sy_pixel=min(sh-1,max(0,int(v*sh)))
            pos=(sy_pixel*sw+sx)*4;dest=(py*width+px)*4
            output[dest:dest+4]=raw[pos:pos+4]
    return QImage(output,width,height,width*4,QImage.Format.Format_RGBA8888).copy()
