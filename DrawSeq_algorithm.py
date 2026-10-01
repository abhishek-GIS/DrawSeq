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
    QMessageBox, QLineEdit, QRadioButton, QButtonGroup, QCheckBox, QFrame,
    QComboBox, QInputDialog, QGroupBox, QGridLayout, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QVariant, QSizeF
from qgis.PyQt.QtGui import QColor, QFont, QIcon
from qgis.core import (
    QgsWkbTypes, QgsGeometry, QgsFeatureRequest,
    QgsField, QgsSpatialIndex, QgsPointXY,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
    QgsTextBufferSettings, QgsTextBackgroundSettings, Qgis,
    QgsCoordinateTransform, QgsProject, QgsUnitTypes, QgsApplication,
    QgsSettings
)
from qgis.gui import QgsMapTool, QgsRubberBand

# PyQt5 / PyQt6 Compatibility Block
try:
    STAYS_ON_TOP = Qt.WindowType.WindowStaysOnTopHint
    KEY_DELETE = Qt.Key.Key_Delete
    KEY_BACKSPACE = Qt.Key.Key_Backspace
    KEY_Z = Qt.Key.Key_Z
    MOD_CTRL = Qt.KeyboardModifier.ControlModifier
    BTN_LEFT = Qt.MouseButton.LeftButton
    BTN_RIGHT = Qt.MouseButton.RightButton
    BTN_MIDDLE = Qt.MouseButton.MiddleButton
    LINE_DASH = Qt.PenStyle.DashLine
    LINE_SOLID = Qt.PenStyle.SolidLine
    STATE_CHECKED = Qt.CheckState.Checked
    FRAME_HLINE = QFrame.Shape.HLine
    FRAME_SUNKEN = QFrame.Shadow.Sunken
    FRAME_PLAIN = QFrame.Shadow.Plain
    FRAME_NOFRAME = QFrame.Shape.NoFrame
    FONT_WEIGHT_BOLD = QFont.Weight.Bold  
    POLICY_EXPANDING = QSizePolicy.Policy.Expanding
    POLICY_FIXED = QSizePolicy.Policy.Fixed
except AttributeError:
    STAYS_ON_TOP = Qt.WindowStaysOnTopHint
    KEY_DELETE = Qt.Key_Delete
    KEY_BACKSPACE = Qt.Key_Backspace
    KEY_Z = Qt.Key_Z
    MOD_CTRL = Qt.ControlModifier
    BTN_LEFT = Qt.LeftButton
    BTN_RIGHT = Qt.RightButton
    BTN_MIDDLE = Qt.MiddleButton
    LINE_DASH = Qt.DashLine
    LINE_SOLID = Qt.SolidLine
    STATE_CHECKED = Qt.Checked
    FRAME_HLINE = QFrame.HLine
    FRAME_SUNKEN = QFrame.Sunken
    FRAME_PLAIN = QFrame.Plain
    FRAME_NOFRAME = QFrame.NoFrame
    FONT_WEIGHT_BOLD = QFont.Bold  
    POLICY_EXPANDING = QSizePolicy.Expanding
    POLICY_FIXED = QSizePolicy.Fixed

try:
    TYPE_STRING = QVariant.String
    TYPE_INT = QVariant.Int
    TYPE_UINT = QVariant.UInt
    TYPE_LONGLONG = QVariant.LongLong
    TYPE_DOUBLE = QVariant.Double
except AttributeError:
    from qgis.PyQt.QtCore import QMetaType
    TYPE_STRING = QMetaType.Type.QString
    TYPE_INT = QMetaType.Type.Int
    TYPE_UINT = QMetaType.Type.UInt
    TYPE_LONGLONG = QMetaType.Type.LongLong
    TYPE_DOUBLE = QMetaType.Type.Double


class SmartSpinBox(QSpinBox):
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (KEY_BACKSPACE, KEY_DELETE):
            if self.lineEdit().text().strip() == "":
                self.setValue(self.minimum())
                self.lineEdit().selectAll()


class MultiLineDialog(QDialog):
    def __init__(self, line_data, canvas, layer, tool_ref=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Sequence Numbers")
        self.setMinimumWidth(550)
        self.canvas     = canvas
        self.layer      = layer
        self.tool_ref   = tool_ref     
        self._line_data = line_data    

        # --- Window Resizing Memory ---
        self.settings = QgsSettings()
        geom = self.settings.value("DrawSeq/ReviewDialog/Geometry")
        if geom:
            self.restoreGeometry(geom)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.title_label = QLabel()
        main_layout.addWidget(self.title_label)
        self._update_title_label()
        
        # ==========================================
        # GROUP BOX 1: Target Settings
        # ==========================================
        settings_group = QGroupBox("Target Settings")
        settings_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #b0b0b0; border-radius: 5px; margin-top: 1ex; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(8)
        settings_layout.setContentsMargins(10, 15, 10, 10)

        # Row 1: Target Field
        field_layout = QHBoxLayout()
        lbl_field = QLabel("Target Field:")
        lbl_field.setFixedWidth(120)
        lbl_field.setStyleSheet("font-weight: normal;")
        field_layout.addWidget(lbl_field)
        
        self.field_combo = QComboBox()
        self.field_combo.setEditable(True)
        self.field_combo.setSizePolicy(POLICY_EXPANDING, POLICY_FIXED)
        for f in self.layer.fields():
            self.field_combo.addItem(f.name())
            
        if self.field_combo.findText("sequence_no") == -1:
            self.field_combo.insertItem(0, "sequence_no")
        self.field_combo.setCurrentText("sequence_no")
        field_layout.addWidget(self.field_combo)
        settings_layout.addLayout(field_layout)

        # Row 2: Numbering Pattern
        pattern_layout = QHBoxLayout()
        lbl_pattern = QLabel("Numbering Pattern:")
        lbl_pattern.setFixedWidth(120)
        lbl_pattern.setStyleSheet("font-weight: normal;")
        pattern_layout.addWidget(lbl_pattern)
        
        self.pattern_combo = QComboBox()
        self.pattern_combo.setSizePolicy(POLICY_EXPANDING, POLICY_FIXED)
        self.pattern_combo.addItems([
            "Sequential (1, 2, 3...)", 
            "Odd Numbers (1, 3, 5...)", 
            "Even Numbers (2, 4, 6...)", 
            "Custom Interval"
        ])
        pattern_layout.addWidget(self.pattern_combo)

        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 99999)
        self.step_spin.setValue(4)
        self.step_spin.setPrefix("Interval: ")
        self.step_spin.setVisible(False)
        pattern_layout.addWidget(self.step_spin)
        
        settings_layout.addLayout(pattern_layout)
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # ==========================================
        # GROUP BOX 2: Drawn Paths & Numbering
        # ==========================================
        paths_group = QGroupBox("Drawn Paths")
        paths_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #b0b0b0; border-radius: 5px; margin-top: 1ex; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }")
        paths_layout = QVBoxLayout()
        paths_layout.setContentsMargins(5, 15, 5, 5)

        scroll = QScrollArea()
        scroll.setFrameShape(FRAME_NOFRAME)
        scroll_content = QWidget()
        
        self.grid_layout = QGridLayout(scroll_content)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)

        self._rb_prefix = QRadioButton("Prefixes")
        self._rb_suffix = QRadioButton("Suffixes")
        self._rb_prefix.setChecked(True)
        self._rb_prefix.setStyleSheet("font-weight: normal;")
        self._rb_suffix.setStyleSheet("font-weight: normal;")
        
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._rb_prefix, 0)
        self._mode_group.addButton(self._rb_suffix, 1)

        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(350)
        paths_layout.addWidget(scroll)
        paths_group.setLayout(paths_layout)
        main_layout.addWidget(paths_group)

        # ==========================================
        # BUTTON BOX
        # ==========================================
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.reuse_btn = QPushButton("Reuse")
        self.reuse_btn.setIcon(QgsApplication.getThemeIcon('/mActionRefresh.svg'))
        self.reuse_btn.setToolTip("Apply edits and keep lines on the map to reuse them.")
        self.reuse_btn.setMinimumHeight(28)
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setIcon(QgsApplication.getThemeIcon('/mActionSaveEdits.svg'))
        self.ok_btn.setToolTip("Apply edits and clear lines from the map.")
        self.ok_btn.setDefault(True) 
        self.ok_btn.setMinimumHeight(28)
        
        btn_layout.addWidget(self.reuse_btn)
        btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(btn_layout)

        self.ok_btn.clicked.connect(self.accept)
        self.setLayout(main_layout)

        self.spinboxes    = []
        self.text_inputs  = []
        self._carry_pairs = []

        self._build_rows()

        self.pattern_combo.currentIndexChanged.connect(self._recalculate_starts)
        self.step_spin.valueChanged.connect(self._recalculate_starts)
        self._recalculate_starts() 

    def get_target_field(self):
        return self.field_combo.currentText().strip()

    def _update_title_label(self):
        active_lines = [d for d in self._line_data if not d.get('skip')]
        self.title_label.setText(
            f"<b>Paths Created: {len(active_lines)}</b><br>"
            "Arrows show numbering direction. Adjust values below:"
        )

    def _build_rows(self):
        row_idx = 0
        
        # Header Row for Text Boxes
        radio_widget = QWidget()
        radio_layout = QHBoxLayout(radio_widget)
        radio_layout.setContentsMargins(0, 0, 0, 0)
        radio_layout.addWidget(self._rb_prefix)
        radio_layout.addWidget(self._rb_suffix)
        radio_layout.addStretch()
        self.grid_layout.addWidget(radio_widget, row_idx, 4)
        row_idx += 1

        for i, data in enumerate(self._line_data):
            if data.get('skip'):
                continue

            zoom_icon = QgsApplication.getThemeIcon('/mActionZoomIn.svg')
            del_icon = QgsApplication.getThemeIcon('/mActionRemove.svg')

            zoom_btn = QPushButton()
            zoom_btn.setIcon(zoom_icon)
            zoom_btn.setFixedSize(30, 30)
            zoom_btn.setToolTip("Zoom to this path")
            zoom_btn.setStyleSheet(
                f"QPushButton {{ border: 2px solid {data['color'].name()}; border-radius: 4px; background: transparent; }}"
                f"QPushButton:hover {{ background: rgba(0,0,0,0.05); }}"
            )
            zoom_btn.clicked.connect(
                lambda checked, d=data, idx=i: self._zoom_and_select(d, idx)
            )

            del_btn = QPushButton()
            del_btn.setIcon(del_icon)
            del_btn.setFixedSize(30, 30)
            del_btn.setToolTip("Delete this path")
            del_btn.setStyleSheet(
                "QPushButton { border: 1px solid #ccc; border-radius: 4px; background: transparent; }"
                "QPushButton:hover { background: #ffe6e6; border: 1px solid #ff4d4d; }"
            )
            del_btn.clicked.connect(
                lambda checked, d=data, idx=i: self._delete_row(d, idx)
            )

            path_lbl = QLabel(f"Path {i + 1}:")
            path_lbl.setStyleSheet("font-weight: normal;")
            path_lbl.setFixedWidth(45)

            spinbox = SmartSpinBox()
            spinbox.setMinimum(1)
            spinbox.setMaximum(9_999_999)
            spinbox.setFixedWidth(100)

            text_edit = QLineEdit()
            text_edit.setPlaceholderText("text...")
            text_edit.setMinimumWidth(130)

            feat_lbl = QLabel(f"({data['count']} feat.)")
            feat_lbl.setStyleSheet("color: #666; font-size: 11px;")
            feat_lbl.setMinimumWidth(60)

            self.grid_layout.addWidget(zoom_btn, row_idx, 0)
            self.grid_layout.addWidget(del_btn, row_idx, 1)
            self.grid_layout.addWidget(path_lbl, row_idx, 2)
            self.grid_layout.addWidget(spinbox, row_idx, 3)
            self.grid_layout.addWidget(text_edit, row_idx, 4)
            self.grid_layout.addWidget(feat_lbl, row_idx, 5)
            
            data['_row_widgets'] = [zoom_btn, del_btn, path_lbl, spinbox, text_edit, feat_lbl]
            self.spinboxes.append(spinbox)
            self.text_inputs.append(text_edit)
            row_idx += 1

            if len(self.text_inputs) > 1:
                carry_chk = QCheckBox("Carry over text")
                carry_chk.setStyleSheet("color: #555; font-size: 11px;")
                prev_edit = self.text_inputs[-2]
                carry_chk.stateChanged.connect(
                    lambda state, te=text_edit, pe=prev_edit:
                        self._on_carry_changed(state, te, pe)
                )
                self.grid_layout.addWidget(carry_chk, row_idx, 4)
                self._carry_pairs.append((carry_chk, text_edit))
                row_idx += 1
            else:
                self._carry_pairs.append((None, text_edit))

            if i < len(self._line_data) - 1:
                div = QFrame()
                div.setFrameShape(FRAME_HLINE)
                div.setFrameShadow(FRAME_PLAIN)
                div.setStyleSheet("color: #e0e0e0;")
                self.grid_layout.addWidget(div, row_idx, 0, 1, 6) 
                row_idx += 1

        self.grid_layout.setRowStretch(row_idx, 1)

    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self._clear_layout(item.layout())

    def update_data(self, new_line_data):
        state = self.get_state()
        self._line_data = new_line_data
        self._clear_layout(self.grid_layout)
        self.spinboxes.clear()
        self.text_inputs.clear()
        self._carry_pairs.clear()
        self._build_rows()
        self._update_title_label()
        self.restore_state(state)

    def _recalculate_starts(self):
        idx = self.pattern_combo.currentIndex()
        if idx == 0: 
            step = 1
            start = 1
            self.step_spin.setVisible(False)
        elif idx == 1: 
            step = 2
            start = 1
            self.step_spin.setVisible(False)
        elif idx == 2: 
            step = 2
            start = 2
            self.step_spin.setVisible(False)
        elif idx == 3: 
            step = self.step_spin.value()
            start = 1 
            self.step_spin.setVisible(True)

        current = start
        for i, data in enumerate(self._line_data):
            if data.get('skip'):
                continue
            active_idx = [j for j, d in enumerate(self._line_data) if not d.get('skip')].index(i)
            self.spinboxes[active_idx].setValue(current)
            current += data['count'] * step

    def get_step_value(self):
        idx = self.pattern_combo.currentIndex()
        if idx == 0: return 1
        if idx == 1: return 2
        if idx == 2: return 2
        if idx == 3: return self.step_spin.value()
        return 1

    def get_state(self):
        return {
            'target_field': self.field_combo.currentText(),
            'pattern_idx': self.pattern_combo.currentIndex(),
            'step_val': self.step_spin.value(),
            'mode_idx': self._mode_group.checkedId(),
            'affixes': [te.text() for te in self.text_inputs],
            'carry_overs': [chk.isChecked() if chk else False for chk, _ in self._carry_pairs]
        }

    def restore_state(self, state):
        self.field_combo.setCurrentText(state.get('target_field', 'sequence_no'))
        self.pattern_combo.setCurrentIndex(state.get('pattern_idx', 0))
        self.step_spin.setValue(state.get('step_val', 4))
        
        mode = state.get('mode_idx', 0)
        if mode == 0:
            self._rb_prefix.setChecked(True)
        elif mode == 1:
            self._rb_suffix.setChecked(True)
            
        affixes = state.get('affixes', [])
        carry_overs = state.get('carry_overs', [])
        
        for i, te in enumerate(self.text_inputs):
            if i < len(affixes):
                te.setText(affixes[i])
                
        for i, (chk, _) in enumerate(self._carry_pairs):
            if chk and i < len(carry_overs):
                chk.setChecked(carry_overs[i])
                
        self._recalculate_starts()

    def keyPressEvent(self, event):
        if event.key() == KEY_DELETE and self.tool_ref is not None:
            sel = self.tool_ref.selected_idx
            if sel is not None and 0 <= sel < len(self._line_data):
                data = self._line_data[sel]
                if not data.get('skip', False):
                    self._delete_row(data, sel)
            return          
        super().keyPressEvent(event)

    def _on_carry_changed(self, state, this_edit, prev_edit):
        if state == STATE_CHECKED:
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
        extent = data['geom'].boundingBox()
        extent.scale(1.3)
        self.canvas.setExtent(extent)
        self.canvas.refresh()
        if self.tool_ref is not None:
            self.tool_ref.select_line(idx)

    def _delete_row(self, data, idx):
        data['skip'] = True
        self.update_data(self._line_data)
        if self.tool_ref is not None:
            self.tool_ref.hide_path_rubbers(idx)
            
        self._recalculate_starts()

    def is_prefix_mode(self):
        return self._rb_prefix.isChecked()
        
    def get_start_values(self):
        return [sb.value() for sb in self.spinboxes]

    def get_affix_values(self):
        return [te.text() for te in self.text_inputs]

    def closeEvent(self, event):
        self.settings.setValue("DrawSeq/ReviewDialog/Geometry", self.saveGeometry())
        super().closeEvent(event)
        
    def accept(self):
        self.settings.setValue("DrawSeq/ReviewDialog/Geometry", self.saveGeometry())
        super().accept()
        
    def reject(self):
        self.settings.setValue("DrawSeq/ReviewDialog/Geometry", self.saveGeometry())
        super().reject()


# ---------------------------------------------------------------------------
# SequenceNumberingTool
# ---------------------------------------------------------------------------

class SequenceNumberingTool(QgsMapTool):
    _SEL_LINE_COLOR   = QColor(255, 80,  0)
    _SEL_VERTEX_COLOR = QColor(255, 80,  0)
    _NORMAL_VERTEX_BG = QColor(0,   0,   0)
    _NORMAL_VERTEX_FG = QColor(255, 255, 255)

    def __init__(self, canvas, target_layer, selected_only=False):
        super().__init__(canvas)
        self.canvas        = canvas
        self.layer         = target_layer
        self.selected_only = selected_only

        self.finished_lines  = []
        self.current_points  = []
        self.drag_info       = None
        self.selected_idx    = None
        
        self._did_selection       = False   
        self._ignore_next_release = False
        self.review_dlg           = None  
        self._MIN_SNAP_PX         = 8       

        self.hue_accumulator        = 0.35
        self.golden_ratio_conjugate = 0.618033988749895

        self.active_rubberband = self._make_rubberband(QColor(180, 180, 180), dashed=True)
        self.active_arrow      = self._make_arrow_polygon(alpha=120)

    def _make_rubberband(self, color, dashed=False, width=3):
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        rb.setColor(color)
        rb.setWidth(width)
        if dashed:
            rb.setLineStyle(LINE_DASH)
        return rb

    def _make_arrow_polygon(self, alpha=255):
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        rb.setColor(QColor(0, 0, 0, alpha))
        rb.setStrokeColor(QColor(255, 255, 255, alpha))
        rb.setWidth(1.5)
        return rb

    def _make_vertex_rb(self):
        vrb = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        vrb.setIcon(QgsRubberBand.ICON_FULL_BOX)
        vrb.setIconSize(7)
        vrb.setColor(self._NORMAL_VERTEX_BG)
        vrb.setSecondaryStrokeColor(self._NORMAL_VERTEX_FG)
        return vrb

    def _make_sel_rb(self):
        srb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        sel_color = QColor(self._SEL_LINE_COLOR)
        sel_color.setAlpha(160)
        srb.setColor(sel_color)
        srb.setWidth(7)
        return srb

    def _rebuild_vertex_dots(self, idx):
        data = self.finished_lines[idx]
        vrb  = data['vertex_rb']
        vrb.reset(QgsWkbTypes.PointGeometry)
        for pt in data['points']:
            vrb.addPoint(pt)

    def _build_arrow_geom(self, p1, p2):
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
            QgsPointXY(br_x, br_y),
            QgsPointXY(tip_x, tip_y) 
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

    def _sync_review_dialog(self):
        if getattr(self, 'review_dlg', None) and self.review_dlg.isVisible():
            self._process_multiple_lines(is_sync=True)

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
        self._sync_review_dialog()

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

    def _get_2m_in_units(self, crs):
        try:
            unit = crs.mapUnits()
            if unit == Qgis.DistanceUnit.Degrees:
                return 2.0 / 111319.49
            elif unit == Qgis.DistanceUnit.Feet:
                return 2.0 * 3.28084
            else:
                return 2.0
        except AttributeError:
            unit = crs.mapUnits()
            if unit == QgsUnitTypes.DistanceDegrees:
                return 2.0 / 111319.49
            elif unit == QgsUnitTypes.DistanceFeet:
                return 2.0 * 3.28084
            else:
                return 2.0

    def keyPressEvent(self, event):
        if event.key() == KEY_DELETE:
            if self.selected_idx is not None:
                self._delete_selected()
            return

        undo = (event.key() == KEY_BACKSPACE or
                (event.key() == KEY_Z and event.modifiers() & MOD_CTRL))
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
        if event.button() != BTN_LEFT:
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
        if self.drag_info:
            self.drag_info      = None
            self._did_selection = False
            self._sync_review_dialog() 
            return

        point = self.toMapCoordinates(event.pos())
        
        if self._ignore_next_release:
            self._ignore_next_release = False
            return

        if event.button() == BTN_LEFT:
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

        elif event.button() == BTN_MIDDLE:
            tol = self._pixel_tolerance()
            for i, line_data in enumerate(self.finished_lines):
                dist, _, _, _ = QgsGeometry.fromPolylineXY(
                    line_data['points']
                ).closestSegmentWithContext(point)
                if math.sqrt(dist) < tol:
                    line_data['points'].reverse()
                    self._update_finished_line_visuals(i)
                    self._sync_review_dialog() 
                    return

        elif event.button() == BTN_RIGHT:
            if len(self.current_points) >= 2:
                
                if self.layer.geometryType() == QgsWkbTypes.PointGeometry:
                    canvas_crs = self.canvas.mapSettings().destinationCrs()
                    layer_crs = self.layer.crs()
                    
                    dist_canvas = self._get_2m_in_units(canvas_crs)
                    dist_layer = self._get_2m_in_units(layer_crs)
                    
                    canvas_geom = QgsGeometry.fromPolylineXY(self.current_points)
                    project = QgsProject.instance()
                    
                    transform_to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, project)
                    transform_to_layer = QgsCoordinateTransform(canvas_crs, layer_crs, project)
                    
                    search_geom = QgsGeometry(canvas_geom)
                    try:
                        search_geom.transform(transform_to_layer)
                    except Exception:
                        pass
                    
                    bbox = search_geom.boundingBox()
                    bbox.setXMinimum(bbox.xMinimum() - dist_layer)
                    bbox.setXMaximum(bbox.xMaximum() + dist_layer)
                    bbox.setYMinimum(bbox.yMinimum() - dist_layer)
                    bbox.setYMaximum(bbox.yMaximum() + dist_layer)
                    
                    request = QgsFeatureRequest().setFilterRect(bbox)
                    if self.selected_only:
                        selected_ids = self.layer.selectedFeatureIds()
                        if not selected_ids:
                            request.setFilterFids([])
                        else:
                            request.setFilterFids(selected_ids)
                    
                    segment_snaps = {i: [] for i in range(len(self.current_points) - 1)}
                    
                    for feat in self.layer.getFeatures(request):
                        geom = feat.geometry()
                        if geom.isNull():
                            continue
                        try:
                            geom.transform(transform_to_canvas)
                        except Exception:
                            pass
                        
                        if geom.type() == QgsWkbTypes.PointGeometry:
                            pts = geom.asMultiPoint() if geom.isMultipart() else [geom.asPoint()]
                            for pt_canvas in pts:
                                dist, snapped_pt, next_vertex, _ = canvas_geom.closestSegmentWithContext(pt_canvas)
                                if math.sqrt(dist) <= dist_canvas:
                                    segment_idx = next_vertex - 1
                                    if segment_idx < 0: segment_idx = 0
                                    if segment_idx >= len(self.current_points) - 1:
                                        segment_idx = len(self.current_points) - 2
                                        
                                    seg_start = self.current_points[segment_idx]
                                    sq_dist = (snapped_pt.x() - seg_start.x())**2 + (snapped_pt.y() - seg_start.y())**2
                                    segment_snaps[segment_idx].append((sq_dist, pt_canvas))
                    
                    new_points = []
                    for i in range(len(self.current_points) - 1):
                        if not new_points or new_points[-1].distance(self.current_points[i]) > 1e-6:
                            new_points.append(self.current_points[i])
                        
                        snaps = segment_snaps[i]
                        snaps.sort(key=lambda x: x[0])
                        for snap in snaps:
                            if new_points[-1].distance(snap[1]) > 1e-6:
                                new_points.append(snap[1])
                                
                    if new_points[-1].distance(self.current_points[-1]) > 1e-6:
                        new_points.append(self.current_points[-1])
                        
                    self.current_points = new_points

                line_geom = QgsGeometry.fromPolylineXY(self.current_points)
                color     = self.get_next_distinct_color()

                self.active_rubberband.setColor(color)
                self.active_rubberband.setLineStyle(LINE_SOLID)

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
                
                self._sync_review_dialog() 

            elif len(self.current_points) == 1:
                self.current_points = []
                self.active_rubberband.reset()
                self.active_arrow.reset()
                self.canvas.refresh()

            elif len(self.current_points) == 0 and self.finished_lines:
                if not getattr(self, 'review_dlg', None) or not self.review_dlg.isVisible():
                    self._process_multiple_lines()

    def canvasDoubleClickEvent(self, event):
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
                self._sync_review_dialog() 
                return

            geom = QgsGeometry.fromPolylineXY(pts)
            dist, _, after_vertex, _ = geom.closestSegmentWithContext(point)
            if math.sqrt(dist) < tol:
                pts.insert(after_vertex, point)
                self._update_finished_line_visuals(i)
                self._sync_review_dialog() 
                return

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _process_multiple_lines(self, is_sync=False):
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs  = self.layer.crs()
        project    = QgsProject.instance()
        transform  = QgsCoordinateTransform(canvas_crs, layer_crs, project)

        if self.selected_only:
            selected_ids = self.layer.selectedFeatureIds()
            if not selected_ids:
                if not is_sync:
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
                except Exception:
                    pass

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

        if getattr(self, 'review_dlg', None) and self.review_dlg.isVisible():
            self.review_dlg.update_data(line_data_results)
        else:
            if not self.finished_lines:
                return 

            self.review_dlg = MultiLineDialog(line_data_results, self.canvas, self.layer, tool_ref=self)
            self.review_dlg.setWindowFlags(self.review_dlg.windowFlags() | STAYS_ON_TOP)
            
            self.review_dlg.accepted.connect(lambda: self._commit_sequence_numbers(self.review_dlg._line_data, reuse=False))
            self.review_dlg.reuse_btn.clicked.connect(lambda checked=False: self._commit_sequence_numbers(self.review_dlg._line_data, reuse=True))
            self.review_dlg.rejected.connect(self.cleanup)

            self.review_dlg.show()
            if not is_sync:
                self.review_dlg.raise_()
                self.review_dlg.activateWindow()

    def _commit_sequence_numbers(self, line_data_results, reuse=False):
        prefix_mode  = self.review_dlg.is_prefix_mode()
        start_values = self.review_dlg.get_start_values()
        affix_values = self.review_dlg.get_affix_values()
        step = self.review_dlg.get_step_value()
        target_field = self.review_dlg.get_target_field()
        
        idx = self.layer.fields().indexOf(target_field)
        if idx == -1:
            new_field = QgsField(target_field, TYPE_STRING)
            if self.layer.isEditable():
                self.layer.addAttribute(new_field)
            else:
                self.layer.dataProvider().addAttributes([new_field])
            self.layer.updateFields()
            idx = self.layer.fields().indexOf(target_field)
            if idx == -1:
                QMessageBox.critical(None, "DrawSeq", f"Could not create field for '{target_field}'.")
                if not reuse: 
                    self.cleanup()
                return
                    
        field_type = self.layer.fields().field(idx).type()

        was_editable = self.layer.isEditable()
        if not was_editable:
            self.layer.startEditing()

        self.layer.beginEditCommand("DrawSeq Numbering")

        def get_first_touch(f, line_geom):
            ix = line_geom.intersection(f.geometry())
            if ix.isNull() or ix.isEmpty():
                return line_geom.lineLocatePoint(f.geometry().centroid())
            min_dist = float('inf')
            for v in ix.vertices():
                pt_geom = QgsGeometry.fromPointXY(QgsPointXY(v.x(), v.y()))
                dist = line_geom.lineLocatePoint(pt_geom)
                if dist < min_dist:
                    min_dist = dist
            return min_dist if min_dist != float('inf') else line_geom.lineLocatePoint(f.geometry().centroid())

        for i, data in enumerate(line_data_results):
            if data.get('skip'):
                continue
            seq   = start_values[i]
            affix = affix_values[i]
            
            sorted_feats = sorted(
                data['features'],
                key=lambda f: get_first_touch(f, data['layer_geom'])
            )
            
            for feat in sorted_feats:
                if affix:
                    val_str = f"{affix}{seq}" if prefix_mode else f"{seq}{affix}"
                    final_value = val_str
                else:
                    if field_type in (TYPE_INT, TYPE_UINT, TYPE_LONGLONG):
                        final_value = int(seq)
                    elif field_type == TYPE_DOUBLE:
                        final_value = float(seq)
                    else:
                        final_value = str(seq)

                self.layer.changeAttributeValue(feat.id(), idx, final_value)
                seq += step

        self.layer.endEditCommand()

        if not was_editable:
            success = self.layer.commitChanges()
            if not success:
                QMessageBox.warning(
                    None, "DrawSeq - Database Save Issue",
                    "The sequence numbers were successfully applied, but QGIS blocked the automatic save to the database.\n\n"
                    "This usually happens when your layer has invalid data in other fields.\n\n"
                    "Your numbers are safe! The layer has been left in Edit Mode. You can fix your layer's errors and click the QGIS Save button manually."
                )

        self._apply_labels(target_field)
        self.canvas.refreshAllLayers()
        
        if not reuse:
            self.cleanup()
        else:
            fields = [f.name() for f in self.layer.fields()]
            current_idx = fields.index(target_field) if target_field in fields else 0
            
            new_field, ok = QInputDialog.getItem(
                self.review_dlg, 
                "Reuse Successful", 
                "Data saved! The lines are preserved on your map.\n\nSelect or type the Target Field for your NEXT operation:", 
                fields, 
                current_idx, 
                True 
            )
            
            if ok and new_field.strip():
                if self.review_dlg.field_combo.findText(new_field.strip()) == -1:
                    self.review_dlg.field_combo.insertItem(0, new_field.strip())
                self.review_dlg.field_combo.setCurrentText(new_field.strip())

    def _apply_labels(self, target_field):
        pal           = QgsPalLayerSettings()
        pal.enabled   = True
        pal.scaleVisibility = True
        pal.minimumScale = 5000  

        pal.isExpression = False
        pal.fieldName = target_field

        text_fmt = QgsTextFormat()
        text_fmt.setFont(QFont('Arial', 13, FONT_WEIGHT_BOLD))
        text_fmt.setSize(13)
        text_fmt.setColor(QColor('LightSeaGreen'))

        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(1)
        buf.setColor(QColor('white'))
        text_fmt.setBuffer(buf)

        bg = QgsTextBackgroundSettings()
        bg.setEnabled(True)
        bg.setType(QgsTextBackgroundSettings.ShapeRectangle)
        bg.setFillColor(QColor('#A0A0A0'))
        bg.setStrokeColor(QColor('#606060'))
        bg.setStrokeWidth(0.3)
        bg.setOpacity(0.85)
        bg.setSizeType(QgsTextBackgroundSettings.SizeBuffer)
        bg.setSize(QSizeF(1.0, 0.5))
        text_fmt.setBackground(bg)

        pal.setFormat(text_fmt)

        self.layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        self.layer.setLabelsEnabled(True)
        self.layer.triggerRepaint()

    def deactivate(self):
        self.cleanup()
        super().deactivate()

    def cleanup(self):
        if getattr(self, 'review_dlg', None):
            try:
                self.review_dlg.rejected.disconnect(self.cleanup)
            except TypeError:
                pass 
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