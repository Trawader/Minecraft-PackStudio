"""Read-only content-addressed vanilla resources, with no reference-folder dependency."""
import json,zipfile
from pathlib import Path
from functools import lru_cache
from collections import OrderedDict
from threading import RLock

@lru_cache(maxsize=1)
def store():
    path=Path(__file__).parent/'data/vanilla-assets.zip'
    if not path.is_file():raise FileNotFoundError('缺少程序内置资源 vanilla-assets.zip，请修复程序安装。')
    archive=zipfile.ZipFile(path)
    return archive,json.loads(archive.read('manifest.json'))['versions']

def paths(version):return set(store()[1].get(version,{}))

CACHE_BYTES=32*1024*1024
_blob_cache=OrderedDict()
_blob_bytes=0
_blob_lock=RLock()

def blob(key):
    global _blob_bytes
    with _blob_lock:
        if key in _blob_cache:
            _blob_cache.move_to_end(key);return _blob_cache[key]
    raw=store()[0].read('objects/'+key)
    if len(raw)<=CACHE_BYTES:
        with _blob_lock:
            if key in _blob_cache:return _blob_cache[key]
            while _blob_cache and (_blob_bytes+len(raw)>CACHE_BYTES or len(_blob_cache)>=128):
                _,old=_blob_cache.popitem(last=False);_blob_bytes-=len(old)
            _blob_cache[key]=raw;_blob_bytes+=len(raw)
    return raw

def get(version,path):
    key=store()[1].get(version,{}).get(path)
    return blob(key) if key else None
