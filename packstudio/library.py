"""Persistent, self-contained asset copies; original paths are provenance only."""
import logging
import uuid
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .core import load_project,save_project

class LibraryStore:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.pending={};self.job=None;self.executor=None
    def path(self,uid):return self.root/(uuid.UUID(uid).hex+'.packstudio')
    def load(self):
        self.flush()
        result=[]
        for path in sorted(self.root.glob('*.packstudio')):
            try:
                layers,_=load_project(path)
                if layers:result.append(layers[0])
            except Exception:logging.exception('Cannot read library copy %s',path)
        return result
    def queue(self,layer):
        # Metadata and mapping are independent; immutable PNG bytes are shared.
        self.pending[layer.uid]=copy.deepcopy(layer)
    def finish(self,wait=False):
        if self.job is None:return
        uid,layer,future=self.job
        if not wait and not future.done():return
        self.job=None
        try:future.result()
        except Exception:
            self.pending.setdefault(uid,layer)
            raise
    def start(self):
        self.finish()
        if self.job is None and self.pending:
            uid=next(iter(self.pending));layer=self.pending.pop(uid)
            if self.executor is None:self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='library-save')
            future=self.executor.submit(save_project,self.path(uid),[layer],'1.8.9')
            self.job=(uid,layer,future)
        return bool(self.pending or self.job)
    def flush(self):
        self.finish(wait=True)
        for uid,layer in list(self.pending.items()):
            save_project(self.path(uid),[layer],'1.8.9')
            self.pending.pop(uid)
    def put(self,layer):
        self.finish(wait=True)
        save_project(self.path(layer.uid),[layer],'1.8.9')
        self.pending.pop(layer.uid,None)
    def remove(self,uid):
        self.finish(wait=True)
        self.path(uid).unlink(missing_ok=True)
        self.pending.pop(uid,None)
    def close(self):
        self.flush()
        if self.executor is not None:self.executor.shutdown(wait=True);self.executor=None
