import sys
import logging
import faulthandler
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImageReader,QIcon
from packstudio.studio import StudioWindow
from packstudio.core import ROOT
from packstudio.release import VERSION,APP_TITLE,EXECUTABLE_NAME

def main():
    logs=ROOT/'.tmp';logs.mkdir(exist_ok=True)
    logging.basicConfig(filename=logs/'editor-errors.log',level=logging.ERROR,format='%(asctime)s %(levelname)s %(message)s')
    crash_log=(logs/'native-crash.log').open('a',encoding='utf-8')
    QImageReader.setAllocationLimit(640)
    app=QApplication(sys.argv)
    faulthandler.enable(crash_log)
    app.setApplicationName(EXECUTABLE_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(VERSION)
    icon_path=Path(__file__).parent/'packstudio/assets/mcps.ico'
    app.setWindowIcon(QIcon(str(icon_path)))
    if '--check-install' in sys.argv:
        import json
        from packstudio.core import Vanilla
        from packstudio.models import ModelLibrary
        from packstudio.appearance import tool_icon
        vanilla=Vanilla();models=ModelLibrary(vanilla)
        from packstudio.versions import VERSIONS
        counts={version:len(vanilla.paths(version)) for version in VERSIONS}
        assert all(counts.values()),'Missing vanilla resources'
        assert len(models.xml)>=48,'Missing entity models'
        assert not tool_icon('pencil').isNull(),'Missing toolbar assets'
        assert not app.windowIcon().isNull(),'Missing application icon'
        window=StudioWindow(drafts=False)
        assert window.windowTitle().startswith(APP_TITLE)
        window.dirty=False;window.close()
        (ROOT/'install-check.json').write_text(json.dumps({'resources':counts,'models':len(models.xml),'status':'ok'},indent=2),encoding='utf-8')
        faulthandler.disable();crash_log.close();return 0
    window=StudioWindow()
    def report_error(kind,error,trace):
        logging.error('Unhandled UI exception',exc_info=(kind,error,trace))
        window.statusBar().showMessage('操作异常，工程仍保留。可保存工程后重试；详情已写入错误日志。')
    sys.excepthook=report_error
    window.show()
    try:return app.exec()
    finally:faulthandler.disable();crash_log.close()

if __name__=='__main__':
    sys.exit(main())
