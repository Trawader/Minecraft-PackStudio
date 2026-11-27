"""Minimal menus retain export capabilities and automatic selector source."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from unittest.mock import patch
from packstudio.core import Layer,png
from packstudio.studio import StudioWindow
from packstudio.export_dialog import ExportDialog
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='compact-menus-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        assert not w.statusBar().isVisible() and not hasattr(w,'version_filter') and not hasattr(w,'version_actions')
        actions=w.menuBar().actions()[0].menu().actions();texts=[a.text() for a in actions]
        assert not any(any(term in text for term in ('关闭项目','关闭当前','草稿','报告','PNG','撤销')) for text in texts),texts
        im=QImage(16,16,QImage.Format.Format_ARGB32);im.fill(QColor('red'))
        path='assets/minecraft/textures/blocks/stone.png'
        for name in ('first','second'):
            w.add_import(Layer(name,{'pack.mcmeta':b'{"pack":{"pack_format":1,"description":"test"}}',path:png(im)},source_version='1.8.9'))
        owner=w.sources[-1];d={'origin':owner.uid,'kind':'root','path':'','name':owner.name}
        menu=w.resource_menu(d);labels=[a.text() for a in menu.actions()]
        assert labels[:5]==['加入项目','直接编辑素材','选中','替换为选中','删除素材'],labels
        assert not any('设为选择器来源' in s or '创建副本' in s for s in labels)
        assert not hasattr(w,'set_selector_source')
        item=next(w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount()) if (w.tree.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole) or {}).get('origin')==owner.uid)
        w.tree.setCurrentItem(item);w.library_mode.setCurrentIndex(1);app.processEvents()
        assert w.selector_source.currentData()==owner.uid
        w.library_mode.setCurrentIndex(0);w.vanilla_version.setCurrentIndex(w.vanilla_version.findData('1.8.9'));app.processEvents()
        assert w.tree.topLevelItemCount()==2
        w.edit_descriptor(dict(d,path=path,kind='png'));w.frontend_flow.sync();app.processEvents()
        assert w.export_png_button.isVisible() and w.export_png_button.isEnabled(), (w.export_png_button.isVisible(),w.export_png_button.isEnabled(),w.export_png_action.isEnabled(),w.current,w.canvas.image.isNull(),w.export_png_button.parentWidget())
        with patch.object(w,'export_png') as export:
            w.export_png_button.click();export.assert_called_once()
        w.add_to_composition(d);dialog=ExportDialog(w)
        assert dialog.report_button.text()=='报告与记录'
        with patch('packstudio.export_history.show') as report:
            # The connected callback is bound at construction, so recreate under patch.
            other=ExportDialog(w);other.report_button.click();report.assert_called_once_with(w);other.close()
        dialog.close();w.clear_editor();w.frontend_flow.sync();assert not w.export_png_button.isEnabled()
        print('PASS minimal File/context menus, hidden status bar, single filter, automatic selector source, PNG and report entry points')
    finally:w.dirty=False;w.close();app.processEvents()
