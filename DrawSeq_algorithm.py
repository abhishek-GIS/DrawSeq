# -*- coding: utf-8 -*-
"""
DrawSeq_algorithm.py
Core map tool logic:
  - SequenceNumberingTool  : interactive QgsMapTool for drawing paths
  - MultiLineDialog        : review / adjust start numbers before committing
"""

import math

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSpinBox,
    QPushButton, QLabel, QDialogButtonBox, QScrollArea, QWidget,
    QMessageBox, QLineEdit, QRadioButton, QButtonGroup, QCheckBox, QFrame
)
from qgis.PyQt.QtCore import Qt, QVariant, QSizeF
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsWkbTypes, QgsGeometry, QgsFeatureRequest,
    QgsField, QgsSpatialIndex, QgsPointXY,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
    QgsTextBufferSettings, QgsTextBackgroundSettings, Qgis,
    QgsCoordinateTransform, QgsProject, QgsMessageLog
)
from qgis.gui import QgsMapTool, QgsRubberBand


# ---------------------------------------------------------------------------
# MultiLineDialog
# ---------------------------------------------------------------------------

class MultiLineDialog(QDialog):
    """
    Review dialog shown before sequence numbers are committed.
    """

    def __init__(self, line_data, canvas, tool_ref=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Sequence Numbers")
        self.setMinimumWidth(450)
        self.canvas     = canvas
        self.tool_ref   = tool_ref     
        self._line_data = line_data    

        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Header
        main_layout.addWidget(
            QLabel(f"<b>Paths Created: {len(line_data)}</b><br>"
                   "Arrows show numbering direction. Set a start number for each path:")
        )

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep0)

        # Scroll area
        scroll         = QScrollArea()
        scroll_content = QWidget()
        grid_layout    = QVBoxLayout(scroll_content)
        grid_layout.setSpacing(0)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        # Column widths
        _INDENT = 50 + 6 + 58 + 6 + 95 + 6

        # Prefix / Suffix radio header row
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header_row.setContentsMargins(0, 2, 0, 4)
        spc = QWidget()
        spc.setFixedWidth(_INDENT)
        header_row.addWidget(spc)

        self._rb_prefix = QRadioButton("Prefixes")
        self._rb_suffix = QRadioButton("Suffix")
        self._rb_prefix.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._rb_prefix, 0)
        self._mode_group.addButton(self._rb_suffix, 1)

        header_row.addWidget(self._rb_prefix)
        header_row.addSpacing(12)
        header_row.addWidget(self._rb_suffix)
        header_row.addStretch()
        grid_layout.addLayout(header_row)

        self.spinboxes    = []
        self.text_inputs  = []
        self._carry_pairs = []

        current_default_start = 1

        for i, data in enumerate(line_data):
            # Main control row
            row = QHBoxLayout()
            row.setSpacing(6)
            row.setContentsMargins(0, 4, 0, 0)

            zoom_btn = QPushButton("Zoom")
            zoom_btn.setFixedSize(28, 28)
            lum     = data['color'].lightness()
            txt_col = 'white' if lum < 150 else 'black'
            zoom_btn.setStyleSheet(
                f"background-color:{data['color'].name()};"
                f"color:{txt_col};font-weight:bold;border-radius:3px;"
            )
            zoom_btn.clicked.connect(
                lambda checked, d=data, idx=i: self._zoom_and_select(d, idx)
            )

            del_btn = QPushButton("✕")
            del_btn.setFixedSize(10, 10)
            del_btn.setToolTip("Delete this path")
            del_btn.setStyleSheet(
                "QPushButton{background:#e05555;color:white;font-weight:bold;"
                "border-radius:3px;}"
                "QPushButton:hover{background:#c03030;}"
            )
            del_btn.clicked.connect(
                lambda checked, d=data, idx=i, btn=del_btn,
                       sb=None, te=None: self._delete_row(d, idx)
            )

            path_lbl = QLabel(f"Path {i + 1}:")
            path_lbl.setFixedWidth(58)

            spinbox = QSpinBox()
            spinbox.setRange(1, 9_999_999)
            spinbox.setValue(current_default_start)
            spinbox.setFixedWidth(95)

            text_edit = QLineEdit()
            text_edit.setPlaceholderText("text...")
            text_edit.setFixedWidth(120)
            text_edit.setToolTip(
                "Text placed before the number (Prefix) or after it (Suffix).\n"
                "Leave blank for plain numbers."
            )

            feat_lbl = QLabel(
                f"({data['count']} feature{'s' if data['count'] != 1 else ''})"
            )
            feat_lbl.setMinimumWidth(80)

            row.addWidget(zoom_btn)
            row.addWidget(del_btn)
            row.addWidget(path_lbl)
            row.addWidget(spinbox)
            row.addWidget(text_edit)
            row.addWidget(feat_lbl)
            row.addStretch()
            grid_layout.addLayout(row)

            # Store widget refs so _delete_row can hide them
            data['_row_widgets'] = [zoom_btn, del_btn, path_lbl, spinbox, text_edit, feat_lbl]

            self.spinboxes.append(spinbox)
            self.text_inputs.append(text_edit)
            current_default_start += data['count']

            # Carry over row
            carry_row = QHBoxLayout()
            carry_row.setContentsMargins(0, 1, 0, 6)
            carry_row.setSpacing(4)
            carry_row.addSpacing(_INDENT)

            carry_chk = QCheckBox("Carry over values")
            carry_chk.setToolTip("Copy the prefix/suffix text from the path above into this path.")
            if i == 0:
                carry_chk.setEnabled(False)
                carry_chk.setToolTip("No path above - nothing to carry over.")
            else:
                prev_edit = self.text_inputs[i - 1]
                carry_chk.stateChanged.connect(
                    lambda state, te=text_edit, pe=prev_edit:
                        self._on_carry_changed(state, te, pe)
                )

            carry_row.addWidget(carry_chk)
            carry_row.addStretch()
            grid_layout.addLayout(carry_row)
            self._carry_pairs.append((carry_chk, text_edit))

            if i < len(line_data) - 1:
                div = QFrame()
                div.setFrameShape(QFrame.Shape.HLine)
                div.setFrameShadow(QFrame.Shadow.Plain)
                div.setStyleSheet("color: #cccccc;")
                grid_layout.addWidget(div)

        grid_layout.addStretch()
        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(430)
        main_layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)
        self.setLayout(main_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.tool_ref is not None:
            sel = self.tool_ref.selected_idx
            if sel is not None and 0 <= sel < len(self._line_data):
                data = self._line_data[sel]
                if not data.get('skip', False):
                    self._delete_row(data, sel)
            return          
        super().keyPressEvent(event)

    def _on_carry_changed(self, state, this_edit, prev_edit):
        if state == Qt.CheckState.Checked:
            this_edit.setText(prev_edit.text())
            this_edit.setEnabled(False)
            prev_edit.textChanged.connect(this_edit.setText)
        else:
            this_edit.setEnabled(True)
            try:
                prev_edit.textChanged.disconnect(this_edit.setText)
            except RuntimeError:
                pass

    def _zoom_and_select(self, data, idx):
        # Uses the original Canvas geometry for zooming
        extent = data['geom'].boundingBox()
        extent.scale(1.3)
        self.canvas.setExtent(extent)
        self.canvas.refresh()
        if self.tool_ref is not None:
            self.tool_ref.select_line(idx)

    def _delete_row(self, data, idx):
        data['skip'] = True
        for w in data.get('_row_widgets', []):
            w.hide()
        if idx < len(self._carry_pairs):
            chk, te = self._carry_pairs[idx]
            chk.hide()
        if self.tool_ref is not None:
            self.tool_ref.hide_path_rubbers(idx)

    def is_prefix_mode(self):
        return self._rb_prefix.isChecked()

    def get_start_values(self):
        return [sb.value() for sb in self.spinboxes]

    def get_affix_values(self):
        return [te.text().strip() for te in self.text_inputs]


# ---------------------------------------------------------------------------
# SequenceNumberingTool
# ---------------------------------------------------------------------------

class SequenceNumberingTool(QgsMapTool):
    """
    Interactive map tool that lets the user draw one or more poly-line paths.
    """

    _SEL_LINE_COLOR   = QColor(255, 80,  0)
    _SEL_VERTEX_COLOR = QColor(255, 80,  0)
    _NORMAL_VERTEX_BG = QColor(0,   0,   0)
    _NORMAL_VERTEX_FG = QColor(255, 255, 255)

    def __init__(self, canvas, target_layer, target_field, selected_only=False):
        super().__init__(canvas)
        self.canvas        = canvas
        self.layer         = target_layer
        self.target_field  = target_field
        self.selected_only = selected_only

        self.finished_lines  = []
        self.current_points  = []
        self.drag_info       = None
        self.selected_idx    = None
        
        self._did_selection       = False   
        self._ignore_next_release = False
        self._is_reviewing        = False # Safety lock when dialog is floating
        self.review_dlg           = None  # Keep reference to the non-modal dialog
        self._MIN_SNAP_PX         = 8       

        self.hue_accumulator        = 0.35
        self.golden_ratio_conjugate = 0.618033988749895

        self.active_rubberband = self._make_rubberband(QColor(180, 180, 180), dashed=True)
        self.active_arrow      = self._make_arrow_polygon(alpha=120)

    def _make_rubberband(self, color, dashed=False, width=3):
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        rb.setColor(color)
        rb.setWidth(width)
        if dashed:
            rb.setLineStyle(Qt.PenStyle.DashLine)
        return rb

    def _make_arrow_polygon(self, alpha=255):
        """Creates a black polygon rubberband to act as a triangle arrow."""
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        rb.setColor(QColor(0, 0, 0, alpha))
        rb.setStrokeColor(QColor(255, 255, 255, alpha))
        rb.setWidth(1.5)
        return rb

    def _make_vertex_rb(self):
        vrb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        vrb.setIcon(QgsRubberBand.IconType.ICON_FULL_BOX)
        vrb.setIconSize(7)
        vrb.setColor(self._NORMAL_VERTEX_BG)
        vrb.setSecondaryStrokeColor(self._NORMAL_VERTEX_FG)
        return vrb

    def _make_sel_rb(self):
        srb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        sel_color = QColor(self._SEL_LINE_COLOR)
        sel_color.setAlpha(160)
        srb.setColor(sel_color)
        srb.setWidth(7)
        return srb

    def _rebuild_vertex_dots(self, idx):
        data = self.finished_lines[idx]
        vrb  = data['vertex_rb']
        vrb.reset(QgsWkbTypes.GeometryType.PointGeometry)
        for pt in data['points']:
            vrb.addPoint(pt)

    def _build_arrow_geom(self, p1, p2):
        """Calculates a black triangle pointing toward p2 at the segment midpoint."""
        units = self.canvas.mapUnitsPerPixel()
        mid_x = (p1.x() + p2.x()) / 2.0
        mid_y = (p1.y() + p2.y()) / 2.0
        
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            
        length = 16 * units
        width = 12 * units
        
        tip_x = mid_x + math.cos(angle) * (length / 2.0)
        tip_y = mid_y + math.sin(angle) * (length / 2.0)
        
        back_x = mid_x - math.cos(angle) * (length / 2.0)
        back_y = mid_y - math.sin(angle) * (length / 2.0)
        
        bl_x = back_x + math.cos(angle + math.pi/2.0) * (width / 2.0)
        bl_y = back_y + math.sin(angle + math.pi/2.0) * (width / 2.0)
        
        br_x = back_x + math.cos(angle - math.pi/2.0) * (width / 2.0)
        br_y = back_y + math.sin(angle - math.pi/2.0) * (width / 2.0)
        
        return QgsGeometry.fromPolygonXY([[
            QgsPointXY(tip_x, tip_y),
            QgsPointXY(bl_x, bl_y),
            QgsPointXY(br_x, br_y)
        ]])

    def _update_finished_line_visuals(self, idx):
        data = self.finished_lines[idx]
        pts  = data['points']
        geom = QgsGeometry.fromPolylineXY(pts)
        data['geom'] = geom
        data['rb'].setToGeometry(geom, None)
        data['sel_rb'].setToGeometry(geom, None)
        
        while len(data['arrow_rbs']) < len(pts) - 1:
            data['arrow_rbs'].append(self._make_arrow_polygon())
        while len(data['arrow_rbs']) > len(pts) - 1:
            old_rb = data['arrow_rbs'].pop()
            old_rb.reset()
            old_rb.hide()
            
        for j in range(len(pts) - 1):
            arr_geom = self._build_arrow_geom(pts[j], pts[j+1])
            data['arrow_rbs'][j].setToGeometry(arr_geom, None)
            
        self._rebuild_vertex_dots(idx)
        self.canvas.refresh()

    def _pixel_tolerance(self):
        return self.canvas.mapUnitsPerPixel() * 10

    def get_next_distinct_color(self):
        self.hue_accumulator = (self.hue_accumulator + self.golden_ratio_conjugate) % 1.0
        return QColor.fromHsvF(self.hue_accumulator, 0.8, 0.9)

    def select_line(self, idx):
        if self.selected_idx is not None and self.selected_idx != idx:
            self._apply_deselect_style(self.selected_idx)

        self.selected_idx = idx
        data = self.finished_lines[idx]
        data['sel_rb'].setToGeometry(data['geom'], None)
        data['sel_rb'].show()
        data['vertex_rb'].setColor(self._SEL_VERTEX_COLOR)
        data['vertex_rb'].setSecondaryStrokeColor(QColor(255, 255, 255))
        self.canvas.refresh()

    def _deselect_all(self):
        for i in range(len(self.finished_lines)):
            self._apply_deselect_style(i)
        self.selected_idx = None
        self.canvas.refresh()

    def _apply_deselect_style(self, idx):
        data = self.finished_lines[idx]
        data['sel_rb'].hide()
        data['vertex_rb'].setColor(self._NORMAL_VERTEX_BG)
        data['vertex_rb'].setSecondaryStrokeColor(self._NORMAL_VERTEX_FG)

    def _delete_selected(self):
        if self.selected_idx is None:
            return
        idx  = self.selected_idx
        data = self.finished_lines[idx]
        for rb_key in ('rb', 'vertex_rb', 'sel_rb'):
            data[rb_key].reset()
            data[rb_key].hide()
        for arr_rb in data['arrow_rbs']:
            arr_rb.reset()
            arr_rb.hide()
        self.finished_lines.pop(idx)
        self.selected_idx = None
        self.canvas.refresh()

    def hide_path_rubbers(self, idx):
        if 0 <= idx < len(self.finished_lines):
            d = self.finished_lines[idx]
            for key in ('rb', 'vertex_rb', 'sel_rb'):
                d[key].reset()
                d[key].hide()
            for arr_rb in d['arrow_rbs']:
                arr_rb.reset()
                arr_rb.hide()
            if self.selected_idx == idx:
                self.selected_idx = None
            self.canvas.refresh()

    def keyPressEvent(self, event):
        if self._is_reviewing: 
            return # Block interaction while dialog is floating

        if event.key() == Qt.Key.Key_Delete:
            if self.selected_idx is not None:
                self._delete_selected()
            return

        undo = (event.key() == Qt.Key.Key_Backspace or
                (event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier))
        if undo and self.current_points:
            self.current_points.pop()
            if len(self.current_points) >= 2:
                self.active_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY(self.current_points), None
                )
                geom = self._build_arrow_geom(self.current_points[-2], self.current_points[-1])
                self.active_arrow.setToGeometry(geom, None)
            elif len(self.current_points) == 1:
                self.active_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY(self.current_points), None
                )
                self.active_arrow.reset()
            else:
                self.active_rubberband.reset()
                self.active_arrow.reset()
            self.canvas.refresh()

    def canvasPressEvent(self, event):
        if self._is_reviewing: 
            return # Block interaction while dialog is floating

        if event.button() != Qt.MouseButton.LeftButton:
            return

        point = self.toMapCoordinates(event.pos())
        tol   = self._pixel_tolerance()

        if not self.current_points:
            for i, line_data in enumerate(self.finished_lines):
                for j, pt in enumerate(line_data['points']):
                    if pt.distance(point) < tol:
                        self.drag_info      = (i, j)
                        self._did_selection = True
                        self.select_line(i)
                        return

        best_idx  = None
        best_dist = float('inf')
        for i, line_data in enumerate(self.finished_lines):
            geom = QgsGeometry.fromPolylineXY(line_data['points'])
            dist, _, _, _ = geom.closestSegmentWithContext(point)
            dist = math.sqrt(dist)
            if dist < tol and dist < best_dist:
                best_dist = dist
                best_idx  = i

        if best_idx is not None:
            self._did_selection = True
            self.select_line(best_idx)
        elif not self.current_points:
            self._deselect_all()

    def canvasMoveEvent(self, event):
        if self._is_reviewing: 
            return # Block interaction while dialog is floating

        point = self.toMapCoordinates(event.pos())

        if self.drag_info:
            li, vi = self.drag_info
            self.finished_lines[li]['points'][vi] = point
            self._update_finished_line_visuals(li)
            return

        if self.current_points:
            temp = self.current_points + [point]
            self.active_rubberband.setToGeometry(QgsGeometry.fromPolylineXY(temp), None)
            if len(temp) >= 2:
                geom = self._build_arrow_geom(temp[-2], temp[-1])
                self.active_arrow.setToGeometry(geom, None)

    def canvasReleaseEvent(self, event):
        if self._is_reviewing: 
            return # Block interaction while dialog is floating

        if self.drag_info:
            self.drag_info      = None
            self._did_selection = False
            return

        point = self.toMapCoordinates(event.pos())
        
        if self._ignore_next_release:
            self._ignore_next_release = False
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._did_selection:
                self._did_selection = False
                return
            self._did_selection = False

            if self.current_points:
                last_screen = self.toCanvasCoordinates(self.current_points[-1])
                dx = last_screen.x() - event.pos().x()
                dy = last_screen.y() - event.pos().y()
                if (dx * dx + dy * dy) < self._MIN_SNAP_PX ** 2:
                    return

            self.current_points.append(point)

        elif event.button() == Qt.MouseButton.MiddleButton:
            tol = self._pixel_tolerance()
            for i, line_data in enumerate(self.finished_lines):
                dist, _, _, _ = QgsGeometry.fromPolylineXY(
                    line_data['points']
                ).closestSegmentWithContext(point)
                if math.sqrt(dist) < tol:
                    line_data['points'].reverse()
                    self._update_finished_line_visuals(i)
                    return

        elif event.button() == Qt.MouseButton.RightButton:
            if len(self.current_points) >= 2:
                line_geom = QgsGeometry.fromPolylineXY(self.current_points)
                color     = self.get_next_distinct_color()

                self.active_rubberband.setColor(color)
                self.active_rubberband.setLineStyle(Qt.PenStyle.SolidLine)

                vrb = self._make_vertex_rb()
                for pt in self.current_points:
                    vrb.addPoint(pt)

                srb = self._make_sel_rb()
                srb.setToGeometry(line_geom, None)
                srb.hide()
                
                arrow_rbs = []
                for j in range(len(self.current_points) - 1):
                    arrow_rbs.append(self._make_arrow_polygon())

                self.finished_lines.append({
                    'points':           list(self.current_points),
                    'geom':             line_geom,
                    'color':            color,
                    'rb':               self.active_rubberband,
                    'arrow_rbs':        arrow_rbs,
                    'vertex_rb':        vrb,
                    'sel_rb':           srb,
                })
                
                self._update_finished_line_visuals(len(self.finished_lines) - 1)

                self.canvas.refresh()
                self.active_rubberband = self._make_rubberband(QColor(180, 180, 180), dashed=True)
                self.active_arrow.reset()
                self.current_points    = []

            elif len(self.current_points) == 1:
                self.current_points = []
                self.active_rubberband.reset()
                self.active_arrow.reset()
                self.canvas.refresh()

            elif len(self.current_points) == 0 and self.finished_lines:
                self._process_multiple_lines()

    def canvasDoubleClickEvent(self, event):
        if self._is_reviewing: 
            return # Block interaction while dialog is floating

        self._ignore_next_release = True 
        
        point = self.toMapCoordinates(event.pos())
        tol   = self._pixel_tolerance()
        arrow_tol = tol * 1.5

        for i, line_data in enumerate(self.finished_lines):
            pts = line_data['points']
            
            clicked_arrow = False
            for j in range(len(pts) - 1):
                mid_pt = QgsPointXY((pts[j].x() + pts[j+1].x()) / 2.0, 
                                    (pts[j].y() + pts[j+1].y()) / 2.0)
                
                if point.distance(mid_pt) < arrow_tol:
                    clicked_arrow = True
                    break

            if clicked_arrow:
                pts.reverse()
                self._update_finished_line_visuals(i)
                return

            geom = QgsGeometry.fromPolylineXY(pts)
            dist, _, after_vertex, _ = geom.closestSegmentWithContext(point)
            if math.sqrt(dist) < tol:
                pts.insert(after_vertex, point)
                self._update_finished_line_visuals(i)
                return

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _process_multiple_lines(self):
        idx = self.layer.fields().indexOf(self.target_field)
        if idx == -1:
            new_field = QgsField(self.target_field, QVariant.String)
            
            if self.layer.isEditable():
                self.layer.addAttribute(new_field)
            else:
                self.layer.dataProvider().addAttributes([new_field])
            
            self.layer.updateFields()
            idx = self.layer.fields().indexOf(self.target_field)
            
            if idx == -1:
                idx = len(self.layer.fields()) - 1
                self.target_field = self.layer.fields().at(idx).name()

            if idx == -1:
                QMessageBox.critical(None, "DrawSeq", f"Could not create field for '{self.target_field}'.")
                self.cleanup()
                return
        else:
            if self.layer.fields().field(idx).type() not in (QVariant.String,):
                QMessageBox.warning(
                    None, "DrawSeq - Numeric Field Notice",
                    f"The field '{self.target_field}' is numeric.\n\n"
                    "Numbers will save fine, but if you attempt to use text prefixes "
                    "or suffixes, the values may be rejected by the layer."
                )

        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs  = self.layer.crs()
        project    = QgsProject.instance()
        transform  = QgsCoordinateTransform(canvas_crs, layer_crs, project)

        if self.selected_only:
            selected_ids = self.layer.selectedFeatureIds()
            if not selected_ids:
                QMessageBox.warning(
                    None, "DrawSeq - No Selection",
                    "No features are selected in the target layer.\n"
                    "Either select features first, or uncheck 'selected only'."
                )
                self.cleanup()
                return
            features_iterator = self.layer.getFeatures(
                QgsFeatureRequest().setFilterFids(selected_ids)
            )
        else:
            features_iterator = self.layer.getFeatures()

        spatial_index  = QgsSpatialIndex(features_iterator)
        processed_fids = set()
        line_data_results = []

        for line_item in self.finished_lines:
            canvas_geom = line_item['geom']
            layer_geom  = QgsGeometry(canvas_geom)
            
            if canvas_crs != layer_crs:
                try:
                    layer_geom.transform(transform)
                except Exception as e:
                    QgsMessageLog.logMessage(f"DrawSeq transform error: {e}", "DrawSeq", Qgis.MessageLevel.Warning)

            candidate_fids = spatial_index.intersects(layer_geom.boundingBox())
            matched = []
            for feat in self.layer.getFeatures(
                    QgsFeatureRequest().setFilterFids(candidate_fids)):
                if feat.id() not in processed_fids and feat.geometry().intersects(layer_geom):
                    matched.append(feat)
                    processed_fids.add(feat.id())
                    
            line_data_results.append({
                'geom':       canvas_geom, 
                'layer_geom': layer_geom,  
                'features':   matched,
                'count':      len(matched),
                'color':      line_item['color'],
            })

        # 4. DIALOG & ATTRIBUTE UPDATE
        self._is_reviewing = True # Lock drawing tool

        # Clear old dialog if it somehow exists
        if self.review_dlg:
            try:
                self.review_dlg.close()
                self.review_dlg.deleteLater()
            except Exception as e:
                QgsMessageLog.logMessage(f"DrawSeq dialog cleanup error: {e}", "DrawSeq", Qgis.MessageLevel.Warning)

        self.review_dlg = MultiLineDialog(line_data_results, self.canvas, tool_ref=self)
        self.review_dlg.setWindowFlags(self.review_dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        # Pass the data processing to a dedicated commit function once Accepted
        self.review_dlg.accepted.connect(lambda: self._commit_sequence_numbers(line_data_results, idx))
        self.review_dlg.rejected.connect(self.cleanup)

        # Show as Non-Modal so QGIS can be interacted with!
        self.review_dlg.show()
        self.review_dlg.raise_()
        self.review_dlg.activateWindow()

    def _commit_sequence_numbers(self, line_data_results, idx):
        """Called when the user clicks 'OK' on the Review Dialog."""
        if not self.layer.isEditable():
            self.layer.startEditing()

        prefix_mode  = self.review_dlg.is_prefix_mode()
        start_values = self.review_dlg.get_start_values()
        affix_values = self.review_dlg.get_affix_values()
        
        field_type = self.layer.fields().field(idx).type()

        for i, data in enumerate(line_data_results):
            if data.get('skip'):
                continue
            seq   = start_values[i]
            affix = affix_values[i]
            
            sorted_feats = sorted(
                data['features'],
                key=lambda f: data['layer_geom'].lineLocatePoint(f.geometry().centroid())
            )
            
            for feat in sorted_feats:
                if affix:
                    val_str = f"{affix}{seq}" if prefix_mode else f"{seq}{affix}"
                    final_value = val_str
                else:
                    if field_type in (QVariant.Int, QVariant.UInt, QVariant.LongLong):
                        final_value = int(seq)
                    elif field_type == QVariant.Double:
                        final_value = float(seq)
                    else:
                        final_value = str(seq)

                self.layer.changeAttributeValue(feat.id(), idx, final_value)
                seq += 1

        if self.layer.commitChanges():
            self._apply_labels()
            self.canvas.refreshAllLayers()
        else:
            QMessageBox.critical(
                None, "DrawSeq - Commit Failed",
                "Could not commit changes to the layer."
            )

        self.cleanup()

    def _apply_labels(self):
        pal           = QgsPalLayerSettings()
        pal.fieldName = self.target_field
        pal.enabled   = True

        pal.scaleVisibility = True
        pal.minimumScale = 5000  

        text_fmt = QgsTextFormat()
        text_fmt.setFont(QFont('Arial', 13, QFont.Weight.Bold))
        text_fmt.setSize(13)

        text_fmt.setColor(QColor('LightSeaGreen'))

        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(1)
        buf.setColor(QColor('white'))
        text_fmt.setBuffer(buf)

        bg = QgsTextBackgroundSettings()
        bg.setEnabled(True)
        bg.setType(QgsTextBackgroundSettings.ShapeType.ShapeRectangle)
        bg.setFillColor(QColor('#A0A0A0'))
        bg.setStrokeColor(QColor('#606060'))
        bg.setStrokeWidth(0.3)
        bg.setOpacity(0.85)
        bg.setSizeType(QgsTextBackgroundSettings.SizeType.SizeBuffer)
        bg.setSize(QSizeF(1.0, 0.5))
        text_fmt.setBackground(bg)

        pal.setFormat(text_fmt)

        self.layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        self.layer.setLabelsEnabled(True)
        self.layer.triggerRepaint()

    def deactivate(self):
        """Called natively by QGIS when the user switches to another map tool (like Pan)."""
        self.cleanup()
        super().deactivate()

    def cleanup(self):
        self._is_reviewing = False
        
        # Ensure the dialog gracefully exits and doesn't sit in memory
        if getattr(self, 'review_dlg', None):
            try:
                self.review_dlg.rejected.disconnect(self.cleanup)
            except TypeError as e:
                QgsMessageLog.logMessage(f"DrawSeq disconnect error: {e}", "DrawSeq", Qgis.MessageLevel.Info)
            self.review_dlg.close()
            self.review_dlg.deleteLater()
            self.review_dlg = None

        self.active_rubberband.reset()
        self.active_rubberband.hide()
        self.active_arrow.reset()
        self.active_arrow.hide()

        for d in self.finished_lines:
            for rb_key in ('rb', 'vertex_rb', 'sel_rb'):
                d[rb_key].reset()
                d[rb_key].hide()
            for arr_rb in d['arrow_rbs']:
                arr_rb.reset()
                arr_rb.hide()

        self.finished_lines.clear()
        self.current_points.clear()
        self.drag_info    = None
        self.selected_idx = None

        self.canvas.unsetMapTool(self)
        self.canvas.refresh()
