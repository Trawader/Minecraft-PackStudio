"""Multi-file groups use one canvas with explicit reversible pixel bindings."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from .core import decode,png,pixel_rect
from .versions import source_version
from .library_browser import builtin_version

def snapshot_group(w,d):
    bindings=d.get('bindings')
    if not bindings:return None
    owner=w.source(d['origin']);version=source_version(owner,w.working_version) if owner else builtin_version(w,d['origin'])
    if owner and owner.kind=='component':files=dict(owner.files)
    else:
        files={}
        for i,b in enumerate(bindings):
            raw=owner.files[b['path']] if owner else w.vanilla.get(version,b['path'])
            im=decode(raw);files[str(i)]=png(im.copy(*pixel_rect(b['region'],im)))
    return {'name':d['name'],'files':files,'kind':'component','path':bindings[0]['path'],'regions':[b['region'] for b in bindings],
        'bindings':copy.deepcopy(bindings),'origin':w.origin_label(owner) if owner else 'Vanilla '+version,'hint':owner.format_hint if owner else None,'version':version,'asset_versions':{}}

def open_group(w,d):
    if not d.get('bindings'):return False
    w.selection_timer.stop();w.pending_resource=None
    asset=snapshot_group(w,d);w.current_source=d['origin'];w.current=(d['path'],d.get('regions'));w.edit_bindings=copy.deepcopy(d['bindings'])
    image=w.join_parts([decode(asset['files'][str(i)]) for i in range(len(d['bindings']))]);w.canvas.set_image(image)
    w.atlas_size=(image.width(),image.height());w.preview.clear_model();w.preview.flat_image=image.copy();w.preview.update()
    w.caption.setText(d['name']+' · '+str(len(d['bindings']))+' 个部件 / parts');return True

def commit_group(w):
    bindings=getattr(w,'edit_bindings',None)
    if not bindings:return False
    owner=w.source(w.current_source)
    if not owner:return True  # Built-in originals are read-only.
    patches=[w.canvas.image.copy(*rect) for rect in w.edit_parts]
    if owner.kind=='component':owner.files={str(i):png(im) for i,im in enumerate(patches)}
    else:
        images={}
        for b,patch in zip(bindings,patches):
            path=b['path']
            if path not in images:images[path]=decode(owner.files[path])
            im=images[path];x,y,width,height=pixel_rect(b['region'],im)
            painter=QPainter(im);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.drawImage(x,y,patch.scaled(width,height));painter.end()
        owner.files.update({p:png(im) for p,im in images.items()})
    w.changed();w.preview.flat_image=w.canvas.image.copy();w.preview.update();return True
