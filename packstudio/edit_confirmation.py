"""Explicit user confirmation before loading a large editable original or writing a batch."""
from PySide6.QtWidgets import QMessageBox

LARGE_IMAGE_PIXELS=4*1024*1024


def large_image(window,descriptor):
    if descriptor.get('kind') not in ('png','component'):return True
    owner=window.source(descriptor.get('origin',''))
    if owner is None or window.is_builtin(descriptor):return True
    path=descriptor.get('path','')
    if window.current_source==descriptor['origin'] and window.current and window.current[0]==path:return True
    from .sky_view import dimensions
    width,height=dimensions(owner.files.get(path,b''))
    if width*height<=LARGE_IMAGE_PIXELS:return True
    title=window.tr('确认编辑大图','Confirm large image editing')
    message=window.tr(f'将载入原图进行编辑：\n{path}\n\n尺寸：{width} × {height}（约 {width*height/1000000:.1f} 百万像素）。\n处理和撤销记录可能占用较多内存，耗时操作将显示进度。\n继续吗？',f'Load the original image for editing:\n{path}\n\nSize: {width} × {height} ({width*height/1000000:.1f} megapixels).\nProcessing and undo may use substantial memory. Slow operations show progress.\nContinue?')
    return QMessageBox.question(window,title,message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Yes


def batch(window,parent,files):
    title=window.tr('确认批量调色','Confirm batch recolor')
    message=window.tr(f'即将修改 {len(files)} 张 PNG。\n将按当前参数处理勾选图片的完整原图，其他文件不变。\n是否继续？',f'Modify {len(files)} PNG files at full resolution using the current settings?\nOther files are unchanged.')
    return QMessageBox.question(parent,title,message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Yes
