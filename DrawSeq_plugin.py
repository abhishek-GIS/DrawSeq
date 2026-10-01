# -*- coding: utf-8 -*-
"""
DrawSeq_plugin.py
Main plugin class — registers the toolbar action and wires the setup dialog.
"""

import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsMapLayer

from .DrawSeq_dialog import SetupDialog
from .DrawSeq_algorithm import SequenceNumberingTool

# PyQt5 / PyQt6 Compatibility Block
try:
    STAYS_ON_TOP = Qt.WindowType.WindowStaysOnTopHint
except AttributeError:
    STAYS_ON_TOP = Qt.WindowStaysOnTopHint


class DrawSeqPlugin:
    """QGIS Plugin Implementation for DrawSeq."""

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dlg = None

    def initGui(self):
        """Create the menu entry and toolbar button inside QGIS GUI."""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "DrawSeq: Sequence Numbering", self.iface.mainWindow())
        self.action.setToolTip("Draw paths to assign sequence numbers to vector features")
        self.action.triggered.connect(self.run)

        # Add to standard QGIS Toolbar and Vector Menu
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu("&DrawSeq", self.action)

    def unload(self):
        """Remove the plugin menu item and toolbar icon on unload."""
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginVectorMenu("&DrawSeq", self.action)

    def run(self):
        """Show the setup dialog as a floating, non-modal window."""
        vector_layers = [
            l for l in QgsProject.instance().mapLayers().values()
            if l.type() == QgsMapLayer.VectorLayer
        ]
        if not vector_layers:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "DrawSeq",
                "No vector layers are loaded in the project.\n"
                "Please add a vector layer before using DrawSeq."
            )
            return

        if self.dlg:
            self.dlg.close()
            self.dlg.deleteLater()

        self.dlg = SetupDialog(self.iface.mainWindow())
        self.dlg.setWindowFlags(self.dlg.windowFlags() | STAYS_ON_TOP)
        self.dlg.accepted.connect(self._start_drawing_tool)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def _start_drawing_tool(self):
        """Triggered when the user clicks 'Start Drawing' in the dialog."""
        if not self.dlg:
            return
            
        layer_id = self.dlg.get_layer_id()
        if not layer_id:
            QMessageBox.warning(self.iface.mainWindow(), "DrawSeq", "Please select a valid layer.")
            return
            
        target_layer = QgsProject.instance().mapLayer(layer_id)
        selected_only = self.dlg.get_selected_only()

        if target_layer is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "DrawSeq",
                "Could not retrieve the selected layer."
            )
            return

        tool = SequenceNumberingTool(self.canvas, target_layer, selected_only)
        self.canvas.setMapTool(tool)