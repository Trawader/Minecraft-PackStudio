"""Generate immutable defaults and the public read-only version/ID reference."""
import os,sys,json,csv
from pathlib import Path
os.environ['PACKSTUDIO_BUILD_NAMES']='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from packstudio.semantics import identities,describe,parts,search_tags,variant_id
from packstudio.naming import number
from packstudio.versions import VERSIONS,records
from packstudio.adaptation import RULES_BY_SOURCE
entries={};rows=[];model_ids={}
default_path=ROOT/'packstudio/data/naming_defaults.json'
old_defaults=json.loads(default_path.read_text('utf8')) if default_path.exists() else {'entries':{}}
for version in VERSIONS:
 reverse={}
 for model,record in records(version).items():
  if '/models/' not in model:continue
  namespace=model.split('/')[1];identifier=Path(model).stem
  if '/models/item/' not in model and f'assets/{namespace}/blockstates/{identifier}.json' not in records(version):continue
  for texture in record.get('textures',{}).values():
   value=texture.get('sprite') if isinstance(texture,dict) else texture
   if not isinstance(value,str) or value.startswith('#'):continue
   if ':' not in value:value='minecraft:'+value
   reverse.setdefault(value,set()).add(namespace+':'+identifier)
 model_ids[version]=reverse
for path,code in sorted(identities()[0].items()):
 info=describe(path);tags=search_tags().get(Path(path).stem,{}).get('tags',[]) if '/particle/' in path else []
 entries.setdefault(code,{'number':number(code),'name':info['name'],'tags':tags,'include_default_search':True})
 for version in VERSIONS:
  if path not in records(version):continue
  namespace=path.split('/')[1];resource=namespace+':'+path.split('/textures/')[-1].removesuffix('.png')
  ids=model_ids[version].get(resource,set())
  rows.append([version,resource,','.join(sorted(ids)),code,number(code),variant_id(path,version),info['name'],path])
for path in RULES_BY_SOURCE:
 for version in VERSIONS:
  if path not in records(version):continue
  for part in parts(path,version):
   code=part['code'];entries.setdefault(code,{'number':number(code),'name':part['name'],'tags':search_tags().get(Path(code).name,{}).get('tags',[]),'include_default_search':True})
   rows.append([version,'minecraft:'+code,'',code,number(code),code,part['name'],path+' # '+repr(part['regions'])])
default_path.write_text(json.dumps({'schema':1,'entries':entries},ensure_ascii=False,indent=2),'utf8')
# Upgrade untouched defaults in the public copy; never overwrite player edits.
copy_path=ROOT/'config/names-and-search.json'
if '--update-public' in sys.argv and copy_path.exists():
 try:
  public=json.loads(copy_path.read_text('utf-8-sig'))
  for code,row in list(public.get('entries',{}).items()):
   if row==old_defaults['entries'].get(code) and code in entries:public['entries'][code]=entries[code]
  copy_path.write_text(json.dumps(public,ensure_ascii=False,indent=2),'utf8')
 except (ValueError,TypeError,AttributeError):pass
with (ROOT/'docs/resource-identities.tsv').open('w',encoding='utf-8-sig',newline='') as file:
 writer=csv.writer(file,delimiter='\t');writer.writerow(['版本','贴图资源ID','物品/方块ID（模型证据）','本地语义键','固定编号','布局变体','默认名称','路径／区域']);writer.writerows(rows)
print(len(entries),'naming entries;',len(rows),'version bindings')
