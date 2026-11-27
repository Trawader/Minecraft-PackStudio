"""Object-first selector index, resolved from model roots rather than PNG neighbours."""
from collections import OrderedDict,defaultdict,Counter
from functools import lru_cache
import re
import json
from .resource_graph import ResourceGraph
from .semantics import identities,translations,describe
from .object_catalog import hierarchy,related_paths,related_index,object_entity_paths,entries as texture_entries
from .selector_taxonomy import item_base,object_kind,category,chinese_name,state_name,local_names,linked_identity,english_name
from .versions import VERSIONS

_cache=OrderedDict()
_graphs={}


def introduced(code,version,available):
    known=available.get(code,())
    return not known or version not in VERSIONS or any(v in VERSIONS and VERSIONS.index(v)<=VERSIONS.index(version) for v in known)


@lru_cache(maxsize=3)
def vanilla(version):
    from .builtin_assets import paths,get
    return {p:get(version,p) if p.endswith(('.json','.properties','.mcmeta')) else b'' for p in paths(version)}


def canonical(kind,name):
    kind,name=linked_identity(kind,name)
    if kind=='block' and name in ('anvil','chipped_anvil','damaged_anvil','anvil_intact','anvil_slightly_damaged','anvil_very_damaged'):return 'block/anvil'
    if kind=='item':name=item_base(name)
    return kind+'/'+name


def texture_identity(path,aliases):
    code=aliases.get(path,path.split('/textures/')[-1].removesuffix('.png'))
    kind,sep,name=code.partition('/')
    if not sep:return code
    kind,name=linked_identity(kind,name)
    if kind=='block':
        if re.fullmatch(r'(?:anvil(?:_base|_top|_top_damaged_[012]|_top_(?:intact|damaged|very_damaged))?|(?:chipped|damaged)_anvil_top)',name):return 'block/anvil'
        candidate=re.sub(r'_(stage_?\d+|top|bottom|side|front|back|end|inner|outer|side_on|front_on)$','',name)
        zh,en=translations()
        if 'block.minecraft.'+candidate in zh or 'block.minecraft.'+candidate in en:name=candidate
    if kind=='item':name=item_base(name);kind=object_kind(kind,name,path.split('/')[1] if path.startswith('assets/') else 'minecraft')
    return canonical(kind,name)


def label(identity,preview):
    return chinese_name(identity,preview)


def entries(source,version,full=False):
    signature=(version,full,tuple(source.files),tuple((p,raw) for p,raw in source.files.items() if p.endswith(('.json','.lang','.properties','.mcmeta'))))
    cached=_cache.get(source.uid)
    if cached and cached[0]==signature:return cached[1]
    combined=dict(vanilla(version));combined.update(source.files)
    graph=ResourceGraph(combined).parse();roots=defaultdict(set);rows={};covered=set()
    aliases,available=identities();anchors=defaultdict(set)
    for path in source.files:
        if not path.lower().endswith('.png'):continue
        code=aliases.get(path)
        # Version availability is evidence, not an invitation to synthesize missing resources.
        if code and not introduced(code,version,available):continue
        identity=texture_identity(path,aliases)
        namespace=path.split('/')[1] if path.startswith('assets/') else 'minecraft'
        anchors[(namespace,identity)].add(path)
    block_names={(p.split('/')[1],p.split('/blockstates/',1)[1][:-5]) for p in combined if p.startswith('assets/') and '/blockstates/' in p and p.endswith('.json')}
    for path in combined:
        if not path.startswith('assets/') or not path.endswith('.json'):continue
        namespace=path.split('/')[1];kind=None;name=None
        if '/blockstates/' in path:kind='block';name=path.split('/blockstates/',1)[1][:-5]
        elif '/items/' in path and '/models/' not in path:
            name=path.split('/items/',1)[1][:-5];kind='block' if (namespace,name) in block_names else 'item'
        elif '/models/item/' in path:
            name=path.split('/models/item/',1)[1][:-5];kind='block' if (namespace,name) in block_names else 'item'
        if kind:roots[(namespace,canonical(object_kind(kind,name,namespace,block_names),name))].add(path)
    siblings=defaultdict(list)
    for path in source.files:siblings[path.rsplit('/',1)[0]].append(path)
    item_index=related_index(source)
    for (namespace,identity),seeds in roots.items():
        if not introduced(identity,version,available):continue
        # A vanilla model's shared texture alone does not establish that object in this pack.
        if not anchors.get((namespace,identity)) and not (seeds & source.files.keys()):continue
        selected,_=graph.closure(seeds,include_callers=False)
        selected.update(anchors.get((namespace,identity),()))
        local=selected & source.files.keys()
        pictures={p for p in local if p.lower().endswith('.png')}
        if not pictures:continue
        # Armour equipment / shared worn textures are explicit object rules.
        for path in tuple(pictures):local.update(related_paths(source,path,siblings,item_index))
        local.update(object_entity_paths(source,identity,namespace))
        selected,_=graph.closure(local,include_callers=False);local=selected & source.files.keys()
        pictures={p for p in local if p.lower().endswith('.png')}
        preview=min(pictures,key=lambda p:('/textures/item/' not in p and '/textures/items/' not in p,len(p),p))
        groups=category(identity,preview,full,version)
        if groups is None:continue
        state_roots=sorted(p for p in seeds if '/blockstates/' in p)
        rows[(namespace,identity)]={'id':namespace+':'+identity,'name':chinese_name(identity,preview,namespace),'category':groups,'paths':set(local),'preview':preview,'state_roots':state_roots}
        covered.update(pictures)
    # Legacy versions without model definitions still have explicit local identities.
    # Only known face/state aliases are folded; unknown extensions stay labelled as such.
    for groups,path,name,paths in texture_entries(source,full,item_index):
        code=aliases.get(path,path.split('/textures/')[-1].removesuffix('.png'))
        if not introduced(code,version,available):continue
        namespace=path.split('/')[1] if path.startswith('assets/') else 'minecraft'
        identity=texture_identity(path,aliases)
        if path in covered and (namespace,identity) not in rows and not identity.startswith(('entity/','models/armor/')):continue
        key=(namespace,identity)
        recognized=category(identity,path,full,version)
        # Sky properties can explicitly reference a texture outside the usual sky directory.
        groups=groups if groups[0]=='天空' or groups[:2]==('贴图','天空') else recognized
        if groups is None or groups[0]=='其他':continue
        row=rows.setdefault(key,{'id':namespace+':'+identity,'name':chinese_name(identity,path,namespace) if '/' in identity else name,'category':groups,'paths':set(),'preview':path,'state_roots':[]})
        selected,_=graph.closure(paths,include_callers=False)
        row['paths'].update(selected & source.files.keys());row['paths'].update(paths)
    result=[];names=local_names(source.files);english=local_names(source.files,'en')
    for row in rows.values():
        namespace,identity=row['id'].split(':',1)
        associated,_=graph.closure(object_entity_paths(source,identity,namespace),include_callers=False)
        row['paths'].update(associated & source.files.keys())
        row['name']=chinese_name(identity,row['preview'],namespace,names)
        row['name_en']=english_name(identity,row['preview'],namespace,english)
        row['paths']=sorted(p for p in row['paths'] if p in source.files)
        row['texture_states']=legacy_states(row) if not row['state_roots'] else []
        candidates=states(source,version,row,graph=graph)
        # One default representation is the object itself, not a useful expandable choice.
        row['resolved_states']=candidates if len(candidates)>1 else []
        if row['category'][0]!='其他' and any(p.lower().endswith('.png') for p in row['paths']):result.append(row)
    counts=Counter(row['category'] for row in result)
    for row in result:
        group=row['category']
        if group[0] in ('工具','工具与实用物品') and len(group)>1 and group[-1]!='交通运输' and counts[group]<=2:
            row['category']=group[:-1]
    result.sort(key=lambda row:(row['category'],row['name'],row['id']))
    _cache[source.uid]=(signature,result);_cache.move_to_end(source.uid)
    while len(_cache)>4:_cache.popitem(last=False)
    _graphs[source.uid]=graph
    for uid in list(_graphs):
        if uid not in _cache:del _graphs[uid]
    return result


def legacy_states(row):
    """Only explicit texture-state suffixes, for packs predating blockstate models."""
    if ':block/' not in row['id']:return []
    groups=defaultdict(set);aliases=identities()[0];labels={}
    for path in row['paths']:
        if not path.lower().endswith('.png'):continue
        stem=aliases.get(path,path).rsplit('/',1)[-1].removesuffix('.png')
        title=None
        if row['id'].endswith(':block/anvil'):
            if stem in ('anvil_top','anvil_top_damaged_0','anvil_top_intact'):title='完好'
            elif stem in ('chipped_anvil_top','anvil_top_damaged_1','anvil_top_damaged'):title='轻度损坏'
            elif stem in ('damaged_anvil_top','anvil_top_damaged_2','anvil_top_very_damaged'):title='严重损坏'
        match=re.search(r'_stage_?(\d+)$',stem)
        if match:title='生长阶段 '+match[1]
        if title:groups[title].add(path)
    state_paths=set().union(*groups.values()) if groups else set()
    shared=set(row['paths'])-state_paths
    for title,paths in groups.items():labels[title]={'id':'texture:'+title,'name':title,'paths':sorted(shared|paths),'preview':min(paths),'models':[],'condition':title,'root':'旧版明确贴图状态','multipart':False}
    return list(labels.values())


def states(source,version,descriptor,graph=None):
    """Expand only the chosen object's variants, preserving real config conditions."""
    if descriptor.get('texture_states'):return descriptor['texture_states']
    if graph is None:graph=_graphs.get(source.uid)
    if graph is None:
        combined=dict(vanilla(version));combined.update(source.files);graph=ResourceGraph(combined).parse()
    output=[];roots=descriptor.get('state_roots',[])
    for root in roots:
        try:data=json.loads(graph.files[root])
        except (ValueError,TypeError,KeyError):continue
        if not isinstance(data,dict):continue
        variants=data.get('variants',{})
        choices=[(condition,value,False) for condition,value in variants.items()] if isinstance(variants,dict) else []
        for part in data.get('multipart',[]):
            if not isinstance(part,dict):continue
            when=part.get('when',{})
            choices.append((when,part.get('apply',{}),True))
        for index,(condition,value,multipart) in enumerate(choices):
            options=value if isinstance(value,list) else [value]
            models=[graph.resource(root,opt.get('model'),'models','.json') for opt in options if isinstance(opt,dict)]
            models=[p for p in models if p]
            local,_=graph.closure(models,include_callers=False);local=local & source.files.keys()
            pictures=sorted(p for p in local if p.lower().endswith('.png'))
            if not pictures:continue
            name=state_name(condition)
            if multipart:name='连接部件 · '+name
            if len(roots)>1:name=chinese_name('block/'+root.rsplit('/',1)[1][:-5],pictures[0],root.split('/')[1])+' · '+name
            output.append({'id':root+':'+str(index),'name':name,'paths':sorted(local),'preview':pictures[0],
                           'models':models,'condition':json.dumps(condition,ensure_ascii=False) if isinstance(condition,dict) else condition,'root':root,'multipart':multipart})
    return output
