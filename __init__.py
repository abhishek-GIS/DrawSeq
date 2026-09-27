# -*- coding: utf-8 -*-
"""
DrawSeq - QGIS Plugin
Assigns sequence numbers to vector features by drawing paths on the map canvas.
"""

def classFactory(iface):
    """
    Load DrawSeqPlugin class from DrawSeq_plugin module.
    Called by QGIS at plugin load time.

    :param iface: A QGIS interface instance (QgsInterface).
    :type iface: QgsInterface
    """
    from .DrawSeq_plugin import DrawSeqPlugin
    return DrawSeqPlugin(iface)
