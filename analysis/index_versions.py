"""Read-only vanilla inventory; generate reproducible local conversion evidence."""
import sys,json,hashlib,struct,collections,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'reference/各版本assets'
sys.path.insert(0,str(ROOT))
from packstudio.versions import VERSIONS,FORMATS
from version_sources import source_directory
catalog={'schema':1,'versions':{},'rename_candidates':[]}
for version in VERSIONS:
    directory=source_directory(version)
    entries={};categories=collections.Counter();ids={'blockstates':[],'items':[],'models/item':[]};errors=[]
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.name=='.mcassetsroot':continue
        name='assets/'+path.relative_to(directory).as_posix();data=path.read_bytes()
        entry={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        if data.startswith(b'\x89PNG\r\n\x1a\n'):entry['size']=list(struct.unpack('>II',data[16:24]))
        if path.suffix=='.json':
            try:
                value=json.loads(data)
                if isinstance(value,dict):
                    if 'parent' in value:entry['parent']=value['parent']
                    if 'textures' in value:entry['textures']=value['textures']
                    if 'elements' in value:entry['geometry']=hashlib.sha256(json.dumps(value['elements'],sort_keys=True).encode()).hexdigest()
            except (ValueError,UnicodeError) as error:errors.append([name,str(error)])
        entries[name]=entry;categories['/'.join(name.split('/')[2:4])]+=1
        for prefix in ids:
            if name.startswith('assets/minecraft/'+prefix+'/') and name.endswith('.json'):ids[prefix].append(name.split(prefix+'/',1)[1][:-5])
    catalog['versions'][directory.name]={'format':FORMATS.get(directory.name),'minor':1 if directory.name=='26.3' else 0,'files':entries,'categories':dict(categories),'ids':ids,'errors':errors}
    print(directory.name,len(entries),'files',flush=True)
# Unique byte-identical texture renames across the flattening boundary are evidence,
# not arbitrary fuzzy filename matches. Ambiguous hashes are deliberately excluded.
a=catalog['versions']['1.12.2']['files'];b=catalog['versions']['1.13.2']['files']
for oldcat,newcat in [('blocks','block'),('items','item')]:
    hashes=collections.defaultdict(list)
    for p,e in b.items():
        if f'/textures/{newcat}/' in p and p.endswith('.png'):hashes[e['sha256']].append(p)
    oldhashes=collections.Counter(e['sha256'] for p,e in a.items() if f'/textures/{oldcat}/' in p and p.endswith('.png'))
    for p,e in a.items():
        if f'/textures/{oldcat}/' not in p or not p.endswith('.png'):continue
        candidates=hashes[e['sha256']]
        if len(candidates)==1 and oldhashes[e['sha256']]==1:
            catalog['rename_candidates'].append({'source':p,'target':candidates[0],'evidence':'unique identical vanilla bytes: 1.12.2 -> 1.13.2'})
out=ROOT/'packstudio/data/version_catalog.json';out.write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
report=['# 本地 assets 全版本盘点','', '由 analysis/index_versions.py 逐文件生成；原始 assets 不修改。文件哈希、尺寸、模型引用和 ID 清单见 packstudio/data/version_catalog.json。','', '| 版本 | 文件 | PNG | JSON | 方块状态 ID | 新物品定义 ID | 物品模型 ID |','|---|---:|---:|---:|---:|---:|---:|']
previous=None;diffs={}
for version,record in catalog['versions'].items():
    files=record['files'];ids=record['ids'];report.append(f"| {version} | {len(files)} | {sum('size' in e for e in files.values())} | {sum(p.endswith('.json') for p in files)} | {len(ids['blockstates'])} | {len(ids['items'])} | {len(ids['models/item'])} |")
    if previous:
        old=catalog['versions'][previous]['files'];common=files.keys()&old.keys()
        diffs[previous+' -> '+version]={'added':sorted(files.keys()-old.keys()),'removed':sorted(old.keys()-files.keys()),'changed':sorted(p for p in common if old[p]['sha256']!=files[p]['sha256']),'resized':{p:[old[p].get('size'),files[p].get('size')] for p in common if old[p].get('size')!=files[p].get('size')}}
    previous=version
report+=['','## 相邻版本差异','']
for pair,diff in diffs.items():report.append(f"- {pair}：新增 {len(diff['added'])}、删除 {len(diff['removed'])}、同路径内容改变 {len(diff['changed'])}、尺寸改变 {len(diff['resized'])}。")
report+=['',f"1.12.2 → 1.13.2 唯一同字节贴图路径候选：{len(catalog['rename_candidates'])} 条。",'', '注意：资源路径、模型 ID 不等于游戏数值 ID；assets 不含完整注册表，也不含所有 Java 内置实体几何。路径相同或尺寸相同均不能单独证明 UV 兼容。']
(ROOT/'analysis/version-differences.json').write_text(json.dumps(diffs,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'docs/version-assets-analysis.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
