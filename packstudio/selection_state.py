"""Keep provenance and export decisions when selecting a subset of a source."""
import copy


def subset(source,paths):
    paths=set(paths);result=copy.deepcopy(source.selection)
    result['source_uid']=source.library_uid or result.get('source_uid') or source.uid
    for key in ('unmapped_paths','seeds','shared_textures'):
        if key in result:result[key]=[p for p in result[key] if p in paths]
    if 'export_targets' in result:
        result['export_targets']={p:t for p,t in result['export_targets'].items() if p in paths}
    if 'references' in result:
        result['references']=[row for row in result['references'] if row.get('source') in paths]
    derivation=result.get('derivation')
    if isinstance(derivation,dict) and 'target_colors' in derivation:
        derivation['target_colors']={p:color for p,color in derivation['target_colors'].items() if p in paths}
    return result


def merged(layers,paths):
    paths=set(paths);claimed=set();unmapped=[];targets={};origins=[]
    for layer in layers:
        if not layer.enabled:continue
        origins.append({'uid':layer.uid,'name':layer.name,'selection':copy.deepcopy(layer.selection)})
        if layer.kind=='component':continue
        pending=set(layer.selection.get('unmapped_paths',[]));saved=layer.selection.get('export_targets',{})
        for path in layer.files:
            if path not in paths or path in claimed:continue
            claimed.add(path)
            if path in pending:unmapped.append(path)
            if path in saved:targets[path]=saved[path]
    # Multiple input owners cannot safely be treated as one library source.
    # Keep decisions on the merged project copy and retain original provenance.
    return {'unmapped_paths':sorted(unmapped),'export_targets':targets,'merged_sources':origins}
