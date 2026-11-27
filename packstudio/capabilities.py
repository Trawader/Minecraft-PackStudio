"""Shared predicates for menus, tool surfaces and backend entry points."""
from .sky_view import dimensions

TOOLS=(('mouse','移动'),('pencil','画笔'),('eraser','橡皮擦'),('bucket','油漆桶'),('picker','吸管'),('select','矩形选区'),('wand','魔棒'),('burn','加深'),('lighten','变明'))


def replacement(window,d,frame=False):
    selected=window.selected_asset;owner=window.source(d.get('origin',''))
    if owner is None or window.is_builtin(d):return False,'目标不存在或只读'
    if not selected:return False,'请先选中替换来源'
    files=selected.get('files',{});kind=d.get('kind');path=d.get('path','')
    if path.lower().endswith('.ogg'):
        ok=len(files)==1 and next(iter(files.values()),b'').startswith(b'OggS')
        return ok,'' if ok else '请选择单个 OGG 音效'
    if kind in ('root','folder'):
        ok=selected.get('kind')=='pack'
        return ok,'' if ok else '请选择文件夹或整包'
    if kind not in ('png','component'):return False,'此类型不支持替换'
    bindings=d.get('bindings',[])
    count=len(bindings) or (len(owner.regions) if owner.kind=='component' else len(d.get('regions',[]))) or 1
    if bindings and selected.get('kind')!='component':
        if all(b['path'] in files for b in bindings):values=[files[b['path']] for b in bindings]
        elif len(bindings)==1 and len(files)==1:values=list(files.values())
        else:return False,'请选择对应组件或包含相同资源路径的素材'
    else:values=list(files.values())
    if not bindings and owner.kind!='component' and selected.get('kind') not in ('png','component'):return False,'请选择 PNG 或图内组件'
    if len(values)!=count or any(not raw.startswith(b'\x89PNG\r\n\x1a\n') for raw in values):return False,'替换来源的图片类型或组件数量不匹配'
    if frame:
        width,height=dimensions(owner.files.get(path,b''));regions=d.get('regions',[])
        if len(values)!=1 or len(regions)!=1:return False,'请选择单张图片或单帧'
        r=regions[0];expected=(round(r[2]*width),round(r[3]*height))
        if dimensions(values[0])!=expected:return False,'帧替换需要相同尺寸'
    return True,''


def frame_reason(window):
    animation=window.animation_editor
    if not animation.frames:return '当前不是时间动画'
    if animation.mode.currentIndex()!=0:return '请切换到单帧编辑'
    rects={tuple(f[1]) for f in animation.frames}
    if len(rects)>256 or sum(r[2]*r[3] for r in rects)>4*1024*1024:return '整体分析限 256 帧／400 万像素；可逐帧编辑'
    if any(r[2]*r[3]>512*512 for r in rects):return '自动分析单帧限 512×512；可逐帧手动编辑'
    if window.canvas.selection_region.isEmpty():return '请先选中参考区域'
    return ''


def sync_editor(window):
    canvas=window.canvas;panel=window.recolor_panel
    editable=bool(window.current) and not canvas.image.isNull() and not canvas.read_only and not getattr(window,'large_view_only',False)
    if hasattr(window,'reset_material_button'):
        window.reset_material_button.setEnabled(editable and not canvas.drawing and not canvas.task_running and canvas.reset_image.size()==canvas.image.size())
    panel.body.setEnabled(editable)
    reason=frame_reason(window);panel.prepare_button.setEnabled(not reason);panel.prepare_button.setToolTip(reason or '分析各帧')
    item=panel.scope.model().item(2);item.setEnabled(bool(window.animation_editor.frames))
    if not window.animation_editor.frames and panel.scope.currentIndex()==2:panel.scope.setCurrentIndex(0)
    pending=panel.scope.currentIndex()==2 and (not panel.frames or any(f['include'] and not f['reviewed'] for f in panel.frames))
    enabled=bool(window.current) and not canvas.image.isNull() and not canvas.read_only and not pending
    panel.preview_button.setEnabled(enabled);panel.preview_button.setToolTip('请先分析并确认各帧范围' if pending else ('预览渐变' if getattr(panel,'tool_kind','recolor')=='gradient' else '预览调色'))
