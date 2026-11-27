"""OGG resource identities and conservative sounds.json composition."""
import copy,json,re


def is_audio(path):return path.lower().endswith('.ogg')
def is_definition(path):return bool(re.fullmatch(r'assets/[^/]+/sounds\.json',path))


def parse(raw,path):
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('重复键：'+key)
            result[key]=value
        return result
    try:
        value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs)
        if not isinstance(value,dict):raise ValueError('根节点必须为对象')
        for name,event in value.items():
            if not isinstance(event,dict) or not isinstance(event.get('sounds',[]),list):raise ValueError(name+'：sounds 必须为列表')
            if 'replace' in event and type(event['replace']) is not bool:raise ValueError(name+'：replace 必须为布尔值')
        return value
    except (ValueError,UnicodeError,AttributeError) as error:raise ValueError(path+'：声音定义无法解析：'+str(error)) from error


def merge(lower,upper,path):
    if lower==upper:return upper
    low=parse(lower,path);high=parse(upper,path);result=copy.deepcopy(low)
    for name,event in high.items():
        if name not in low or event==low[name] or event.get('replace',False):
            result[name]=copy.deepcopy(event);continue
        base=low[name]
        conflicts=[k for k in base.keys() & event.keys() if k not in ('sounds','replace') and base[k]!=event[k]]
        if conflicts:raise ValueError(f'{path} / {name}：声音定义冲突（{", ".join(conflicts)}）。请调整声音定义或项目顺序；不会静默丢弃引用。')
        merged={**base,**event};merged['sounds']=copy.deepcopy(base.get('sounds',[])+event.get('sounds',[]))
        if base.get('replace') or event.get('replace'):merged['replace']=True
        result[name]=merged
    return json.dumps(result,ensure_ascii=False,indent=2).encode('utf8')


def composed_definitions(layers):
    result={}
    for layer in reversed(layers):
        if not layer.enabled or layer.kind=='component':continue
        for path,raw in layer.files.items():
            if is_definition(path):result[path]=merge(result[path],raw,path) if path in result else raw
    return result


def references(path,raw):
    """Return file/event references, keeping unsupported syntax explicit."""
    data=parse(raw,path);rows=[]
    for event,definition in data.items():
        for sound in definition.get('sounds',[]):
            value=sound if isinstance(sound,str) else sound.get('name') if isinstance(sound,dict) else None
            kind=sound.get('type','file') if isinstance(sound,dict) else 'file'
            if not isinstance(value,str) or kind not in ('file','event'):raise ValueError(path+' / '+event+'：未知声音引用格式')
            namespace,separator,name=value.partition(':')
            if not separator:namespace,name='minecraft',namespace
            if not re.fullmatch(r'[a-z0-9_.-]+',namespace) or not re.fullmatch(r'[a-z0-9_./-]+',name) or name.startswith('/') or '..' in name.split('/'):
                raise ValueError(path+' / '+event+'：无效声音引用 '+value)
            target=f'assets/{namespace}/sounds/{name}.ogg' if kind=='file' else f'assets/{namespace}/sounds.json'
            rows.append((event,target,kind,name))
    return rows


def reference_issues(files):
    issues=[];events={};links={}
    for path,raw in files.items():
        if not is_definition(path):continue
        try:
            events[path]=parse(raw,path)
            for event,target,kind,name in references(path,raw):
                if kind=='event':links.setdefault((path,event),[]).append((target,name))
                elif target not in files:issues.append({'path':path,'action':'sound_unverified','detail':'声音文件不在导出包中：'+target+'；可能依赖原版音效，当前未核实原版回退。'})
        except ValueError as error:issues.append({'path':path,'action':'sound_unverified','detail':str(error)+'；原文件保留。'})
    for (path,event),targets in links.items():
        for target,name in targets:
            if name not in events.get(target,{}):issues.append({'path':path,'action':'sound_unverified','detail':event+' 引用的声音事件未在包内找到：'+target+' / '+name+'；原版回退未核实。'})
    # Detect cycles without recursively traversing arbitrary user configuration.
    for start in links:
        todo=list(links[start]);seen=set()
        while todo:
            node=todo.pop()
            if node==start:
                issues.append({'path':start[0],'action':'sound_unverified','detail':'声音事件循环引用：'+start[1]});break
            if node not in seen:seen.add(node);todo.extend(links.get(node,()))
    return issues
