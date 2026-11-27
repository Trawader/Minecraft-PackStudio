import json
import zipfile
import uuid
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter,QImageReader

ROOT = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
from .versions import VERSIONS,detect,metadata_format,asset_tags

# Shared decode/edit ceiling: large sky atlases must retain their original pixels.
IMAGE_PIXEL_LIMIT=128*1024*1024
IMAGE_EDGE_LIMIT=32768
QImageReader.setAllocationLimit(640)

def safe_path(name):
    name = name.replace('\\', '/')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or ':' in name or not p.parts:
        raise ValueError(f'Unsafe resource path: {name}')
    return str(p)

def decode(data):
    if not isinstance(data,(bytes,bytearray)):raise ValueError('Missing image data')
    from .image_cache import images
    data=bytes(data)
    cached=images.get(data)
    if cached is not None:return cached
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer);size=reader.size()
    if size.width()>IMAGE_EDGE_LIMIT or size.height()>IMAGE_EDGE_LIMIT or size.width()*size.height()>IMAGE_PIXEL_LIMIT:
        raise ValueError('图片超出可编辑内存范围（单边 32768／总计 128 Mi 像素）；未缩小或修改原图。')
    im = reader.read()
    if im.isNull():
        raise ValueError('Cannot decode image')
    im=im.convertToFormat(QImage.Format.Format_ARGB32)
    images.put(data,im)
    return im

def png(im):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not im.save(buf, 'PNG'):raise ValueError('无法编码 PNG；原文件未修改。')
    result=bytes(data)
    from .image_cache import images
    images.put(result,im.convertToFormat(QImage.Format.Format_ARGB32))
    return result

def preserve_resolution(atlas,patch,region):
    """Grow the destination uniformly; never discard a patch's source pixels."""
    import math
    _,_,w,h=pixel_rect(region,atlas)
    scale=max(1,patch.width()/max(1,w),patch.height()/max(1,h))
    if scale<=1:return atlas
    width,height=math.ceil(atlas.width()*scale),math.ceil(atlas.height()*scale)
    if width>16384 or height>16384 or width*height>32*1024*1024:
        raise ValueError('保留高清像素所需的图集超过 3200 万像素，无法安全合成；请使用较小素材。')
    return atlas.scaled(width,height)

@dataclass
class Layer:
    name: str
    files: dict = field(default_factory=dict)
    kind: str = 'pack'
    target: str = ''
    regions: list = field(default_factory=list)
    enabled: bool = True
    source: str = ''
    uid: str = field(default_factory=lambda:uuid.uuid4().hex)
    format_hint: object = None
    library_uid: str = ''
    library_refs: list = field(default_factory=list)
    source_version: str = ''
    asset_versions: dict = field(default_factory=dict)
    layout_confirmations: dict = field(default_factory=dict)
    bindings: list = field(default_factory=list)
    read_only: bool = False
    selection: dict = field(default_factory=dict)

def import_pack(path,cancel=None,progress=None):
    def report(done,total):
        if cancel and cancel.is_set():raise InterruptedError("已取消导入")
        if progress:progress(done,total)
    path = Path(path)
    files = {}
    total = 0
    if path.is_dir():
        roots = list(path.rglob('pack.mcmeta')) if not (path/'pack.mcmeta').exists() else [path/'pack.mcmeta']
        root = roots[0].parent if len(roots) == 1 else path
        entries = [(p.relative_to(root).as_posix(), p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
        for index,(name, p) in enumerate(entries):
            report(index,len(entries))
            total += p.stat().st_size
            if p.stat().st_size > 256*1024**2 or total > 1024**3:
                raise ValueError('Resource pack exceeds size limit')
            files[safe_path(name)] = p.read_bytes()
    else:
        with zipfile.ZipFile(path) as z:
            entries = [i for i in z.infolist() if not i.is_dir()]
            roots = [i.filename[:-len('pack.mcmeta')] for i in entries if PurePosixPath(i.filename).name == 'pack.mcmeta']
            prefix = roots[0] if len(roots) == 1 else ''
            for index,i in enumerate(entries):
                report(index,len(entries))
                safe_path(i.filename)
                if not i.filename.startswith(prefix):
                    continue
                total += i.file_size
                if i.file_size > 256*1024**2 or total > 1024**3:
                    raise ValueError('Resource pack exceeds size limit')
                name = safe_path(i.filename[len(prefix):])
                if name in files:
                    raise ValueError(f'Duplicate resource: {name}')
                files[name] = z.read(i)
    report(0,0)
    candidates=detect(files)
    return Layer(path.stem, files, source=str(path.resolve()),source_version=candidates[0] if len(candidates)==1 else '',asset_versions=asset_tags(files,candidates[-1]))

class Vanilla:
    def __init__(self, root=None):
        self.root = Path(root) if root else None
        self._paths={}
    def get(self, version, name):
        name = safe_path(name)
        if version not in VERSIONS or not name.startswith('assets/'):
            return None
        if self.root:
            p = self.root/version/name[7:]
            if p.is_file():return p.read_bytes()
        from .builtin_assets import get
        return get(version,name)
    def paths(self, version):
        if version not in VERSIONS:return set()
        if version in self._paths:return self._paths[version]
        from .builtin_assets import paths
        self._paths[version]=paths(version)
        if self.root:
            root = self.root/version
            self._paths[version].update('assets/'+p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
        return self._paths[version]

def identify(layer, vanilla):
    try:
        fmt = json.loads(layer.files.get('pack.mcmeta', b'{}').decode('utf-8-sig')).get('pack', {}).get('pack_format', '?')
    except (ValueError, UnicodeError):
        fmt = 'invalid'
    matches = {v: len(set(layer.files) & vanilla.paths(v)) for v in VERSIONS}
    return fmt, matches

def pixel_rect(region, image):
    x,y,w,h = region
    left,top = round(x*image.width()),round(y*image.height())
    right,bottom = round((x+w)*image.width()),round((y+h)*image.height())
    if min(left,top)<0 or right>image.width() or bottom>image.height() or right<=left or bottom<=top:
        raise ValueError('Component is outside the image')
    return left,top,right-left,bottom-top

def compose(layers, vanilla, version):
    from .sounds import is_definition,merge
    files, provenance = {}, {}
    for layer in reversed(layers):
        if not layer.enabled:
            continue
        if layer.kind != 'component':
            for name, data in layer.files.items():
                if name in files and is_definition(name):data=merge(files[name],data,name)
                files[name] = data
                provenance[name] = [layer.name]
            continue
        if layer.bindings:
            from dataclasses import replace
            for i,binding in enumerate(layer.bindings):
                part=replace(layer,files={'0':layer.files[str(i)]},target=binding['path'],regions=[binding['region']],bindings=[])
                files,part_provenance=compose([part,Layer('base',files)],vanilla,version)
                provenance.update(part_provenance)
            continue
        name = layer.target
        base = files.get(name) or vanilla.get(version,name)
        if base is None:
            from .versions import source_version
            base=vanilla.get(source_version(layer,version),name)
        if base is None:
            raise ValueError(f'Missing atlas: {name}')
        atlas = decode(base)
        for i,r in enumerate(layer.regions):atlas=preserve_resolution(atlas,decode(layer.files[str(i)]),r)
        patches = [(pixel_rect(r,atlas),decode(layer.files[str(i)])) for i,r in enumerate(layer.regions)]
        painter = QPainter(atlas)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        for (x,y,w,h), patch in patches:
            painter.drawImage(x,y,patch.scaled(w,h))
        painter.end()
        files[name] = png(atlas)
        provenance.setdefault(name,['Vanilla']).append(layer.name)
    return files, provenance

def export_pack(path, files, version, description):
    if version not in (*VERSIONS, 'unchanged'):
        raise ValueError('Unsupported version')
    files = dict(files)
    if version != 'unchanged':
        pack={'description':description};metadata_format(pack,version)
        files['pack.mcmeta'] = json.dumps({'pack':pack},ensure_ascii=False,indent=2).encode()
    write_zip(path, files)

def newer_pack_sources(layers):
    """Evidence only: no attempt to convert names, models or texture layouts."""
    result=[]
    for layer in layers:
        if not layer.enabled:continue
        if isinstance(layer.format_hint,(int,float)) and layer.format_hint>1:
            result.append((layer.name,layer.format_hint));continue
        if 'pack.mcmeta' not in layer.files:continue
        try:
            pack=json.loads(layer.files['pack.mcmeta'].decode('utf-8-sig')).get('pack',{})
            fmt=pack.get('pack_format',1)
            if (isinstance(fmt,(int,float)) and fmt>1) or 'min_format' in pack or 'max_format' in pack:
                result.append((layer.name,fmt))
        except (ValueError,UnicodeError,AttributeError):pass
    return result

def write_zip(path, files, progress=None):
    path = Path(path)
    temp = path.with_name(path.name+'.writing')
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for index,(name,data) in enumerate(sorted(files.items())):
                if progress:progress(index,len(files)+1)
                z.writestr(safe_path(name),data)
        temp.replace(path)
        if progress:progress(len(files)+1,len(files)+1)
    finally:
        temp.unlink(missing_ok=True)

def save_project(path,layers,version,sources=None):
    manifest = {'schema':2,'version':version,'layers':[],'sources':[],'selections':{}}
    files = {}
    for section,entries in [('layers',layers),('sources',sources or [])]:
        for i,l in enumerate(entries):
            item = {k:getattr(l,k) for k in ('name','kind','target','regions','enabled','source','uid','format_hint','library_uid','library_refs','source_version','asset_versions','layout_confirmations','bindings','read_only')}
            if l.selection:manifest['selections'][l.uid]=l.selection
            item['files'] = {}
            for j,(name,data) in enumerate(l.files.items()):
                blob = 'blobs/'+hashlib.sha256(data).hexdigest()
                files[blob] = data
                item['files'][name] = blob
            manifest[section].append(item)
    files['project.json'] = json.dumps(manifest,ensure_ascii=False).encode()
    write_zip(path,files)

def load_project(path,include_sources=False):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 1024**3:
            raise ValueError('Project exceeds size limit')
        manifest = json.loads(z.read('project.json'))
        if manifest['schema'] not in (1,2) or manifest['version'] not in VERSIONS:
            raise ValueError('Unsupported project')
        sections={}
        blobs={}
        def read_blob(name):
            name=safe_path(name)
            if name not in blobs:blobs[name]=z.read(name)
            return blobs[name]
        for section in ('layers','sources'):
            sections[section]=[]
            for original in manifest.get(section,[]):
                item=dict(original)
                item['files'] = {safe_path(k):read_blob(v) for k,v in item['files'].items()}
                if item['kind'] not in ('pack','png','component'):raise ValueError('Unknown layer type')
                if item['target']:item['target'] = safe_path(item['target'])
                item['selection']=manifest.get('selections',{}).get(item.get('uid'),item.get('selection',{}))
                sections[section].append(Layer(**item))
        if manifest['schema']==1:
            # Existing projects keep their composition and gain independent browseable sources.
            from dataclasses import replace
            sections['sources']=[replace(l,files=dict(l.files),uid=uuid.uuid4().hex) for l in sections['layers'] if l.kind!='component']
    result=(sections['layers'],manifest['version'])
    return (*result,sections['sources']) if include_sources else result

def components(path,version='1.8.9'):
    from .semantics import parts,GROUPS
    detailed=parts(path,version)
    if detailed:
        result=[(p['name'],p['regions']) for p in detailed]
        groups={}
        for p in detailed:groups.setdefault(p['group'],[]).extend(p['regions'])
        return [(GROUPS[g],r) for g,r in groups.items()]+result
    if path.endswith('/gui/icons.png'):
        xp = [(0,64/256,182/256,5/256),(0,69/256,182/256,5/256)]
        return [('准星 / Crosshair',[(0,0,15/256,15/256)]),('经验条组 / XP bar',xp),('经验条底 / XP background',xp[:1]),('经验条填充 / XP fill',xp[1:])]
    if path.endswith('/particle/particles.png'):
        grid=32 if version=='1.13.2' else 16
        return [(f'粒子格 / Particle cell {y:02},{x:02}',[(x/grid,y/grid,1/grid,1/grid)]) for y in range(grid) for x in range(grid)]
    from .adaptation import RULES_BY_SOURCE,slot
    result=[];seen=set()
    for rule in RULES_BY_SOURCE.get(path,[]):
        match=slot(rule,version)
        if not match or match[0]!=path:continue
        x,y,w,h,tw,th=match[1];region=(x/tw,y/th,w/tw,h/th)
        if region in seen:continue
        seen.add(region);result.append((Path(rule['target']).stem,[region]))
    return result
