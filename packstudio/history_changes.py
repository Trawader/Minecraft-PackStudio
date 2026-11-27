"""UID-based, session-local undo for library additions and cascading deletions."""
from functools import wraps
from .resource_history import restore

LIMIT=256*1024*1024

def snapshot(w):
    return {name:{item.uid:w.clone_layer(item) for item in getattr(w,name)} for name in ('sources','layers')}

def difference(before,after):
    return {name:{uid:(before[name].get(uid),after[name].get(uid)) for uid in before[name].keys()|after[name].keys() if before[name].get(uid)!=after[name].get(uid)} for name in before}

def size(changes):
    values={id(raw):raw for group in changes.values() for pair in group.values() for item in pair if item is not None for raw in item.files.values()}
    return sum(map(len,values.values()))

def install_state(w,changes,side,order):
    for name,group in changes.items():
        current={item.uid:item for item in getattr(w,name)}
        for uid,pair in group.items():
            target=pair[side]
            if target is None:current.pop(uid,None)
            elif uid in current:restore(current[uid],target)
            else:current[uid]=w.clone_layer(target)
        ids=[uid for uid in order[name] if uid in current]+[uid for uid in current if uid not in order[name]]
        setattr(w,name,[current[uid] for uid in ids])

def persist(w,changes,side):
    for uid,pair in changes['sources'].items():
        if pair[side] is None:w.library_store.remove(uid)
        else:w.library_store.put(pair[side])

def apply(w,entry,redo):
    changes=entry['changes'];expected=0 if redo else 1;target=1-expected
    for name,group in changes.items():
        current={item.uid:item for item in getattr(w,name)}
        for uid,pair in group.items():
            if current.get(uid)!=pair[expected]:raise ValueError('资源身份或内容已变化，回滚已停止：'+uid)
    w.library_store.flush()
    try:persist(w,changes,target)
    except Exception:
        persist(w,changes,expected)
        raise
    w.clear_editor();install_state(w,changes,target,entry['order'][target])
    w.selected_asset=None
    for record in list(w.browsers):
        if record['uid'] and not w.source('stage:'+record['uid']):w.close_browser(record)
    if changes['layers']:w.changed()
    w.refresh()

def grouped(label):
    def decorate(fn):
        @wraps(fn)
        def call(w,*args,**kwargs):
            history=getattr(w,'operation_history',None)
            if history is None or history.busy:return fn(w,*args,**kwargs)
            history.flush();w.library_store.flush()
            before=snapshot(w);old_history=list(w.resource_history)
            orders={name:list(items) for name,items in before.items()}
            history.busy=True
            try:
                result=fn(w,*args,**kwargs)
                after=snapshot(w);changes=difference(before,after)
            except Exception:
                changes=difference(before,snapshot(w))
                # Restore both the material and its linked project copies on failure.
                install_state(w,changes,0,orders)
                persist(w,changes,0);w.refresh()
                raise
            finally:
                w.resource_history=old_history;history.busy=False
            if any(changes.values()):
                cost=size(changes)
                if cost>LIMIT:
                    history.append(dict(kind='blocked',label=label,reason='暂存内容超过 256 MiB，无法回滚'))
                else:
                    history.append(dict(kind='group',label=label,changes=changes,cost=cost,order=(orders,{name:list(items) for name,items in after.items()})))
            return result
        return call
    return decorate
