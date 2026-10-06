# -*- coding: utf-8 -*-
"""
DrawSeq_dialog.py
Setup dialog — loads DrawSeq_dialog.ui and exposes helper getters.
"""

import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QCompleter, QComboBox
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsMapLayer

# Load the .ui file at import time
FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'DrawSeq_dialog.ui')
)

HELP_TEXT = """\
<h3>🗺️ Quick Guide: DrawSeq Tool</h3>
<p>Draw lines across map features to automatically assign them sequence numbers.</p>

<h4>Drawing Controls</h4>
<ul>
  <li><b>Left-Click</b> — Add a point to your line.</li>
  <li><b>Backspace / Ctrl+Z</b> — Undo the last point.</li>
  <li><b>Right-Click</b> — Finish the current line and open the Review Dialog.</li>
</ul>

<h4>Editing Lines</h4>
<ul>
  <li><b>Add a Point</b> — Double-click anywhere on a line segment to add a new vertex.</li>
  <li><b>Move a Point</b> — Left-click and drag any vertex to adjust the line.</li>
  <li><b>Flip Direction</b> — Middle-click the line (or double-click the black triangles) to instantly reverse the numbering direction.</li>
</ul>

<h4>Saving & Fields</h4>
<ul>
  <li><b>Target Field</b> — In the Review Dialog, you can select an existing field from the dropdown or type a brand new field name to save your numbers into.</li>
  <li><b>Reuse</b> — Click "Reuse" to save your numbers but keep the lines on the map so you can run them again for a different field.</li>
</ul>
"""


class SetupDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._setup_autocomplete()

        self.layerComboBox.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.LayerType.VectorLayer:
                self.layerComboBox.addItem(layer.name(), layer.id())

        self.startDrawingButton.clicked.connect(self.accept)
        self.helpButton.clicked.connect(self._show_help)

    def _setup_autocomplete(self):
        """Make combo box searchable."""
        self.layerComboBox.setEditable(True)
        self.layerComboBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        layer_completer = self.layerComboBox.completer()
        if layer_completer:
            layer_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            layer_completer.setFilterMode(Qt.MatchFlag.MatchContains)

    def _show_help(self):
        """Display the quick-guide."""
        dlg = QMessageBox(self)
        dlg.setWindowTitle("DrawSeq — Quick Guide")
        dlg.setTextFormat(Qt.TextFormat.RichText)
        dlg.setText(HELP_TEXT)
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        dlg.exec()

    def get_layer_id(self) -> str:
        idx = self.layerComboBox.currentIndex()
        return self.layerComboBox.itemData(idx) if idx >= 0 else None

    def get_selected_only(self) -> bool:
        return self.selectedOnlyCheckBox.isChecked()
