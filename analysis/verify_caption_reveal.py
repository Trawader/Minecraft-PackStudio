"""Regression: caption wheel overflow and selector-to-lazy-tree navigation."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent,QImage
from packstudio.studio import StudioWindow
from packstudio.core import Layer,png

app=QApplication([])
(ROOT/'.tmp').mkdir(exist_ok=True)
def settle():
    for _ in range(30):app.processEvents()

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='caption-reveal-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini'
    os.environ['PACKSTUDIO_NAMING_FILE']=tmp+'/names.json'
    w=StudioWindow(Path(tmp)/'library',drafts=False)
    try:
        im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(Qt.GlobalColor.red)
        path='assets/minecraft/textures/item/diamond_sword.png'
        source=Layer('Test',{path:png(im),'assets/minecraft/textures/block/stone.png':png(im)},source_version='1.20.1')
        w.sources=[source];w.defaults.setChecked(False);w.refresh();w.show();settle()
        assert len(w.tree_items)==1
        w.library_mode.setCurrentIndex(1);settle()
        d={'origin':source.uid,'path':path,'kind':'png','name':'diamond_sword'}
        menu=w.resource_menu(d)
        next(a for a in menu.actions() if a.text() in ('在文件树中查看','Show in file tree')).trigger()
        settle();assert w.library_mode.currentIndex()==0
        item=w.tree.currentItem();assert item.data(0,Qt.ItemDataRole.UserRole)['path']==path and item.isSelected()
        parent=item.parent()
        while parent is not None:
            assert parent.isExpanded();parent=parent.parent()
        assert w.tree.viewport().rect().intersects(w.tree.visualItemRect(item))
        other=w._library_index.rows.get((source.uid,'assets/minecraft/textures/block'))
        assert other is None or not other.isExpanded()
        for language in ('zh','en'):
            w.lang=language
            for width in (240,500):
                s=w.caption_scroll;s.setFixedWidth(width)
                w.caption.setText('assets/minecraft/textures/models/armor/leather_layer_2.png\nfrom '+('folder name/'*200)+'pack.zip');settle()
                assert s.verticalScrollBar().maximum()>0
                s.verticalScrollBar().setValue(0)
                point=QPointF(s.viewport().rect().center())
                event=QWheelEvent(point,point,QPoint(),QPoint(0,-120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
                app.sendEvent(s.viewport(),event);assert s.verticalScrollBar().value()>0
                w.caption.setText('short');settle();assert s.verticalScrollBar().maximum()==0
        print('PASS: selector menu reveals unloaded PNG, opens ancestors and scrolls into view; caption wheel and long/short reset in both languages.')
    finally:
        w.dirty=False;w.close();settle()
