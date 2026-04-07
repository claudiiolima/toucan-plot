# Toucan-Plot

An interactive PyQt6 + Matplotlib plotting tool for CSV, SMV, and CAN bus log files.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

### Supported File Formats

| Format | Description |
|--------|-------------|
| `.csv` / `.smv` | Comma or semicolon delimited data (auto-detected) |
| `.mf4` / `.mf4z` | ASAM MDF v4 measurement data (via asammdf) |
| `.blf` | CAN bus binary log |
| `.trc` | CAN bus trace log |
| `.asc` | CAN bus ASCII log |
| `.dbc` | CAN database for signal decoding (required with BLF/TRC/ASC) |

- Auto-detects `Time` / `timestamp` columns as the default X axis
- CAN signals are forward-fill interpolated and named as `Message.Signal`

### Plot Interaction

- **Shared X axis** across all subplots with linked panning and zooming
- **Secondary Y axis** support per series
- **Double-click** a subplot to edit its series, or **right-click** for a context menu
- **Measure cursors** — two draggable vertical cursors with a live delta table
- **Expression evaluator** — create computed series from math expressions (e.g. `sin("series_A") + "series_B" * 2`)
- **Multi-file merge** — overlay series from different files, each in its own tab
- **X axis switching** — reassign the X column without losing subplot configuration
- **Per-series properties** (label, color, linewidth, linestyle, marker) persisted across all redraws
- Live mouse coordinates in the status bar

### Toolbar

| Button | Action |
|--------|--------|
| Home | Auto-fit all axes |
| Back / Forward | Navigate view history |
| Pan | Pan mode |
| Zoom | Zoom rectangle mode |
| Customize | Matplotlib per-curve property editor |
| Save | Export figure to file |
| Add subplot | Open the series selector |
| Fit Y | Auto-fit Y axis keeping current X range |
| Measure | Toggle measure cursors |
| X axis | Select X axis column |

### Menus

- **File → Open** (`Ctrl+O`) — open one or more files (multi-select)
- **File → Merge** (`Ctrl+M`) — append files to the current session
- **Style → Customize plot style** — preset, line mode, marker, text size, grid, legend
- **Style → Theme** — Dark / Light (icons swap automatically)

### Right-Click Context Menu

- Add subplot above / below
- Delete subplot
- Legend: show/hide, position (14 options), orientation, text size
- Line style: plot / step

### Style Presets

Four built-in presets: **Default**, **Style 1**, **IEEE**, **Other**.

## Installation

### From source (recommended)

```shell
pip install .
```

### With uv

```shell
uv pip install .
```

## Usage

```shell
# Open a CSV file
toucan-plot data.csv

# Open an MF4 measurement file
toucan-plot recording.mf4

# Open a CAN log with DBC decoding
toucan-plot recording.blf signals.dbc

# Open multiple files (merge mode)
toucan-plot file1.csv file2.csv

# Launch without files
toucan-plot
```

## Requirements

- Python ≥ 3.11
- PyQt6
- Matplotlib
- NumPy
- pyqtdarktheme
- SciencePlots
- python-can (for CAN log files)
- cantools (for DBC decoding)
- asammdf (for MF4 files)

## License

MIT
