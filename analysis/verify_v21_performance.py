"""V2.1 correctness and performance checks using isolated settings and real samples."""
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QImage
from packstudio.core import decode,png,import_pack,pixel_rect,Layer,load_project
from packstudio.studio import StudioWindow
from packstudio.image_cache import images,ImageCache
from packstudio.semantics import parts
from packstudio import library

app=QApplication([])
report={}
def timed(action,n=5):
    durations=[]
    for _ in range(n):
        start=time.perf_counter();action();durations.append(round((time.perf_counter()-start)*1000,3))
    return {'median_ms':statistics.median(durations),'runs_ms':durations}

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='v21-performance-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=str(Path(tmp)/'settings.ini')
    os.environ['PACKSTUDIO_NAMING_FILE']=str(Path(tmp)/'names.json')
    w=StudioWindow(Path(tmp)/'library',drafts=False)
    try:
        w.defaults.setChecked(False)
        source=import_pack(ROOT/'test/b1ue 128x.zip');w.sources=[source]
        report['first_index_and_tree']=timed(w.refresh,1)
        report['warm_tree_refresh']=timed(w.refresh)
        assert len(w.tree_items)==1
        index=w._library_index;builds=index.index_builds
        root=w.tree.topLevelItem(0)
        report['expand_root']=timed(lambda:(root.setExpanded(False),root.setExpanded(True)))
        assert index.index_builds==builds and len(w.tree_items)<20
        report['search_icons_first']=timed(lambda:w.search.setText('icons'),1)
        report['search_icons_warm']=timed(lambda:(w.search.clear(),w.search.setText('icons')))
        assert all('icons' in d['path'] or d['kind'] in ('root','folder')
                   for i in w.tree_items.values() if (d:=i.data(0,Qt.ItemDataRole.UserRole)))
        w.search.clear();assert w.tree.topLevelItem(0).isExpanded()
        # Directory matches must be usable without prebuilding their descendants.
        w.search.setText('blocks')
        folder=next(i for i in w.tree_items.values() if (i.data(0,Qt.ItemDataRole.UserRole) or {}).get('path','').endswith('/blocks'))
        assert folder.childCount()==0
        folder.setExpanded(True);assert folder.childCount()>100
        w.search.clear()
        # Changed path keys rebuild once; ordinary byte edits reuse the path index.
        source.files['custom/new.txt']=b'one';w.refresh();assert index.index_builds==builds+1
        source.files['custom/new.txt']=b'two';w.refresh();assert index.index_builds==builds+1
        source.files.pop('custom/new.txt');w.refresh()

        icons='assets/minecraft/textures/gui/icons.png'
        heart=next(p for p in parts(icons,'1.8.9') if p['code'].endswith('/heart/full'))
        crosshair=next(p for p in parts(icons,'1.8.9') if 'crosshair' in p['code'])
        def descriptor(part):return {'origin':source.uid,'path':icons,'kind':'component','name':part['name'],'regions':part['regions']}
        w.edit_descriptor(descriptor(heart));original=QImage(w.canvas.image)
        assert w.canvas.regions and w.canvas.image.size()==decode(source.files[icons]).size()
        misses=images.misses
        report['component_roundtrip']=timed(lambda:(w.edit_descriptor(descriptor(crosshair)),w.edit_descriptor(descriptor(heart))))
        report['component_roundtrip_decode_misses']=images.misses-misses
        assert images.misses==misses
        # Editing a visible pixel modifies precisely the original atlas coordinate.
        rect=pixel_rect(heart['regions'][0],original);x,y=rect[:2]
        w.canvas.checkpoint();w.canvas.set_pixel((1,1),QColor('magenta'));w.commit_canvas()
        assert decode(source.files[icons]).pixelColor(x+1,y+1)==QColor('magenta')
        assert decode(source.files[icons]).pixelColor(0,0)==original.pixelColor(0,0)
        w.edit_descriptor(descriptor(crosshair));w.edit_descriptor(descriptor(heart))
        assert w.canvas.history, 'Region switch discarded atlas undo history'
        w.canvas.undo();assert decode(source.files[icons]).pixelColor(x+1,y+1)==original.pixelColor(x+1,y+1)
        w.canvas.redo();assert decode(source.files[icons]).pixelColor(x+1,y+1)==QColor('magenta')
        replacement=QImage(w.canvas.view_size(),QImage.Format.Format_ARGB32);replacement.fill(QColor('cyan'))
        w.canvas.replace_view(replacement);w.commit_canvas()
        assert decode(source.files[icons]).pixelColor(x,y)==QColor('cyan')
        assert decode(source.files[icons]).pixelColor(0,0)==original.pixelColor(0,0)
        # Cache hits cannot be mutated through another caller, including QPainter writes.
        a=decode(source.files[icons]);b=decode(source.files[icons]);a.setPixelColor(0,0,QColor('yellow'))
        assert b.pixelColor(0,0)!=QColor('yellow')
        cache=ImageCache(1024)
        for n in range(20):
            im=QImage(8,8,QImage.Format.Format_ARGB32);im.fill(QColor(n,0,0));cache.put(bytes([n]),im)
        assert cache.bytes<=cache.budget and len(cache.entries)<20

        w.library_store.flush()
        with patch.object(library,'save_project',wraps=library.save_project) as save:
            def strokes():
                for n in range(5):
                    w.canvas.set_pixel((0,0),QColor(n,0,0));w.commit_canvas()
            report['five_strokes_in_memory']=timed(strokes,1)
            assert save.call_count==0
            report['coalesced_library_save']=timed(w.library_store.flush,1)
            assert save.call_count==1
            report['five_strokes_disk_writes']=save.call_count
        loaded=load_project(w.library_store.path(source.uid))[0][0]
        assert loaded.files==source.files
        # A failed flush retains pending content for a successful retry.
        w.library_store.queue(source)
        with patch.object(library,'save_project',side_effect=OSError('simulated save failure')):
            try:w.library_store.flush()
            except OSError:pass
            else:raise AssertionError('Save failure was hidden')
        assert source.uid in w.library_store.pending
        w.library_store.flush();assert not w.library_store.pending
        # Save and remove synchronize the worker so an old snapshot cannot reappear.
        tiny=Layer('worker',{'note.txt':b'old'})
        w.library_store.queue(tiny);assert w.library_store.start()
        tiny.files['note.txt']=b'new';w.library_store.queue(tiny);w.library_store.flush()
        assert load_project(w.library_store.path(tiny.uid))[0][0].files['note.txt']==b'new'
        w.library_store.queue(tiny);w.library_store.start();w.library_store.remove(tiny.uid)
        assert not w.library_store.path(tiny.uid).exists() and tiny.uid not in w.library_store.pending

        # Paint only the requested pixel region; identical hover positions emit nothing.
        w.canvas.zoom=8;w.canvas.offset=QPointF(16,16);w.canvas.set_tool('pencil');w.canvas.color=QColor('red')
        with patch.object(w.canvas,'update',wraps=w.canvas.update) as update:
            w.canvas.stroke((0,0),(1,1))
            assert update.call_count==1 and len(update.call_args.args)==1
            assert update.call_args.args[0].width()<w.canvas.width()
        with patch.object(w.canvas,'update',wraps=w.canvas.update) as update:
            w.canvas.set_hover((0,0));count=update.call_count;w.canvas.set_hover((0,0));assert update.call_count==count
        w.canvas.grab().save(str(ROOT/'.tmp/v21-atlas-canvas.png'))
        other=Layer('second source',{icons:source.files[icons]})
        w.sources.append(other);w.refresh()
        w.library_search_scope={'origin':source.uid,'path':''}
        w.search.setText('icons')
        origins={i.data(0,Qt.ItemDataRole.UserRole)['origin'] for i in w.tree_items.values()
                 if i.data(0,Qt.ItemDataRole.UserRole).get('kind')=='png'}
        assert origins=={source.uid,other.uid}, 'Selecting a source restricted global search'
        report['status']='PASS'
        report['scope']='Offscreen CPU timings; warm/cold paths labeled separately; no game validation.'
    finally:
        w.dirty=False;w.close()

(ROOT/'analysis/v21-performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
