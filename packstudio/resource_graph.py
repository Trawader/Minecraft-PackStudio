"""Local, evidence-based resource references. Unsupported formats stay opaque."""
from collections import defaultdict
from dataclasses import dataclass, field
import json
import posixpath
import re


def sky_texture(source,value):
    """Resolve explicit sky source paths; unrecognized forms remain opaque."""
    if value is None:return source.removesuffix('.properties')+'.png'
    if not isinstance(value,str) or not value or '\\' in value:return None
    namespace=source.split('/')[1]
    if value.startswith('assets/'):target=value
    elif value.startswith('~/'):
        engine='optifine' if '/optifine/sky/' in source else 'mcpatcher'
        target=f'assets/{namespace}/{engine}/'+value[2:]
    elif ':' in value:
        ns,relative=value.split(':',1)
        if not ns or not relative or relative.startswith('/'):return None
        target=f'assets/{ns}/{relative}'
    elif value.startswith('/'):target=f'assets/{namespace}/'+value[1:]
    elif value.startswith(('./','../')):target=posixpath.join(posixpath.dirname(source),value)
    else:target=f'assets/{namespace}/'+value
    target=posixpath.normpath(target)
    if not target.startswith('assets/') or len(target.split('/'))<4 or ':' in target:return None
    return target if target.lower().endswith('.png') else target+'.png'


def properties(raw):
    text=raw.decode('utf-8-sig',errors='replace')
    logical=[];pending=''
    for line in text.splitlines():
        line=pending+line.lstrip() if pending else line.strip()
        if len(line)-len(line.rstrip('\\')) & 1:pending=line[:-1];continue
        logical.append(line);pending=''
    if pending:logical.append(pending)
    result={}
    for line in logical:
        if not line or line.startswith(('#','!')):continue
        match=re.match(r'([^\s=:]+)\s*[=:]?\s*(.*)',line)
        if match:
            key,value=match.groups()
            result[key]=re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),value)
    return result


@dataclass
class ResourceGraph:
    files: dict
    edges: dict = field(default_factory=lambda:defaultdict(set))
    reverse: dict = field(default_factory=lambda:defaultdict(set))
    evidence: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    conditions: dict = field(default_factory=dict)

    def link(self,source,target,reason):
        if not target:return
        self.edges[source].add(target);self.reverse[target].add(source)
        self.evidence.append({'source':source,'target':target,'reason':reason,'present':target in self.files})

    def resource(self,source,value,folder,extension):
        if not isinstance(value,str) or value.startswith('#'):return None
        namespace=source.split('/')[1] if source.startswith('assets/') else 'minecraft'
        if ':' in value:namespace,value=value.split(':',1)
        value=value.removesuffix(extension)
        if value.startswith('/') or '..' in value.split('/') or '\\' in value or not namespace:return None
        target=f'assets/{namespace}/{folder}/{value}{extension}'
        # Pre-1.13 blockstates use bare model names such as "nether_wart_stage0".
        if folder=='models' and '/blockstates/' in source and '/' not in value and target not in self.files:
            block=f'assets/{namespace}/models/block/{value}{extension}'
            if block in self.files:return block
        return target

    def local(self,source,value,kind):
        extension='.json' if kind=='model' else '.png'
        if value.startswith('./') or value.startswith('../') or ':' not in value and not value.startswith(('item/','block/','entity/','textures/')):
            relative=posixpath.normpath(posixpath.join(posixpath.dirname(source),value))
            if not relative.startswith('assets/') or '..' in relative.split('/'):return None
            return relative if relative.endswith(extension) else relative+extension
        value=value.removeprefix('textures/')
        return self.resource(source,value,'models' if kind=='model' else 'textures',extension)

    def parse(self):
        from .sounds import is_definition,references
        for path,raw in self.files.items():
            if is_definition(path):
                try:
                    for event,target,kind,name in references(path,raw):self.link(path,target,'sound '+kind+' '+event)
                except ValueError as error:self.issues.append({'path':path,'reason':str(error)})
            if path.lower().endswith('.png') and path+'.mcmeta' in self.files:self.link(path,path+'.mcmeta','paired animation metadata')
            if path.endswith('.properties'):
                values=properties(raw);self.conditions[path]=values
                if any(folder in path for folder in ('/optifine/sky/','/mcpatcher/sky/')):
                    self.link(path,sky_texture(path,values.get('source')),'sky properties source')
                for key,value in values.items():
                    if key=='model' or key.startswith('model.') or key=='texture' or key.startswith('texture.'):
                        target=self.local(path,value,'model' if key.startswith('model') else 'texture')
                        self.link(path,target,'properties '+key)
                    elif key=='tiles':
                        for tile in value.split():
                            sequence=re.fullmatch(r'(\d+)-(\d+)',tile)
                            values_to_link=[str(n) for n in range(int(sequence[1]),min(int(sequence[2])+1,int(sequence[1])+4096))] if sequence else [tile]
                            for tile_name in values_to_link:self.link(path,self.local(path,tile_name,'texture'),'properties tiles')
                # CIT's documented implicit same-stem texture is accepted only if present.
                implicit=path.removesuffix('.properties')+'.png'
                if values.get('type')=='item' and not any(k.startswith(('texture','model')) for k in values) and implicit in self.files:
                    self.link(path,implicit,'CIT same-stem texture present')
                continue
            if not path.endswith('.json'):continue
            try:data=json.loads(raw.decode('utf-8-sig'))
            except (ValueError,UnicodeError):
                self.issues.append({'path':path,'reason':'JSON 无法解析，原文件保留'});continue
            if not isinstance(data,dict):continue
            if '/models/' in path:
                parent=data.get('parent')
                if parent not in ('builtin/generated','builtin/entity','minecraft:builtin/generated','minecraft:builtin/entity'):
                    self.link(path,self.resource(path,parent,'models','.json'),'model parent')
                textures=data.get('textures',{})
                for value in textures.values() if isinstance(textures,dict) else ():
                    if isinstance(value,dict):
                        value=value.get('sprite')
                        if not isinstance(value,str) or not value:
                            self.issues.append({'path':path,'reason':'模型贴图对象缺少有效的 sprite 引用，原文件保留'})
                            continue
                    self.link(path,self.resource(path,value,'textures','.png'),'model texture')
            if '/particles/' in path:
                textures=data.get('textures',[])
                for value in textures if isinstance(textures,list) else ():
                    if isinstance(value,str):
                        ns,sep,name=value.partition(':');value=(ns+':particle/'+name) if sep else 'particle/'+value
                        self.link(path,self.resource(path,value,'textures','.png'),'particle texture')
            if '/equipment/' in path:
                equipment=data.get('layers',{})
                for kind,layers in equipment.items() if isinstance(equipment,dict) else ():
                    if not isinstance(layers,list):continue
                    for layer in layers:
                        value=layer.get('texture') if isinstance(layer,dict) else None
                        if isinstance(value,str):
                            ns,sep,name=value.partition(':');value=(ns+':entity/equipment/'+kind+'/'+name) if sep else 'entity/equipment/'+kind+'/'+value
                            self.link(path,self.resource(path,value,'textures','.png'),'equipment layer '+kind)
            def walk(value):
                if isinstance(value,dict):
                    # Models selected by overrides, blockstates and new item definitions.
                    if isinstance(value.get('model'),str):self.link(path,self.resource(path,value['model'],'models','.json'),'model selection')
                    for child in value.values():walk(child)
                elif isinstance(value,list):
                    for child in value:walk(child)
            if any(t in path for t in ('/models/','/items/','/blockstates/','/overrides/')):walk(data)
        return self

    def closure(self,seeds,include_callers=True):
        roots=set(seeds);todo=list(roots)
        if include_callers:
            while todo:
                path=todo.pop()
                for caller in self.reverse.get(path,()):
                    if caller not in roots:roots.add(caller);todo.append(caller)
        selected=set();missing=set();todo=list(roots)
        while todo:
            path=todo.pop()
            if path in selected or path in missing:continue
            if path not in self.files:missing.add(path);continue
            selected.add(path);todo.extend(self.edges.get(path,()))
        return selected,missing


def graph_for(window,source):
    signature=tuple((p,raw) for p,raw in source.files.items() if p.endswith(('.json','.properties','.mcmeta')))
    paths=tuple(source.files)
    cache=getattr(window,'_resource_graphs',{})
    entry=cache.get(source.uid)
    if entry is None or entry[:2]!=(paths,signature):
        entry=(paths,signature,ResourceGraph(source.files).parse());cache[source.uid]=entry
    entry[2].files=source.files
    live={s.uid for s in window.sources}|{s.uid for s in window.layers}
    window._resource_graphs={uid:value for uid,value in cache.items() if uid in live}
    return entry[2]
