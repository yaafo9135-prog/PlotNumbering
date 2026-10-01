# Plot Numbering

Plot Numbering is a QGIS plugin for assigning clear, sequential numbers to polygon plots in cadastral, subdivision, surveying, and land-administration workflows.

## Highlights

- Directional numbering using north/south and east/west ordering.
- Grid / row-column numbering.
- Clockwise ordering around the layer extent.
- Interactive start-point and direction ordering.
- Automatic Block/Grid ordering for layouts containing multiple plot blocks.
- Short-side-first numbering within detected blocks.
- Continuous numbering from one nearby block to the next.
- Preview before writing numbers to the layer.
- Optional prefix and suffix support.
- Resizable, scrollable interface.
- QGIS native polygon-layer and field selection.
- Designed for QGIS 3.22+ and QGIS 4.x.

## Requirements

- QGIS 3.22 or newer, including QGIS 4.x.
- A polygon vector layer containing the plots to be numbered.
- No separate Python package installation is required by the plugin.

## Installation

### From a ZIP file

1. Open QGIS.
2. Go to **Plugins → Manage and Install Plugins…**.
3. Select **Install from ZIP**.
4. Select the Plot Numbering ZIP package.
5. Confirm the installation.
6. Open Plot Numbering from the **Vector** menu or the plugin toolbar.

The ZIP package contains one top-level plugin directory, as required for normal QGIS plugin installation.

## Basic workflow

1. Select the polygon layer containing the plots.
2. Select the field that will receive the plot numbers.
3. Choose a numbering method.
4. Set the starting number.
5. Add an optional prefix or suffix if required.
6. Use **Preview** to inspect the proposed numbering.
7. Use **Apply** to write the numbers to the layer.

Preview is intended to let you inspect the ordering before committing the changes.

## Automatic Block/Grid

Automatic Block/Grid is intended for cadastral or subdivision plans made up of spatially separated plot blocks. The algorithm identifies spatially connected groups of plots, determines a suitable local ordering for each block, and then continues the sequence between nearby blocks.

The intended short-side-first pattern is:

```text
Tall block:

1  2
3  4
5  6
7  8

Wide block:

9  11  13  15
10 12  14  16

Next block:

17 19 21 23
18 20 22 24
```

The exact result depends on the geometry, spacing, orientation, and distribution of the input plots.

## Output field handling

The plugin checks the selected output field before editing. It avoids writing NULL or empty plot values and prepares a compatible output field when the selected configuration requires one.

If your existing field is intended to contain numeric plot numbers, use a numeric field. If prefixes or suffixes are required, use a text-compatible field.

## Interface

The plugin uses a compact, resizable dialog with:

- native QGIS polygon-layer selection;
- native QGIS field selection;
- numbering-method selection;
- starting-number controls;
- optional prefix/suffix controls;
- Preview and Apply actions;
- a preview area for reviewing the proposed sequence.

The plugin window uses the normal operating-system title bar for window controls.

## Compatibility

The release metadata declares compatibility with QGIS 3.22 through QGIS 4.x. The implementation includes Qt 5 / Qt 6 compatibility handling for the QGIS 3 and QGIS 4 environments.

## Version history

### 2026-09-30 — Version 1.0

Initial public release of Plot Numbering.

## Author and support

**Hamadu Hudu Yaafo**  
Email: yaafo9135@gmail.com

Bug reports, compatibility reports, and feature suggestions are welcome by email. When reporting a problem, include your QGIS version, operating system, numbering method, and a small reproducible example where possible.

## License

Plot Numbering is released under the **GNU General Public License, version 3 or any later version (GPL-3.0-or-later)**. See the `LICENSE` file included with this package for the complete license text.

The included plugin icon is part of the Plot Numbering project package. QGIS and its own components remain subject to their respective licenses.


## Source repository

Source code, issue tracking, and project documentation are maintained at:
https://github.com/yaafo9135-Prog/PlotNumbering

## Development layout

The QGIS plugin source is contained in the `PlotNumbering/` directory. The repository root contains project-level documentation and licensing.

## Reporting issues

Please report bugs and feature requests through GitHub Issues:
https://github.com/yaafo9135-Prog/PlotNumbering/issues
