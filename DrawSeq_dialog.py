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
<p>Draw lines across map features to automatically assign them sequence \
numbers based on intersection order.</p>

<h4>Drawing Controls</h4>
<ul>
  <li><b>Left-Click</b> — Add a point to your line.</li>
  <li><b>Backspace / Ctrl+Z</b> — Undo the last point.</li>
  <li><b>Right-Click</b> — Finish the current line (locks it in with a unique colour).</li>
</ul>

<h4>Editing Finished Lines</h4>
<ul>
  <li><b>Move a Point</b> — Left-click and hold a vertex to drag it.</li>
  <li><b>Add a Point</b> — Double-click anywhere on a line segment.</li>
  <li><b>Reverse Line Direction</b> — Double-click directly on a black midpoint triangle, OR Middle-click (scroll wheel) anywhere on the line, to flip the entire line's numbering direction (e.g., A → B → C becomes A ← B ← C).</li>
</ul>

<h4>Finalising</h4>
<ul>
  <li><b>Right-Click (when not drawing)</b> — Opens the Review Dialog.</li>
  <li>Check feature counts, set starting numbers, and click <b>OK</b> to \
automatically populate the chosen field.</li>
</ul>
"""


class SetupDialog(QDialog, FORM_CLASS):
    """
    The initial setup dialog shown when the user clicks the DrawSeq toolbar button.
    Populated with all vector layers in the current project.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._setup_autocomplete()

        # Connect layer change to field update
        self.layerComboBox.currentIndexChanged.connect(self._update_fields)

        # Populate the layer combo-box
        self.layerComboBox.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                self.layerComboBox.addItem(layer.name(), layer.id())

        # Wire buttons
        self.startDrawingButton.clicked.connect(self.accept)
        self.helpButton.clicked.connect(self._show_help)

    def _setup_autocomplete(self):
        """Make combo boxes searchable with autocomplete capabilities."""
        # Layer ComboBox - Searchable, but don't allow typing non-existent layers
        self.layerComboBox.setEditable(True)
        self.layerComboBox.setInsertPolicy(QComboBox.NoInsert)
        layer_completer = self.layerComboBox.completer()
        if layer_completer:
            layer_completer.setCompletionMode(QCompleter.PopupCompletion)
            layer_completer.setFilterMode(Qt.MatchContains)

        # Field ComboBox - Searchable, allows typing new field names
        self.fieldComboBox.setEditable(True)
        self.fieldComboBox.setInsertPolicy(QComboBox.InsertAtBottom)
        field_completer = self.fieldComboBox.completer()
        if field_completer:
            field_completer.setCompletionMode(QCompleter.PopupCompletion)
            field_completer.setFilterMode(Qt.MatchContains)

    def _update_fields(self):
        """Update the field dropdown based on the currently selected layer."""
        self.fieldComboBox.clear()
        layer_id = self.layerComboBox.currentData()
        if not layer_id:
            return
            
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer:
            for field in layer.fields():
                self.fieldComboBox.addItem(field.name())
            
            # Set a default field name if it doesn't exist
            if self.fieldComboBox.findText("sequence_no") == -1:
                self.fieldComboBox.insertItem(0, "sequence_no")
            self.fieldComboBox.setCurrentText("sequence_no")

    # ------------------------------------------------------------------
    # Help dialog
    # ------------------------------------------------------------------

    def _show_help(self):
        """Display the quick-guide in a scrollable message box."""
        dlg = QMessageBox(self)
        dlg.setWindowTitle("DrawSeq — Quick Guide")
        dlg.setTextFormat(Qt.RichText)
        dlg.setText(HELP_TEXT)
        dlg.setIcon(QMessageBox.Information)
        dlg.setStandardButtons(QMessageBox.Ok)
        dlg.exec_()

    # ------------------------------------------------------------------
    # Getters used by DrawSeq_plugin.run()
    # ------------------------------------------------------------------

    def get_layer_id(self) -> str:
        """Return the layer ID of the currently selected layer."""
        idx = self.layerComboBox.currentIndex()
        return self.layerComboBox.itemData(idx) if idx >= 0 else None

    def get_field_name(self) -> str:
        """Return the user-selected or typed field name."""
        return self.fieldComboBox.currentText().strip()

    def get_selected_only(self) -> bool:
        """Return True if 'Number selected features only' is checked."""
        return self.selectedOnlyCheckBox.isChecked()