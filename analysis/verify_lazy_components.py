"""Collapsed atlases stay undecoded; expansion/search still expose real components."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from packstudio.core import import_pack
from packstudio.studio import StudioWindow
from packstudio import library_browser

app = QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='lazy-components-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE'] = str(Path(tmp) / 'settings.ini')
    os.environ['PACKSTUDIO_NAMING_FILE'] = str(Path(tmp) / 'names.json')
    w = StudioWindow(Path(tmp) / 'library', drafts=False)
    try:
        source = import_pack(ROOT / 'test/b1ue 128x.zip')
        w.sources = [source]
        w.defaults.setChecked(False)
        with patch.object(library_browser, 'decode', wraps=library_browser.decode) as decoder:
            w.refresh()
            assert decoder.call_count == 0, 'Collapsed tree decoded component thumbnails'
            assert len(w.tree_items)==1, 'Collapsed source eagerly created file rows'
            for path in source.files:
                if path.endswith(('/gui/container/furnace.png','/gui/icons.png')):
                    w.tree_items[w.descriptor_key({'origin':source.uid,'path':path,'kind':'png'})]
            candidates = [i for i in w.tree_items.values()
                          if (i.data(0, Qt.ItemDataRole.UserRole) or {}).get('kind') == 'png'
                          and i.childIndicatorPolicy() == i.ChildIndicatorPolicy.ShowIndicator]
            assert candidates and all(i.childCount() == 0 for i in candidates)
            for suffix in ('/gui/container/furnace.png', '/gui/icons.png'):
                atlas = next(i for i in candidates if i.data(0, Qt.ItemDataRole.UserRole)['path'].endswith(suffix))
                before = decoder.call_count
                atlas.setExpanded(True)
                assert atlas.childCount() > 0
                calls = decoder.call_count
                assert calls == before + 1
                atlas.setExpanded(False)
                atlas.setExpanded(True)
                assert decoder.call_count == calls, 'Re-expansion regenerated existing components'
        w.search.setText('准心')
        assert any(not i.isHidden() and (i.data(0, Qt.ItemDataRole.UserRole) or {}).get('kind') == 'component'
                   for i in w.tree_items.values())
        w.search.clear()
        w.library_mode.setCurrentIndex(1)
        w.library_mode.setCurrentIndex(0)
        w.refresh()
        assert all(i.data(0, Qt.ItemDataRole.UserRole) for i in w.tree_items.values())
    finally:
        w.dirty = False
        w.close()
print('PASS collapsed decode avoidance, lazy expansion, reuse, component search and mode switching')
