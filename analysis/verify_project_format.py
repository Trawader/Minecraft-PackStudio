"""Project menu terminology, native project suffix and legacy reads."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QFileDialog,QScrollArea
from PySide6.QtGui import QDesktopServices
from packstudio.studio import StudioWindow
from packstudio.core import Layer,save_project,load_project
from packstudio.localization import catalog
app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='mcpsd-') as tmp:
    os.environ['PACKSTUDIO_SETTINGS_FILE']=tmp+'/settings.ini'
    w=StudioWindow(Path(tmp)/'library',drafts=False);w.show();app.processEvents()
    try:
        actions=w.menuBar().actions();assert actions[0].text()=='项目'
        assert actions.index(w.window_menu.menuAction())<actions.index(w.settings_action)
        assert w.settings_action.menu() is None
        w.settings_action.trigger();assert w.settings_dialog.isVisible();w.settings_dialog.hide()
        menu=actions[0].menu();assert len(menu.actions())==5
        assert all(not a.isSeparator() and '工程' not in a.text() and 'ZIP' not in a.text() for a in menu.actions())
        assert w.docks['render'].widget().frameShape()==QScrollArea.Shape.NoFrame
        assert w.project_split.layout() is not None
        with patch.object(QDesktopServices,'openUrl',return_value=True) as open_url:
            w.open_project_folder();url=open_url.call_args.args[0];assert Path(url.toLocalFile())==ROOT/'projects'
        layer=Layer('example',{'assets/demo/readme.txt':b'unchanged'});w.layers=[layer]
        dest=Path(tmp)/'sample'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(dest),'Project file (*.MCPSD)')) as save:
            w.save_as();assert '*.MCPSD' in save.call_args.args[3]
        assert w.project_path==dest.with_suffix('.MCPSD')
        w.read_project(w.project_path);assert w.layers[0].files==layer.files
        legacy=Path(tmp)/'old.packstudio';save_project(legacy,[layer],'1.8.9');w.read_project(legacy)
        assert w.layers[0].files==layer.files
        w.language_changed(1);app.processEvents();w.localizer.refresh()
        assert w.menuBar().actions()[0].text()=='Project'
        assert w.settings_action.text()=='Settings'
        assert all(not any('\u4e00'<=c<='\u9fff' for c in a.text()) for a in menu.actions())
        assert not any('工程' in k for k in catalog())
        for removed in ('偏好设置…','设为选择器来源','加入项目（创建副本）','筛选'):
            assert removed not in catalog()
        print('PASS project menu/settings, frameless fixed regions, project directory, MCPSD save/reopen, legacy read, English and retired catalog entries')
    finally:w.dirty=False;w.close();app.processEvents()

