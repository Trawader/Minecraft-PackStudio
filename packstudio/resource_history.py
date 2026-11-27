"""Conflict-checked library changes sharing the existing resource undo entry."""
from contextlib import contextmanager
from dataclasses import dataclass
import copy


@dataclass
class LibraryChange:
    origin:str
    before:object
    after:object


@dataclass
class ProjectChange:
    before:list
    after:object=None


def remember(window):
    if hasattr(window,'operation_history'):window.operation_history.flush()
    if getattr(window,'_library_transaction',False):return
    seal(window)
    window.resource_history.append(ProjectChange([window.clone_layer(l) for l in window.layers]))
    window.resource_history=window.resource_history[-10:]


def seal(window,finalize=False):
    if window.resource_history and isinstance(window.resource_history[-1],ProjectChange) and (finalize or window.resource_history[-1].after is None):
        window.resource_history[-1].after=[window.clone_layer(l) for l in window.layers]
        if hasattr(window,'operation_history'):window.operation_history.resource(window.resource_history[-1])


def undo_project(window,entry):
    if entry.after is not None and window.layers!=entry.after:raise ValueError('项目之后已有其他修改，请先撤销后续编辑。')
    window.clear_editor();window.resource_history.pop();window.layers=[window.clone_layer(l) for l in entry.before]
    for record in list(window.browsers):
        if record['uid'] and not window.source('stage:'+record['uid']):window.close_browser(record)
    window.changed();window.refresh()
    if hasattr(window,'operation_history'):window.operation_history.external_undo(entry)


def restore(owner,snapshot):
    owner.__dict__.clear();owner.__dict__.update(copy.deepcopy(snapshot.__dict__))


@contextmanager
def transaction(window,origin):
    if hasattr(window,'operation_history'):window.operation_history.flush()
    owner=window.source(origin)
    if origin.startswith('stage:') or owner is None or getattr(window,'_library_transaction',False):
        yield;return
    before=window.clone_layer(owner);history=list(window.resource_history)
    window._library_transaction=True
    try:
        yield
        after=window.clone_layer(owner)
        window.resource_history=history
        if before!=after:
            window.resource_history.append(LibraryChange(origin,before,after))
            window.resource_history=window.resource_history[-10:]
            if hasattr(window,'operation_history'):window.operation_history.resource(window.resource_history[-1])
    except Exception:
        restore(owner,before);window.resource_history=history
        # put() writes atomically; retry restoration if an error occurred later.
        try:window.library_store.put(owner)
        except Exception:pass
        raise
    finally:window._library_transaction=False


def undo(window,entry):
    owner=window.source(entry.origin)
    if owner is None or window.is_builtin({'origin':entry.origin}):raise ValueError('来源已移除或只读')
    if owner!=entry.after:raise ValueError('此素材之后已有其他修改，请先撤销后续编辑。')
    restore(owner,entry.before)
    try:window.library_store.put(owner)
    except Exception:restore(owner,entry.after);raise
    window.resource_history.pop()
    window.clear_editor();window.refresh()
    if hasattr(window,'resource_editors'):window.resource_editors.sync()
    if hasattr(window,'operation_history'):window.operation_history.external_undo(entry)
