"""Explicit PNG scopes, frame-local masks and conflict-checked batch transactions."""
import copy
import struct
from dataclasses import dataclass,field
from PySide6.QtGui import QImage,QRegion,QPainter
from .core import decode,png,pixel_rect,IMAGE_PIXEL_LIMIT
from .recolor import render
from .texture_animation import timeline


def region_candidates(image,allowed):
    """Analyze only the permitted component, keeping frame-local coordinates."""
    from .smart_regions import analyze
    if image.width()*image.height()>512*512:raise ValueError('当前视图超过 512×512，请先切到单帧或使用手动选区。')
    scoped=QImage(image.size(),QImage.Format.Format_ARGB32);scoped.fill(0)
    painter=QPainter(scoped);painter.setClipRegion(allowed)
    painter.drawImage(0,0,image);painter.end()
    return analyze(scoped)


@dataclass
class Unit:
    path: str
    rect: tuple
    allowed: QRegion
    animated: bool=False
    index: int=0
    mask: QRegion=field(default_factory=QRegion)
    weights: dict=field(default_factory=dict)
    reviewed: bool=True
    included: bool=True
    initialized: bool=False


def targets(owner,descriptor):
    files=owner.files;kind=descriptor.get('kind');path=descriptor.get('path','')
    if owner.kind=='component':return {p:None for p in files if files[p].startswith(b'\x89PNG\r\n\x1a\n')}
    if descriptor.get('bindings'):
        result={}
        for binding in descriptor['bindings']:result.setdefault(binding['path'],[]).append(binding['region'])
    elif kind=='component':result={path:descriptor.get('regions')}
    elif kind=='root':result={p:None for p in files}
    elif kind=='folder':result={p:None for p in files if p.startswith(path.rstrip('/')+'/')}
    elif 'resource_paths' in descriptor or 'object_paths' in descriptor:
        result={p:None for p in descriptor.get('resource_paths',descriptor.get('object_paths',[]))}
    elif kind=='png':result={path:None}
    else:return {}
    return {p:regions for p,regions in sorted(result.items()) if p in files and p.lower().endswith('.png')}


def plan(owner,descriptor,cancel=None,progress=None):
    units=[];errors=[];baseline={};metadata={}
    paths=targets(owner,descriptor)
    for number,(path,regions) in enumerate(paths.items()):
        if cancel and cancel.is_set():raise InterruptedError("已取消分析，文件未修改。")
        if progress:progress(number,len(paths))
        raw=owner.files[path]
        try:
            if len(raw)<24 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('不是有效 PNG')
            width,height=struct.unpack('>II',raw[16:24])
            if width*height>IMAGE_PIXEL_LIMIT:raise ValueError('超出可编辑内存范围（128 Mi 像素）；原图保留')
            image=decode(raw);allowed=QRegion(image.rect())
            if regions:
                allowed=QRegion()
                for region in regions:allowed=allowed.united(QRegion(*pixel_rect(region,image)))
                allowed=allowed.intersected(QRegion(image.rect()))
            frames,_=timeline(owner.files.get(path+'.mcmeta'),image.width(),image.height())
            entries=list(dict.fromkeys((index,tuple(rect)) for index,rect,_ in frames)) if frames else [(0,(0,0,image.width(),image.height()))]
            if len(entries)>256:raise ValueError('动画超过 256 帧，请单独处理')
            for index,rect in entries:
                mask=allowed.intersected(QRegion(*rect)).translated(-rect[0],-rect[1])
                if mask.isEmpty():continue
                units.append(Unit(path,rect,mask,bool(frames),index,QRegion() if frames else QRegion(mask),reviewed=not frames))
            baseline[path]=raw;metadata[path+'.mcmeta']=owner.files.get(path+'.mcmeta')
        except (ValueError,UnicodeError,struct.error) as error:errors.append((path,str(error)))
    if progress:progress(len(paths),len(paths))
    return units,baseline,metadata,errors


def plan_whole(owner,descriptor,cancel=None,progress=None):
    """One whole PNG per unit; animation metadata and unused frames stay intact."""
    paths=targets(owner,descriptor);units=[];baseline={};metadata={};errors=[]
    for index,path in enumerate(paths):
        if cancel and cancel.is_set():raise InterruptedError('已取消分析，文件未修改。')
        if progress:progress(index,len(paths))
        try:
            image=decode(owner.files[path]);region=QRegion(image.rect())
            units.append(Unit(path,(0,0,image.width(),image.height()),region,mask=QRegion(region),initialized=True))
            baseline[path]=owner.files[path];metadata[path+'.mcmeta']=owner.files.get(path+'.mcmeta')
        except (ValueError,UnicodeError) as error:errors.append((path,str(error)))
    if progress:progress(len(paths),len(paths))
    return units,baseline,metadata,errors


def preview_files(units,baseline,settings,cancel=None,progress=None):
    groups={}
    for unit in units:
        if not unit.included:continue
        if not unit.reviewed or unit.mask.isEmpty():raise ValueError('仍有未确认或为空的处理区域：'+unit.path)
        groups.setdefault(unit.path,[]).append(unit)
    if not groups:raise ValueError('请勾选要处理的图片／帧')
    outputs={}
    for count,(path,items) in enumerate(groups.items(),1):
        if cancel and cancel.is_set():raise InterruptedError('已取消预览，没有修改文件')
        original=decode(baseline[path]);result=QImage(original)
        for unit_index,unit in enumerate(items):
            if cancel and cancel.is_set():raise InterruptedError('已取消预览，没有修改文件')
            region=unit.mask.intersected(unit.allowed)
            whole=len(items)==1 and unit.rect==(0,0,original.width(),original.height()) and region==QRegion(original.rect())
            patch=render(original if whole else original.copy(*unit.rect),region,settings,unit.weights,cancel,
                (lambda done,total:progress((count-1)*1000+int(950*(unit_index+done/max(1,total))/len(items)),len(groups)*1000)) if progress else None)
            if whole:
                result=patch
                continue
            painter=QPainter(result);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            # Composite only this mask, not the unchanged pixels around it.
            # Every patch reads the baseline, so overlaps are adjusted once.
            painter.setClipRegion(region.translated(unit.rect[0],unit.rect[1]))
            painter.drawImage(unit.rect[0],unit.rect[1],patch);painter.end()
        if result!=original:outputs[path]=png(result)
        if progress:progress(count*1000,len(groups)*1000)
    return outputs


def persist(window,owner,origin):
    if not origin.startswith('stage:'):
        from .task_progress import run_progress
        timer=window.library_save_timer;active=timer.isActive();timer.stop()
        try:run_progress(window,'正在保存批量调色',lambda cancel,progress:window.library_store.put(owner),cancellable=False)
        finally:
            if active:timer.start()


def apply_batch(window,origin,owner,baseline,metadata,output):
    if any(path not in baseline for path in output):raise ValueError('预览包含范围外文件，请重新生成。')
    if hasattr(window,'operation_history'):window.operation_history.flush()
    if window.source(origin) is not owner or window.is_builtin({'origin':origin}):raise ValueError('来源已变化或只读，请重新打开批量调色')
    if window.current_source==origin and window.canvas.drawing:raise ValueError('当前画板仍在绘制，请先结束笔画')
    for path,raw in {**baseline,**metadata}.items():
        if owner.files.get(path)!=raw:raise ValueError('预览后资源已变化，请重新分析：'+path)
    changed={p:raw for p,raw in output.items() if p in baseline and raw!=baseline[p]}
    if not changed:return 0
    before={p:baseline[p] for p in changed};dirty=window.dirty
    owner.files.update(changed)
    try:persist(window,owner,origin)
    except Exception:
        owner.files.update(before);raise
    history=getattr(window,'batch_recolor_history',[])
    history.append((origin,owner.uid,before,changed,{p+'.mcmeta':metadata.get(p+'.mcmeta') for p in changed}))
    # Bound retained compressed PNGs, always retaining the latest transaction.
    while len(history)>1 and (len(history)>10 or sum(sum(map(len,entry[2].values()))+sum(map(len,entry[3].values())) for entry in history)>128*1024*1024):history.pop(0)
    window.batch_recolor_history=history
    if hasattr(window,'operation_history'):window.operation_history.batch(history[-1])
    if window.current_source==origin:window.clear_editor()
    window.changed();window.refresh()
    if not origin.startswith('stage:'):window.dirty=dirty;window.setWindowModified(dirty)
    return len(changed)


def undo_batch(window):
    history=getattr(window,'batch_recolor_history',[])
    if not history:raise ValueError('没有可撤销的批量调色')
    origin,uid,before,after,metadata=history[-1];owner=window.source(origin)
    if owner is None or owner.uid!=uid or window.is_builtin({'origin':origin}):raise ValueError('批量调色来源已移除或只读')
    if any(owner.files.get(p)!=raw for p,raw in {**after,**metadata}.items()):raise ValueError('批量调色后这些文件又被编辑过，已阻止覆盖；请先撤销后续编辑')
    dirty=window.dirty;owner.files.update(before)
    try:persist(window,owner,origin)
    except Exception:
        owner.files.update(after);raise
    item=history.pop()
    if hasattr(window,'operation_history'):window.operation_history.external_undo(item)
    if window.current_source==origin:window.clear_editor()
    window.changed();window.refresh()
    if not origin.startswith('stage:'):window.dirty=dirty;window.setWindowModified(dirty)
    return len(before)


def add_action(window,menu,descriptor):
    if descriptor.get('kind')=='component':return
    owner=window.source(descriptor.get('origin'))
    if owner is None or window.is_builtin(descriptor) or not targets(owner,descriptor):return
    stable=copy.deepcopy(descriptor)
    action=menu.addAction(window.tr('批量调色…','Batch recolor…'))
    def open_dialog():
        from .batch_recolor_dialog import BatchRecolorDialog
        dialog=BatchRecolorDialog(window,stable);window.batch_recolor_dialog=dialog
        try:dialog.exec()
        finally:
            if window.batch_recolor_dialog is dialog:window.batch_recolor_dialog=None
            dialog.deleteLater()
    from PySide6.QtCore import QTimer
    action.triggered.connect(lambda:QTimer.singleShot(0,lambda:window.run(open_dialog)))
