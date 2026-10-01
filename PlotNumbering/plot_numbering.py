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

from qgis.PyQt.QtGui import QAction
import os
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

from .plot_numbering_dialog import PlotNumberingDialog


class PlotNumberingPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.menu_name = self.tr("&Plot Numbering")
        self.dialog = None

    def tr(self, message):
        return QCoreApplication.translate("PlotNumbering", message)

    def initGui(self):
        self.action = QAction(QIcon(os.path.join(os.path.dirname(__file__), "icon.png")), self.tr("Plot Numbering"), self.iface.mainWindow())
        self.action.setObjectName("plotNumberingAction")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToVectorMenu(self.menu_name, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginVectorMenu(self.menu_name, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def run(self):
        if self.dialog is None:
            self.dialog = PlotNumberingDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
