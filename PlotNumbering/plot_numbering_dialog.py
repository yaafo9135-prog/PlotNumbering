# Plot Numbering — QGIS plugin
# Copyright (C) 2026 Hamadu Hudu Yaafo
# This file is part of Plot Numbering.
#
# Plot Numbering is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Plot Numbering is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# LICENSE file for details.

import os

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings, QSize, Qt
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QSizePolicy, QListView, QPlainTextEdit
from qgis.PyQt.QtGui import QPixmap
from qgis.core import QgsProject, QgsVectorLayer, Qgis
from qgis.gui import QgsMapLayerComboBox

# Qt5/Qt6 enum compatibility helpers.
_QtWindowType = getattr(Qt, "WindowType", Qt)
_QtAspectRatioMode = getattr(Qt, "AspectRatioMode", Qt)
_QtTransformationMode = getattr(Qt, "TransformationMode", Qt)
_SizePolicy = getattr(QSizePolicy, "Policy", QSizePolicy)
_LineWrapMode = getattr(QPlainTextEdit, "LineWrapMode", QPlainTextEdit)

try:
    from qgis.gui import QgsMapLayerProxyModel
except ImportError:
    QgsMapLayerProxyModel = None

from .plot_numbering_logic import (
    available_order_modes,
    generate_numbers,
    apply_numbers,
    set_simple_labels,
    is_null_value,
    ensure_output_field_before_edit,
)

UI_PATH = os.path.join(os.path.dirname(__file__), "ui", "plot_numbering_dialog.ui")
FORM_CLASS, _ = uic.loadUiType(UI_PATH)


class PlotNumberingDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setupUi(self)
        self._install_qgis_layer_selector()
        self._preview = {}
        self._start_point = None
        self._point_tool = None
        self._old_tool = None
        self._last_preview_signature = None

        self._configure_controls()
        self._populate_layers()
        self._populate_modes()
        self._connect_signals()
        self._restore_settings()
        self._layer_changed()
        self._order_changed()
        self._update_block_controls()
        self._update_selection_status()

    def _configure_controls(self):
        self.setMinimumSize(QSize(620, 480))
        self.resize(760, 620)
        self.setWindowFlags(_QtWindowType.Window | _QtWindowType.WindowTitleHint | _QtWindowType.WindowSystemMenuHint | _QtWindowType.WindowMinimizeButtonHint | _QtWindowType.WindowCloseButtonHint)
        logo_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            self.logoLabel.setPixmap(pix.scaled(self.logoLabel.size(), _QtAspectRatioMode.KeepAspectRatio, _QtTransformationMode.SmoothTransformation))
            self.logoLabel.setToolTip("Plot Numbering")
        self.setWindowTitle("Plot Numbering")

        # Clean, compact Qt6-friendly visual styling. Layout geometry remains
        # in the .ui file so the interface stays easy to maintain.
        self.setStyleSheet("""
            QDialog { background: palette(window); }
            QFrame#headerFrame { border: 1px solid palette(mid); border-radius: 10px; background: palette(base); }
            QGroupBox { font-weight: 700; margin-top: 9px; padding-top: 6px; border: 1px solid palette(mid); border-radius: 7px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QLabel#titleLabel { font-size: 14pt; font-weight: 700; }
            QLabel#subtitleLabel { font-size: 9pt; }
            QLabel#layerInfoLabel, QLabel#selectionInfoLabel, QLabel#methodHelpLabel { color: palette(mid); }
            QComboBox, QLineEdit, QSpinBox { min-height: 25px; padding: 1px 5px; }
            QPushButton { min-height: 26px; padding: 2px 9px; }
            QCheckBox, QRadioButton { spacing: 5px; }
            QPushButton:hover { border: 1px solid palette(highlight); }
            QPlainTextEdit { border: 1px solid palette(mid); border-radius: 6px; }
            QScrollArea { border: none; background: transparent; }
        """)

        for combo in (self.layerCombo, self.fieldCombo, self.orderCombo, self.blockFieldCombo):
            combo.setMinimumHeight(26)
            combo.setSizePolicy(_SizePolicy.Expanding, _SizePolicy.Fixed)
            combo.setMinimumContentsLength(16)
            combo.setView(QListView())
            combo.view().setMinimumWidth(360)

        self.orderCombo.view().setMinimumWidth(430)
        self.layerCombo.view().setMinimumWidth(360)
        self.fieldCombo.view().setMinimumWidth(360)
        self.blockFieldCombo.view().setMinimumWidth(360)

        self.startSpin.setRange(0, 999999999)
        self.startSpin.setValue(1)
        self.paddingSpin.setRange(0, 12)
        self.paddingSpin.setValue(0)
        self.paddingSpin.setToolTip("0 = normal numbers (1, 2, 3). Increase only if you explicitly want leading zeros.")
        self.directionSpin.setRange(0, 359)
        self.directionSpin.setValue(0)
        self.blockPaddingSpin.setRange(0, 8)
        self.blockPaddingSpin.setValue(0)

        for button in (self.refreshButton, self.previewButton, self.applyButton, self.pickStartButton):
            button.setMinimumHeight(27)

        self.previewText.setLineWrapMode(_LineWrapMode.NoWrap)
        self.previewText.setMinimumHeight(150)

        self.orderCombo.setToolTip("Choose how plots are ordered. Automatic Block/Grid is the recommended method for cadastral blocks.")
        self.selectionCheck.setToolTip("Only currently selected polygons are included.")
        self.skipExistingCheck.setToolTip("Do not reuse a number already present in the selected scope.")
        self.continueExistingCheck.setToolTip("Start after the highest integer value already present.")

    def _connect_signals(self):
        self.fieldCombo.currentIndexChanged.connect(self._invalidate_preview)
        self.orderCombo.currentIndexChanged.connect(self._order_changed)
        self.previewButton.clicked.connect(self.preview)
        self.applyButton.clicked.connect(self.apply)
        self.refreshButton.clicked.connect(self.refresh_layers)
        self.pickStartButton.clicked.connect(self.pick_start_point)
        self.selectionCheck.toggled.connect(self._update_selection_status)
        self.selectionCheck.toggled.connect(self._invalidate_preview)
        self.skipExistingCheck.toggled.connect(self._invalidate_preview)
        self.continueExistingCheck.toggled.connect(self._invalidate_preview)
        self.blockCheck.toggled.connect(self._update_block_controls)
        self.blockCheck.toggled.connect(self._invalidate_preview)
        self.blockFieldCombo.currentIndexChanged.connect(self._invalidate_preview)
        self.startSpin.valueChanged.connect(self._invalidate_preview)
        self.paddingSpin.valueChanged.connect(self._invalidate_preview)
        self.directionSpin.valueChanged.connect(self._invalidate_preview)
        self.prefixEdit.textChanged.connect(self._invalidate_preview)
        self.suffixEdit.textChanged.connect(self._invalidate_preview)
        self.blockSeparatorEdit.textChanged.connect(self._invalidate_preview)
        self.blockPaddingSpin.valueChanged.connect(self._invalidate_preview)

    def closeEvent(self, event):
        self._save_settings()
        self._restore_map_tool()
        super().closeEvent(event)

    def _save_settings(self):
        s = QSettings()
        s.setValue("PlotNumbering/lastOrder", self.orderCombo.currentData())
        s.setValue("PlotNumbering/start", self.startSpin.value())
        s.setValue("PlotNumbering/prefix", self.prefixEdit.text())
        s.setValue("PlotNumbering/suffix", self.suffixEdit.text())
        s.setValue("PlotNumbering/padding", self.paddingSpin.value())
        s.setValue("PlotNumbering/blockPadding", self.blockPaddingSpin.value())
        s.setValue("PlotNumbering/settingsVersion", 6)
        s.setValue("PlotNumbering/direction", self.directionSpin.value())

    def _restore_settings(self):
        s = QSettings()
        order = s.value("PlotNumbering/lastOrder", "auto_block_grid")
        idx = self.orderCombo.findData(order)
        if idx >= 0:
            self.orderCombo.setCurrentIndex(idx)
        self.startSpin.setValue(int(s.value("PlotNumbering/start", 1)))
        self.prefixEdit.setText(str(s.value("PlotNumbering/prefix", "")))
        self.suffixEdit.setText(str(s.value("PlotNumbering/suffix", "")))
        # v1.5 intentionally resets legacy padding so existing v1.2-v1.4
        # settings cannot unexpectedly produce 001, 002, 003.
        settings_version = int(s.value("PlotNumbering/settingsVersion", 0))
        if settings_version < 6:
            self.paddingSpin.setValue(0)
            self.blockPaddingSpin.setValue(0)
            auto_idx = self.orderCombo.findData("auto_block_grid")
            if auto_idx >= 0:
                self.orderCombo.setCurrentIndex(auto_idx)
            s.setValue("PlotNumbering/settingsVersion", 6)
        else:
            self.paddingSpin.setValue(int(s.value("PlotNumbering/padding", 0)))
            self.blockPaddingSpin.setValue(int(s.value("PlotNumbering/blockPadding", 0)))
        self.directionSpin.setValue(int(s.value("PlotNumbering/direction", 0)))

    def refresh_layers(self):
        current_layer = self._layer()
        self._populate_layers()
        if current_layer is not None:
            try:
                self.layerCombo.setLayer(current_layer)
            except Exception:
                pass
        self._layer_changed()
        self.statusLabel.setText("Layer list refreshed.")

    def _is_polygon_layer(self, layer):
        """Return True for polygon vector layers across QGIS 3/4 enum variants."""
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return False
        # QGIS 4 / newer QGIS exposes QgsVectorLayer.geometryType() as
        # Qgis.GeometryType.Polygon. Keep a WKB fallback for providers and
        # compatibility builds which still expose QgsWkbTypes enums.
        try:
            if layer.geometryType() == Qgis.GeometryType.Polygon:
                return True
        except Exception:
            pass
        try:
            from qgis.core import QgsWkbTypes
            if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                return True
        except Exception:
            pass
        try:
            from qgis.core import QgsWkbTypes
            return QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry
        except Exception:
            return False

    def _install_qgis_layer_selector(self):
        """Replace the generic designer combo with QGIS's native dynamic layer selector.

        QGIS documents QgsMapLayerComboBox as the preferred widget for selecting
        project layers because it stays synchronized with the current project.
        """
        old = self.layerCombo
        parent = old.parentWidget()
        replacement = QgsMapLayerComboBox(parent)
        replacement.setObjectName("layerCombo")
        replacement.setProject(QgsProject.instance())
        replacement.setAllowEmptyLayer(True, "— Select polygon layer —")
        # QGIS 4 exposes Qgis.LayerFilter; QGIS 3 exposes
        # QgsMapLayerProxyModel.  Use the native selector in both.
        try:
            replacement.setFilters(Qgis.LayerFilter.VectorLayer | Qgis.LayerFilter.PolygonLayer)
        except Exception:
            if QgsMapLayerProxyModel is not None:
                try:
                    replacement.setFilters(QgsMapLayerProxyModel.PolygonLayer)
                except Exception:
                    try:
                        replacement.setFilters(QgsMapLayerProxyModel.VectorLayer | QgsMapLayerProxyModel.PolygonLayer)
                    except Exception:
                        pass
        replacement.setShowCrs(True)
        replacement.setMinimumHeight(36)
        replacement.setMinimumContentsLength(20)
        replacement.setView(QListView())
        replacement.view().setMinimumWidth(600)
        layout = old.parentWidget().layout() if old.parentWidget() else None
        if layout is not None:
            layout.replaceWidget(old, replacement)
        old.deleteLater()
        self.layerCombo = replacement
        self.layerCombo.layerChanged.connect(lambda _layer: self._layer_changed())

    def _populate_layers(self):
        # QgsMapLayerComboBox is automatically synchronized with QgsProject.
        # Refresh is retained as a user-facing action for consistency.
        try:
            self.layerCombo.setProject(QgsProject.instance())
        except Exception:
            pass

    def _populate_modes(self):
        self.orderCombo.clear()
        for key, label in available_order_modes():
            self.orderCombo.addItem(label, key)

    def _layer(self):
        try:
            layer = self.layerCombo.currentLayer()
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                return layer
        except Exception:
            pass
        layer_id = self.layerCombo.currentData()
        return QgsProject.instance().mapLayer(layer_id) if layer_id else None

    def _layer_changed(self):
        layer = self._layer()
        self.fieldCombo.clear()
        self.blockFieldCombo.clear()
        self._start_point = None
        self.startPointLabel.setText("Start: not selected")
        if not layer:
            self.layerInfoLabel.setText("No polygon layer available.")
            self.selectionCheck.setEnabled(False)
            self._invalidate_preview()
            return

        self.fieldCombo.addItem("— Select plot number field —", "")
        self.blockFieldCombo.addItem("— Select block field —", "")
        for f in layer.fields():
            self.fieldCombo.addItem(f.name(), f.name())
            self.blockFieldCombo.addItem(f.name(), f.name())

        preferred = next(
            (i for i in range(self.fieldCombo.count())
             if self.fieldCombo.itemText(i).lower() in
             ("plot_no", "plotno", "plot_number", "plotnumber", "parcel_no", "plot no")),
            -1
        )
        if preferred >= 0:
            self.fieldCombo.setCurrentIndex(preferred)

        count = layer.featureCount()
        selected = layer.selectedFeatureCount()
        self.layerInfoLabel.setText(f"{count:,} polygon(s) in layer  •  {selected:,} currently selected")
        self.selectionCheck.setEnabled(selected > 0)
        self._update_selection_status()
        self._invalidate_preview()

    def _update_selection_status(self):
        layer = self._layer()
        if not layer:
            self.selectionInfoLabel.setText("No layer selected.")
            return
        selected = layer.selectedFeatureCount()
        self.selectionInfoLabel.setText(
            f"Scope: {selected:,} selected polygon(s)." if self.selectionCheck.isChecked()
            else f"Scope: all {layer.featureCount():,} polygon(s)."
        )

    def _update_block_controls(self):
        enabled = self.blockCheck.isChecked()
        self.blockFieldCombo.setEnabled(enabled)
        self.blockSeparatorEdit.setEnabled(enabled)
        self.blockPaddingSpin.setEnabled(enabled)

    def _order_changed(self):
        mode = self.orderCombo.currentData()
        interactive = mode == "interactive"
        self.pickStartButton.setEnabled(interactive)
        self.directionSpin.setEnabled(interactive)
        if interactive:
            self.methodHelpLabel.setText("Pick a start point and direction on the map.")
        elif mode == "grid":
            self.methodHelpLabel.setText("Grid rows and columns.")
        elif mode == "auto_block_grid":
            self.methodHelpLabel.setText("Automatic Block/Grid: follows local plot blocks with short-side-first numbering and continuous block progression.")
        elif mode == "clockwise":
            self.methodHelpLabel.setText("Clockwise around the current numbering scope.")
        else:
            self.methodHelpLabel.setText("Directional ordering by polygon position.")
        self._invalidate_preview()

    def _invalidate_preview(self):
        if hasattr(self, "previewText"):
            self._preview = {}
            self.previewText.clear()
            self.statusLabel.setText("Settings changed — click Preview numbering to recalculate.")

    def pick_start_point(self):
        self._restore_map_tool()
        QMessageBox.information(self, "Pick numbering start", "Click OK, then click the desired starting location on the QGIS map canvas.")
        canvas = self.iface.mapCanvas()
        self._old_tool = canvas.mapTool()
        from qgis.gui import QgsMapToolEmitPoint
        dialog = self

        class PointTool(QgsMapToolEmitPoint):
            def __init__(self, canvas):
                super().__init__(canvas)
            def canvasReleaseEvent(self, event):
                point = self.toMapCoordinates(event.pos())
                dialog._start_point = (point.x(), point.y())
                dialog.startPointLabel.setText(f"Start: {point.x():.3f}, {point.y():.3f}")
                dialog._restore_map_tool()
                dialog._invalidate_preview()

        self._point_tool = PointTool(canvas)
        canvas.setMapTool(self._point_tool)

    def _restore_map_tool(self):
        if self._point_tool is not None:
            try:
                self.iface.mapCanvas().unsetMapTool(self._point_tool)
            except Exception:
                pass
            self._point_tool = None
        if self._old_tool is not None:
            try:
                self.iface.mapCanvas().setMapTool(self._old_tool)
            except Exception:
                pass
            self._old_tool = None

    def _options(self):
        return {
            "order": self.orderCombo.currentData(),
            "start": int(self.startSpin.value()),
            "prefix": self.prefixEdit.text(),
            "suffix": self.suffixEdit.text(),
            "padding": int(self.paddingSpin.value()),
            "skip_existing": self.skipExistingCheck.isChecked(),
            "continue_existing": self.continueExistingCheck.isChecked(),
            "start_point": self._start_point,
            "direction_degrees": int(self.directionSpin.value()),
            "block_field": self.blockFieldCombo.currentData() if self.blockCheck.isChecked() else None,
            "block_separator": self.blockSeparatorEdit.text(),
            "block_padding": int(self.blockPaddingSpin.value()),
        }

    def _features(self):
        layer = self._layer()
        if not layer:
            return []
        return list(layer.selectedFeatures()) if self.selectionCheck.isChecked() else list(layer.getFeatures())

    def _make_numbers(self):
        layer = self._layer()
        features = self._features()
        field = self.fieldCombo.currentData() or "plot_no"
        existing = []
        for f in features:
            try:
                value = f[field]
            except Exception:
                continue
            if not is_null_value(value):
                existing.append(str(value).strip())
        return generate_numbers(features, existing_values=existing, **self._options())

    def preview(self):
        layer = self._layer()
        if not layer:
            QMessageBox.warning(self, "Plot Numbering", "Select a polygon layer first.")
            return
        features = self._features()
        if not features:
            QMessageBox.warning(self, "Plot Numbering", "There are no polygons in the current numbering scope.")
            return
        if self.orderCombo.currentData() == "interactive" and self._start_point is None:
            QMessageBox.warning(self, "Start point required", "Pick a start point on the map before previewing interactive numbering.")
            return

        self._preview = self._make_numbers()
        if not self._preview or any(is_null_value(v) for v in self._preview.values()):
            self._preview = {}
            QMessageBox.critical(self, "Invalid preview", "The numbering engine produced an empty/NULL plot number. No edits were made.")
            return

        rows = []
        for position, (fid, value) in enumerate(self._preview.items(), start=1):
            rows.append(f"{position:>5}   {fid:>10}   {str(value)}")
            if position >= 200:
                break
        if len(self._preview) > 200:
            rows.append(f"... {len(self._preview) - 200:,} more polygon(s)")
        self.previewText.setPlainText("ORDER     FEATURE ID   PLOT NUMBER\n" + "-" * 58 + "\n" + "\n".join(rows))

        selected_field = self.fieldCombo.currentData()
        field_obj = layer.fields().field(selected_field) if selected_field else None
        note = ""
        if field_obj is not None and field_obj.isNumeric():
            formatted = [str(v) for v in self._preview.values()]
            needs_text = any(
                not __import__('re').fullmatch(r"[+-]?\d+", v) or
                (len(v.lstrip("+-")) > 1 and v.lstrip("+-").startswith("0"))
                for v in formatted
            )
            if needs_text:
                note = " • Apply will create a compatible text field because the selected field is numeric"
        self.statusLabel.setText(f"Preview ready • {len(self._preview):,} plot number(s) • layer unchanged{note}")

    def apply(self):
        layer = self._layer()
        if not layer:
            QMessageBox.warning(self, "Plot Numbering", "Select a polygon layer first.")
            return

        features = self._features()
        if not features:
            QMessageBox.warning(self, "Plot Numbering", "There are no polygons in the current numbering scope.")
            return

        if self.orderCombo.currentData() == "interactive" and self._start_point is None:
            QMessageBox.warning(self, "Start point required", "Pick a start point on the map before applying interactive numbering.")
            return

        requested_field = self.fieldCombo.currentData() or "Plot No"
        values = self._make_numbers()
        if not values:
            QMessageBox.information(self, "Plot Numbering", "Nothing to number.")
            return
        if any(is_null_value(v) or str(v).strip() == "" for v in values.values()):
            QMessageBox.critical(self, "Invalid numbering", "The numbering engine produced a NULL/empty value. No edits were made.")
            return

        # v1.5: schema compatibility is resolved BEFORE edit mode starts.
        # This avoids stale provider field maps and the OGR/QGIS QString commit
        # error seen with the previous versions.
        try:
            field, created = ensure_output_field_before_edit(layer, requested_field, values)
        except Exception as exc:
            QMessageBox.critical(self, "Output field error", str(exc))
            return

        target_text = field
        if created:
            target_text += " (new compatible text field)"

        answer = QMessageBox.question(
            self,
            "Confirm numbering",
            f"Apply {len(values):,} plot number(s) to '{target_text}'?\n\n"
            f"First number: {next(iter(values.values()))}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            # If a schema field was created before confirmation, remove it so
            # cancelling does not leave an unwanted empty field behind.
            if created:
                idx = layer.fields().indexOf(field)
                if idx >= 0:
                    layer.dataProvider().deleteAttributes([idx])
                    layer.updateFields()
            return

        editing_started = False
        try:
            if not layer.isEditable():
                if not layer.startEditing():
                    raise RuntimeError("Could not start editing this layer.")
                editing_started = True

            apply_numbers(layer, field, values)

            if self.labelCheck.isChecked():
                set_simple_labels(layer, field)

            if not layer.commitChanges():
                errors = "; ".join(layer.commitErrors()) if layer.commitErrors() else "Unknown commit error."
                raise RuntimeError(f"QGIS could not commit the edits: {errors}")

        except Exception as exc:
            if layer.isEditable():
                layer.rollBack()
            # If this was a newly created field, try to remove it after rollback.
            if created and field in layer.fields().names():
                idx = layer.fields().indexOf(field)
                if idx >= 0:
                    try:
                        layer.dataProvider().deleteAttributes([idx])
                        layer.updateFields()
                    except Exception:
                        pass
            QMessageBox.critical(self, "Plot Numbering", str(exc))
            return

        layer.triggerRepaint()
        self._preview = values
        self.statusLabel.setText(f"Completed • {len(values):,} plot number(s) written to '{field}'.")
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())
        self._layer_changed()
        QMessageBox.information(self, "Plot Numbering complete", f"Successfully numbered {len(values):,} plot(s).")
