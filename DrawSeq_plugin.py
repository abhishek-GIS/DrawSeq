# -*- coding: utf-8 -*-
"""
DrawSeq_plugin.py
Main plugin class — registers the toolbar action and wires the setup dialog.
"""

import os
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QIcon, QAction
from qgis.core import QgsProject, QgsMapLayer

from .DrawSeq_dialog import SetupDialog
from .DrawSeq_algorithm import SequenceNumberingTool


class DrawSeqPlugin:
    """QGIS Plugin Implementation for DrawSeq."""

    def __init__(self, iface):
        """
        Constructor.

        :param iface: QGIS interface instance.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.toolbar = None

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        """Create the menu entry and toolbar button inside QGIS GUI."""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "DrawSeq: Sequence Numbering", self.iface.mainWindow())
        self.action.setToolTip("Draw paths to assign sequence numbers to vector features")
        self.action.triggered.connect(self.run)

        # Add to Vector menu and a dedicated toolbar
        self.iface.addPluginToVectorMenu("&DrawSeq", self.action)
        self.toolbar = self.iface.addToolBar("DrawSeq")
        self.toolbar.setObjectName("DrawSeqToolbar")
        self.toolbar.addAction(self.action)

    def unload(self):
        """Remove the plugin menu item and toolbar on unload."""
        self.iface.removePluginVectorMenu("&DrawSeq", self.action)
        
        if self.toolbar:
            self.toolbar.clear() # Clear actions safely
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.setParent(None) # Instantly detaches from QGIS main window
            self.toolbar.deleteLater()
            self.toolbar = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Show the setup dialog and, on acceptance, activate the map tool."""
        # Guard: at least one vector layer must be loaded
        vector_layers = [
            l for l in QgsProject.instance().mapLayers().values()
            if l.type() == QgsMapLayer.LayerType.VectorLayer
        ]
        if not vector_layers:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "DrawSeq",
                "No vector layers are loaded in the project.\n"
                "Please add a vector layer before using DrawSeq."
            )
            return

        dlg = SetupDialog(self.iface.mainWindow())
        if dlg.exec():
            layer_id = dlg.get_layer_id()
            if not layer_id:
                QMessageBox.warning(self.iface.mainWindow(), "DrawSeq", "Please select a valid layer.")
                return
                
            target_layer = QgsProject.instance().mapLayer(layer_id)
            target_field = dlg.get_field_name()
            selected_only = dlg.get_selected_only()

            if target_layer is None:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "DrawSeq",
                    "Could not retrieve the selected layer."
                )
                return
                
            if not target_field:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "DrawSeq",
                    "Please specify a target field to store the sequence numbers."
                )
                return

            tool = SequenceNumberingTool(self.canvas, target_layer, target_field, selected_only)
            self.canvas.setMapTool(tool)
