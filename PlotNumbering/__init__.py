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

def classFactory(iface):
    from .plot_numbering import PlotNumberingPlugin
    return PlotNumberingPlugin(iface)
