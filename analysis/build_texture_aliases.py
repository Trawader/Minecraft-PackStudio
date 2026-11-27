"""Precompute unambiguous texture aliases from adjacent vanilla snapshots."""
import json,collections
from pathlib import Path
root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'packstudio/data/version_catalog.json').read_text(encoding='utf-8'))
versions=list(catalog['versions']);edges=[]
# Keep the evidence pairs used by released versions. Inserting an intermediate
# texture overhaul must not erase a previously verified byte-identical rename.
anchors=('1.7.10','1.8.9','1.9.4','1.12.2','1.13.2','1.16.5','1.20.1','1.20.6','1.21.11','26.2','26.3')
pairs=dict.fromkeys([*zip(anchors,anchors[1:]),*zip(versions,versions[1:])])
for before,after in pairs:
    indexes=[]
    for v in (before,after):
        index=collections.defaultdict(list)
        for path,entry in catalog['versions'][v]['files'].items():
            if path.endswith('.png') and any('/textures/'+category+'/' in path for category in ('blocks','block','items','item')):index[entry['sha256']].append(path)
        indexes.append(index)
    for digest,paths in indexes[0].items():
        targets=indexes[1].get(digest,[])
        if len(paths)==len(targets)==1 and paths[0]!=targets[0]:
            edges.append(dict(source=paths[0],target=targets[0],versions=[before,after],evidence='unique identical vanilla bytes'))
for stem in ('quartz_pillar','purpur_pillar'):
    edges.append(dict(source=f'assets/minecraft/textures/block/{stem}.png',target=f'assets/minecraft/textures/block/{stem}_side.png',versions=['1.21.11','26.2'],evidence='Mojang 26.2 release notes'))
(root/'packstudio/data/texture_aliases.json').write_text(json.dumps(edges,ensure_ascii=False,indent=2),encoding='utf-8')
print(len(edges),'version alias edges')
