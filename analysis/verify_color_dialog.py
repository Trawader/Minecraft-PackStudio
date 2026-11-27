"""Compact color picker and mutually exclusive palette in the shared visual area."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtGui import QColor,QFont,QFontDatabase
from packstudio.color_editor import ColorEditor
from packstudio.appearance import STYLE
app=QApplication([])
for name in ('segoeui.ttf','msyh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
app.setFont(QFont('Microsoft YaHei',9));app.setStyleSheet(STYLE)
d=ColorEditor(QColor(170,150,248,123));d.show();app.processEvents()
available=d.screen().availableGeometry()
print('dialog',d.size().toTuple(),'available',available.size().toTuple())
for index in (0,2,1,2,0):
    d.tabs.setCurrentIndex(index);app.processEvents()
    assert d.plane.isVisible()==(index!=2) and d.swatch_scroll.isVisible()==(index==2)
    assert d.comparison.height()==24 and not d.preview.isVisible()
    assert available.contains(d.geometry()),(available,d.geometry())
    for standard in (QDialogButtonBox.StandardButton.Ok,QDialogButtonBox.StandardButton.Cancel):
        button=d.buttons.button(standard)
        assert button.isVisible()
        assert d.rect().contains(button.mapTo(d,button.rect().center()))
    if index==2:
        d.choose_swatch(QColor('#ff8800'));assert d.color.alpha()==123 and d.hex.text()=='#FF8800'
    d.grab().save(str(ROOT/'.tmp'/('v32-color-palette.png' if index==2 else 'v32-color-compact.png')))
d.reject();print('PASS compact bounds, exclusive picker/palette, fixed comparison, visible confirmation, RGBA/HSVA/HEX synchronization')
