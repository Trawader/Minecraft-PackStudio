"""Resolve preserve-format exports from the bottom pack, never the workspace."""
from .versions import VERSIONS,detect,records
from .core import compose,Layer

def bottom_pack(layers):
    return next((layer for layer in reversed(layers) if layer.enabled and layer.kind=='pack' and any(p.startswith('assets/') for p in layer.files)),None)

def target_version(layers):
    layer=bottom_pack(layers)
    if layer is None:return None
    candidates=detect(layer.files,layer.format_hint)
    floors=[]
    for path in layer.files:
        if not path.endswith('.png'):continue
        available=[v for v in VERSIONS if path in records(v)]
        if available:floors.append(VERSIONS.index(available[0]))
    floor=max(floors,default=0)
    if floor>max(VERSIONS.index(v) for v in candidates):
        # A stale pack.mcmeta must not turn modern blocks/entities into a legacy
        # base. Individual old atlases remain subject to the layout review.
        candidates=[v for v in VERSIONS[floor:] if v in detect({p:raw for p,raw in layer.files.items() if p!='pack.mcmeta'})] or [VERSIONS[floor]]
    # Shared resources alone cannot identify an era. Do not use the editor's
    # working version or an automatically assigned import fallback as evidence.
    known=any(any(p in records(v) for v in VERSIONS) for p in layer.files if p.startswith('assets/'))
    if len(candidates)==len(VERSIONS) or not known and 'pack.mcmeta' not in layer.files:return None
    if layer.source_version in candidates:return layer.source_version
    return candidates[-1] if set(candidates)<= {'1.7.10','1.8.9'} else candidates[0]

def compose_original(layers,vanilla,fallback):
    """Without an identifiable base, reconstruct each component in its own era."""
    from .versions import source_version
    files={}
    for layer in reversed(layers):
        if not layer.enabled:continue
        if layer.bindings:
            from dataclasses import replace
            for index,binding in enumerate(layer.bindings):
                part=replace(layer,files={'0':layer.files[str(index)]},target=binding['path'],regions=[binding['region']],bindings=[])
                files=compose_original([part,Layer('export base',files)],vanilla,fallback)
            continue
        version=layer.asset_versions.get(layer.target,source_version(layer,fallback))
        files,_=compose([layer,Layer('export base',files)],vanilla,version)
    return files
