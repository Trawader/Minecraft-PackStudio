"""Local file drops use deterministic path/name rules; ambiguous files stay unassigned."""
from functools import lru_cache
from pathlib import Path,PurePosixPath
import zipfile
from PySide6.QtCore import QObject,QEvent,Qt,QTimer
from PySide6.QtWidgets import QApplication,QWidget,QMessageBox
from .core import Layer,import_pack,decode,safe_path
from .versions import VERSIONS,records
from .export_targets import valid_target


def asset_context(path):
    parts=Path(path).parts
    for index in range(len(parts)-1,-1,-1):
        if parts[index]=='assets':
            return '/'.join(parts[index:])
    return None


@lru_cache(maxsize=11)
def filenames(version):
    result={}
    for path,row in records(version).items():
        if path.endswith('.png'):result.setdefault(PurePosixPath(path).name,[]).append((path,row.get('size')))
    return result


def identify_png(path,image,version):
    explicit=asset_context(path)
    if explicit:
        try:return valid_target(explicit,path.name),'原始 assets 路径'
        except ValueError:pass
    # Require one exact filename in the chosen local version, and compatible dimensions.
    candidates=filenames(version).get(path.name,[]) if version in VERSIONS else []
    if len(candidates)==1:
        target,size=candidates[0]
        if size and size[0]>0 and size[1]>0 and image.width()%size[0]==0 and image.height()%size[1]==0 and image.width()//size[0]==image.height()//size[1]:
            return target,'本地版本数据库：唯一规范文件名及一致尺寸比例'
    return safe_path(path.name),'未确认资源身份'


def mark_unmapped(layer,complete=False):
    if complete:return layer
    pending=[]
    for name in layer.files:
        if name.startswith('assets/'):
            # Existing custom namespace paths remain valid even outside vanilla databases.
            try:valid_target(name,name);continue
            except ValueError:pass
        if name.lower().endswith('.png.mcmeta') and name[:-7] in layer.files:continue
        pending.append(name)
    if pending:layer.selection['unmapped_paths']=pending
    return layer


def read_source(path,version):
    path=Path(path)
    if path.is_dir() or path.suffix.lower()=='.zip':
        layer=import_pack(path)
        if not layer.files:raise ValueError('目录或压缩包没有可导入的文件')
        complete='pack.mcmeta' in layer.files and any(p.startswith('assets/') for p in layer.files)
        prefix=asset_context(path) if path.is_dir() and not complete else None
        if prefix:
            paths={p:safe_path(prefix+'/'+p) for p in layer.files}
            layer.files={paths[p]:raw for p,raw in layer.files.items()}
            layer.asset_versions={paths[p]:v for p,v in layer.asset_versions.items() if p in paths}
        layer.selection['import_kind']='完整资源包' if complete else '文件夹／压缩包素材'
        return mark_unmapped(layer,complete)
    if not path.is_file():raise ValueError('文件不存在')
    if path.stat().st_size>256*1024**2:raise ValueError('单个素材超过 256 MiB')
    raw=path.read_bytes()
    if path.suffix.lower()=='.png':
        from .sky_view import oversized,thumbnail
        if oversized(raw):
            thumbnail(raw);target=asset_context(path) or safe_path(path.name);evidence='大尺寸 PNG，只读预览；保留原路径'
        else:
            image=decode(raw);target,evidence=identify_png(path,image,version)
        files={target:raw};metadata=Path(str(path)+'.mcmeta')
        if metadata.is_file():
            if metadata.stat().st_size>256*1024**2:raise ValueError('动画配置过大')
            files[target+'.mcmeta']=metadata.read_bytes()
        layer=Layer(path.stem,files,kind='png',source=str(path.resolve()))
        layer.selection['identification']=evidence
        if evidence.startswith('本地版本数据库'):
            layer.asset_versions[target]=version
        return mark_unmapped(layer)
    target=asset_context(path) or safe_path(path.name)
    layer=Layer(path.name,{target:raw},source=str(path.resolve()))
    layer.selection['import_kind']='独立文件'
    return mark_unmapped(layer)


def import_paths(window,paths):
    unique=[]
    for raw in paths:
        path=Path(raw).resolve()
        if path not in unique:unique.append(path)
    # A folder already includes explicitly dropped children; don't import them twice.
    unique=[p for p in unique if not any(p!=parent and parent.is_dir() and p.is_relative_to(parent) for parent in unique)]
    unique=[p for p in unique if not (str(p).lower().endswith('.png.mcmeta') and Path(str(p)[:-7]) in unique)]
    imported=[];errors=[]
    window._batch_import=True
    try:
        for path in unique:
            try:
                layer=read_source(path,window.working_version);window.add_import(layer);imported.append(layer)
            except (OSError,ValueError,zipfile.BadZipFile,RuntimeError) as error:errors.append(path.name+'：'+str(error))
    finally:
        window._batch_import=False;window.refresh()
    pending=sum(len(layer.selection.get('unmapped_paths',[])) for layer in imported)
    window.statusBar().showMessage(f'已导入 {len(imported)} 个来源；{pending} 个素材待指定导出目标。未自动加入合成台。')
    if errors:
        message=QMessageBox(window);message.setWindowTitle('部分文件未导入')
        message.setText(f'{len(errors)} 个来源未能导入，其余来源已保留。');message.setDetailedText('\n'.join(errors));message.exec()


class DropFilter(QObject):
    def __init__(self,window):super().__init__(window);self.window=window
    def eventFilter(self,watched,event):
        if event.type() not in (QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.Drop):return False
        if not isinstance(watched,QWidget) or not (watched is self.window or self.window.isAncestorOf(watched)):return False
        if QApplication.activeModalWidget() is not None:return False
        mime=event.mimeData()
        if mime.hasFormat('application/x-packstudio-asset') or not mime.hasUrls():return False
        urls=mime.urls()
        if not urls or any(not url.isLocalFile() for url in urls):return False
        event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        if event.type()==QEvent.Type.Drop:
            paths=[url.toLocalFile() for url in urls]
            QTimer.singleShot(0,self.window,lambda:self.window.run(lambda:import_paths(self.window,paths)))
        return True


def install(window):
    window.setAcceptDrops(True)
    for widget in (window.tree,window.tree.viewport(),window.project_tree,window.project_tree.viewport(),window.canvas,window.preview):widget.setAcceptDrops(True)
    window.external_drop_filter=DropFilter(window)
    QApplication.instance().installEventFilter(window.external_drop_filter)
