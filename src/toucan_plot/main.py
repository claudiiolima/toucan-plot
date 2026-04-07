import os
import sys
import multiprocessing
import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt import NavigationToolbar2QT as NavigationToolbar
import qdarktheme

from toucan_plot.utils import styles, csv_load_worker, can_log_load_worker, mf4_load_worker

LEGEND_POSITIONS = [
    'best', 'upper right', 'upper left', 'lower left', 'lower right',
    'center left', 'center right', 'upper center', 'lower center', 'center',
    'outside right', 'outside top',
    'outside upper right', 'outside lower right',
]

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Toucan-Plot')
        self.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), 'assets', 'ico', 'toucan-plot.ico')))
        self.resize(900, 600)

        # central widget and layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # Matplotlib canvas
        self.fig = Figure(figsize=(6, 4), dpi=100, facecolor='white')
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        # canvas will be placed inside a vertical container together with the full NavigationToolbar

        # Menu bar: add an action to create a new subplot from a chosen series
        menubar = self.menuBar()
        if menubar is not None:
            file_menu = menubar.addMenu('File')
            open_action = QtGui.QAction('Open', self)
            open_action.setShortcut('Ctrl+O')
            open_action.triggered.connect(self.open_file)
            self._merge_action = QtGui.QAction('Merge', self)
            self._merge_action.setShortcut('Ctrl+M')
            self._merge_action.setEnabled(False)
            self._merge_action.triggered.connect(self.merge_file)
            exit_action = QtGui.QAction('Exit', self)
            exit_action.triggered.connect(self.close)
            if file_menu is not None:
                file_menu.addAction(open_action)
                file_menu.addAction(self._merge_action)
                file_menu.addSeparator()
                file_menu.addAction(exit_action)

            style_menu = menubar.addMenu('Style')
            style_action = QtGui.QAction('Customize plot style', self)
            style_action.triggered.connect(self.show_plot_style_dialog)
            if style_menu is not None:
                style_menu.addAction(style_action)

                # Theme submenu
                theme_menu = style_menu.addMenu('Theme')
                self._theme_actions = {}
                theme_group = QtGui.QActionGroup(theme_menu)
                for theme_name in ('dark', 'light'):
                    a = QtGui.QAction(theme_name.capitalize(), self)
                    a.setCheckable(True)
                    a.setChecked(theme_name == 'dark')
                    theme_group.addAction(a)
                    theme_menu.addAction(a)
                    self._theme_actions[theme_name] = a
                    def make_theme_handler(t):
                        def handler():
                            self._apply_theme(t)
                        return handler
                    a.triggered.connect(make_theme_handler(theme_name))

        # Icon mappings for toolbar buttons (keyed by theme variant)
        assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
        self._icons_buttons = {
            "Home": { "dark": os.path.join(assets_dir, 'home-dark.svg'),
                      "light": os.path.join(assets_dir, 'home-light.svg') },
            "Pan": { "dark": os.path.join(assets_dir, 'hand-stop-dark.svg'),
                     "light": os.path.join(assets_dir, 'hand-stop-light.svg') },
            "Zoom": { "dark": os.path.join(assets_dir, 'zoom-dark.svg'),
                      "light": os.path.join(assets_dir, 'zoom-light.svg') },
            "Customize": { "dark": os.path.join(assets_dir, 'adjustments-dark.svg'),
                           "light": os.path.join(assets_dir, 'adjustments-light.svg') },
            "Back": { "dark": os.path.join(assets_dir, 'arrow-narrow-left-dark.svg'),
                      "light": os.path.join(assets_dir, 'arrow-narrow-left-light.svg') },
            "Forward": { "dark": os.path.join(assets_dir, 'arrow-narrow-right-dark.svg'),
                         "light": os.path.join(assets_dir, 'arrow-narrow-right-light.svg') },
            "Save": { "dark": os.path.join(assets_dir, 'device-floppy-dark.svg'),
                      "light": os.path.join(assets_dir, 'device-floppy-light.svg') },
        }
        self._extra_btn_icons = {
            'add_subplot': { "dark": os.path.join(assets_dir, 'layout-grid-add-dark.svg'),
                             "light": os.path.join(assets_dir, 'layout-grid-add-light.svg') },
            'fit_y':       { "dark": os.path.join(assets_dir, 'arrow-autofit-height-dark.svg'),
                             "light": os.path.join(assets_dir, 'arrow-autofit-height-light.svg') },
            'measure':     { "dark": os.path.join(assets_dir, 'ruler-measure-dark.svg'),
                             "light": os.path.join(assets_dir, 'ruler-measure-light.svg') },
            'x_axis':      { "dark": os.path.join(assets_dir, 'math-function-dark.svg'),
                             "light": os.path.join(assets_dir, 'math-function-light.svg') },
        }

        # Current theme ("dark" or "light")
        self._current_theme = 'light'

        # Put canvas and the full Matplotlib navigation toolbar in a vertical widget
        unwanted_buttons = ["Subplots"]
        plot_widget = QtWidgets.QWidget()
        self.nav_toolbar = NavigationToolbar(self.canvas, self, coordinates=False)
        # Override edit_parameters so update_plot runs after the Customize dialog closes
        _orig_edit_parameters = self.nav_toolbar.edit_parameters
        def _custom_edit_parameters():
            _orig_edit_parameters()
            self.update_plot()
        self.nav_toolbar.edit_parameters = _custom_edit_parameters
        # Override the Home button to auto-fit all series data
        for action in self.nav_toolbar.actions():
            if action.text() in unwanted_buttons:
                self.nav_toolbar.removeAction(action)
                continue
            if action.text() in self._icons_buttons:
                icon_path = self._icons_buttons[action.text()][self._current_theme]
                if os.path.exists(icon_path):
                    action.setIcon(QtGui.QIcon(icon_path))
            if action.text() == 'Home':
                action.triggered.disconnect()
                action.triggered.connect(self._home_autoscale)

        # Add subplot button next to the navigation toolbar
        self._add_subplot_btn = QtWidgets.QToolButton()
        self._add_subplot_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['add_subplot'][self._current_theme]))
        self._add_subplot_btn.setIconSize(QtCore.QSize(24, 24))
        self._add_subplot_btn.setToolTip('Add subplot')
        self._add_subplot_btn.clicked.connect(self.show_series_selector)

        # Fit Y axis button
        self._fit_y_btn = QtWidgets.QToolButton()
        self._fit_y_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['fit_y'][self._current_theme]))
        self._fit_y_btn.setIconSize(QtCore.QSize(24, 24))
        self._fit_y_btn.setToolTip('Fit Y data to axis (keep X range)')
        self._fit_y_btn.clicked.connect(self._fit_y_autoscale)

        # Measure lines toggle button
        self.measure_btn = QtWidgets.QToolButton()
        self.measure_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['measure'][self._current_theme]))
        self.measure_btn.setIconSize(QtCore.QSize(24, 24))
        self.measure_btn.setToolTip('Toggle measure cursors')
        self.measure_btn.setCheckable(True)
        self.measure_btn.toggled.connect(self._toggle_measure)

        # X-axis selector button
        self._x_axis_btn = QtWidgets.QToolButton()
        self._x_axis_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['x_axis'][self._current_theme]))
        self._x_axis_btn.setIconSize(QtCore.QSize(24, 24))
        self._x_axis_btn.setToolTip('Select X axis series')
        self._x_axis_btn.clicked.connect(self._show_x_axis_dialog)

        self.nav_toolbar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.nav_toolbar.setStyleSheet("QToolBar { background: transparent; border: none; }")

        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.addWidget(self.nav_toolbar)
        toolbar_layout.addWidget(self._add_subplot_btn)
        toolbar_layout.addWidget(self._fit_y_btn)
        toolbar_layout.addWidget(self.measure_btn)
        toolbar_layout.addWidget(self._x_axis_btn)
        toolbar_layout.addStretch(1)

        plot_vlayout = QtWidgets.QVBoxLayout(plot_widget)
        plot_vlayout.setContentsMargins(0, 0, 0, 0)
        plot_vlayout.addLayout(toolbar_layout)
        plot_vlayout.addWidget(self.canvas)
        layout.addWidget(plot_widget, stretch=3)

        # Status bar for mouse coordinates
        self._coord_label = QtWidgets.QLabel('')
        self.statusBar().addWidget(self._coord_label)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)


        # default frequency used for series that depend on f
        self.default_freq = 1.0

        # Default style used when creating/updating subplot configuration
        self.default_plot_style = {
            'legend_show': True,
            'legend_pos': 'best',
            'legend_orient': 'vertical',
            'legend_fontsize': 12,
            'plot_mode': 'step',
            'grid_show': True,
            'marker': '',
        }
        self.available_plot_presets = {
            'Default': styles.set_default_style,
            'Style 1': styles.set_style1_style,
            'Style 2': styles.set_style2_style,
            'IEEE': styles.set_ieee_style,
        }
        self.selected_plot_preset = 'Default'
        self.available_plot_presets[self.selected_plot_preset]()

        # Prepare series definitions (5 series). x is shared.
        self._x = np.linspace(0, 2 * np.pi, 400)
        self._all_columns = {}  # all loaded columns (name -> numpy array)
        self._x_col_name = ''  # current x-axis column name
        self._skip_xlabel_capture = False  # flag to skip xlabel capture during x-axis change
        self._merged_mode = False  # True when multiple files are merged
        # Tracks loaded files: list of {'name': str, 'series_indices': [int, ...]}
        self._loaded_files = []
        # Each series is a callable that accepts x and freq and returns y
        self.series_list = []
        # Keep track of series per subplot: a list of lists. Each sublist contains indices into series_list.
        # Start with no subplots (user requested the app start with none)
        self.subplot_series = []
        # Parallel structure to hold per-curve properties for each subplot.
        # Each entry is a list of dicts matching the series in `subplot_series`.
        self.subplot_series_props = []
        # Per-subplot axes labels: a list of dicts with keys 'xlabel','ylabel_primary','ylabel_secondary'
        self.subplot_axes_labels = []
        # Per-subplot display config: legend and plot mode
        # Each entry is a dict: {'legend_show': bool, 'legend_pos': str, 'legend_orient': str, 'plot_mode': str}
        self.subplot_config = []

        # Measure cursors state
        self._measure_active = False
        self._measure_lines = []  # list of axvline artists per axes
        self._measure_x = [None, None]  # x positions of the two cursors
        self._measure_dragging = None  # index (0 or 1) of cursor being dragged
        self._measure_cids = []  # matplotlib event connection ids
        self._measure_dialog = None
        self._plotted_line_artists = []  # stored line artists per subplot for property capture
        self._plotted_series_snapshot = []  # snapshot of subplot_series at last draw (for structure matching)

        # Connect matplotlib double-clicks on the canvas to allow adding series to a clicked subplot
        # Use mpl_connect to listen for mouse button press events; event.dblclick indicates a double-click.
        self.canvas.mpl_connect('button_press_event', self.on_canvas_click)

        # initial plot
        self.update_plot()
        self._apply_theme(self._current_theme)

    def update_plot(self):
        # Recreate subplots based on self.subplot_series
        f = float(self.default_freq)
        nsubs = len(self.subplot_series)

        # Save current axis limits and labels before clearing
        saved_limits = []
        for i, ax in enumerate(getattr(self, 'current_axes', [])):
            saved_limits.append((ax.get_xlim(), ax.get_ylim()))
            # Capture labels that may have been edited via the navigation toolbar
            if i < len(self.subplot_axes_labels):
                current_xlabel = ax.get_xlabel()
                current_ylabel = ax.get_ylabel()
                # Only save xlabel if it's a user-set custom label (not the auto-generated x column name)
                if current_xlabel and current_xlabel != self._x_col_name and not self._skip_xlabel_capture:
                    self.subplot_axes_labels[i]['xlabel'] = current_xlabel
                if current_ylabel:
                    self.subplot_axes_labels[i]['ylabel_primary'] = current_ylabel
            # Capture series properties (label, color, linewidth, linestyle, marker) from stored line artists
            # Only capture if this subplot's structure hasn't changed since last draw
            if (i < len(self._plotted_line_artists)
                    and i < len(self._plotted_series_snapshot)
                    and i < len(self.subplot_series)
                    and self._plotted_series_snapshot[i] == self.subplot_series[i]):
                line_artists = self._plotted_line_artists[i]
                if i < len(self.subplot_series_props):
                    for j, line in enumerate(line_artists):
                        if j < len(self.subplot_series_props[i]):
                            label = line.get_label()
                            if label and not label.startswith('_'):
                                self.subplot_series_props[i][j]['label'] = label
                            color = line.get_color()
                            if color:
                                self.subplot_series_props[i][j]['color'] = color
                            self.subplot_series_props[i][j]['linewidth'] = line.get_linewidth()
                            self.subplot_series_props[i][j]['linestyle'] = line.get_linestyle()
                            marker = line.get_marker()
                            if marker and marker != 'None':
                                self.subplot_series_props[i][j]['marker'] = marker
                            else:
                                self.subplot_series_props[i][j]['marker'] = ''

        # Clear and create new axes array with shared x
        self.fig.clear()
        self._plotted_line_artists = []
        self._plotted_series_snapshot = [list(s) for s in self.subplot_series]
        if nsubs == 0:
            # no subplots: clear figure and draw blank canvas
            self.current_axes = []
            self.canvas.draw()
            return

        if nsubs == 1:
            axes = [self.fig.add_subplot(111)]
        else:
            axes = self.fig.subplots(nsubs, 1, sharex=True)
            # ensure axes is a list
            if not isinstance(axes, (list, np.ndarray)):
                axes = [axes]
            else:
                axes = list(axes)

        # Keep a reference to current axes so we can map mouse events to subplot indices
        self.current_axes = axes

        # Plot each subplot's series
        for idx, series_indices in enumerate(self.subplot_series):
            ax = axes[idx]
            # retrieve axis labels for this subplot if any
            ax_labels = {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''}
            if idx < len(self.subplot_axes_labels):
                ax_labels.update(self.subplot_axes_labels[idx])
            props_list = []
            if idx < len(self.subplot_series_props):
                props_list = self.subplot_series_props[idx]
            # Get subplot config
            cfg = dict(self.default_plot_style)
            if idx < len(self.subplot_config):
                cfg.update(self.subplot_config[idx])
            plot_fn_name = cfg.get('plot_mode', 'step')
            axis_text_size = cfg.get('legend_fontsize', self.default_plot_style['legend_fontsize'])

            # Plot each series assigned to this subplot
            subplot_line_artists = []
            for j, series_idx in enumerate(series_indices):
                name, func, x_data = self.series_list[series_idx]
                y = func(x_data, f)
                # get curve properties if present
                if j < len(props_list):
                    p = props_list[j]
                    color = p.get('color', '')
                    lw = p.get('linewidth', 1.5)
                    ls = p.get('linestyle', '')
                    marker = p.get('marker', '')
                    label = p.get('label', name)
                else:
                    color = ''
                    lw = 1.5
                    ls = ''
                    marker = ''
                    label = name
                # choose axis
                yaxis = 1
                if j < len(props_list):
                    yaxis = props_list[j].get('yaxis', 1)

                if not marker:
                    marker = cfg.get('marker', '')
                label = label.strip('_')  # remove leading/trailing underscores for better math text parsing
                draw_kwargs = dict(linewidth=lw, label=label)
                if ls:
                    draw_kwargs['linestyle'] = ls
                if marker:
                    draw_kwargs['marker'] = marker
                if color:
                    draw_kwargs['color'] = color
                target_ax = ax
                if yaxis != 1:
                    target_ax = ax.twinx()
                if plot_fn_name == 'step':
                    step_result = target_ax.step(x_data, y, where='post', **draw_kwargs)
                    subplot_line_artists.append(step_result[0])
                else:
                    plot_result = target_ax.plot(x_data, y, **draw_kwargs)
                    subplot_line_artists.append(plot_result[0])
                if yaxis != 1:
                    ax_ylabel_secondary = ax_labels.get('ylabel_secondary')
                    if ax_ylabel_secondary:
                        target_ax.set_ylabel(ax_ylabel_secondary, fontsize=axis_text_size)
                    target_ax.tick_params(axis='both', labelsize=axis_text_size)
            self._plotted_line_artists.append(subplot_line_artists)
            # Configure axis
            ax_xlabel = ax_labels.get('xlabel')
            ax_ylabel = ax_labels.get('ylabel_primary')
            # X label only on the last subplot
            if idx == nsubs - 1:
                # Check if any subplot has a custom xlabel and use it
                custom_xlabel = ''
                for lbl in self.subplot_axes_labels:
                    if lbl.get('xlabel'):
                        custom_xlabel = lbl['xlabel']
                if custom_xlabel:
                    ax.set_xlabel(custom_xlabel, fontsize=axis_text_size)
                elif self._x_col_name:
                    ax.set_xlabel(self._x_col_name, fontsize=axis_text_size)
            if ax_ylabel:
                ax.set_ylabel(ax_ylabel, fontsize=axis_text_size)
            ax.tick_params(axis='both', labelsize=axis_text_size)
            if cfg.get('grid_show', True):
                ax.grid(True, color='0.95')
            # Legend
            if cfg.get('legend_show', True) and len(series_indices) > 0:
                ncol = len(series_indices) if cfg.get('legend_orient') == 'horizontal' else 1
                legend_fs = cfg.get('legend_fontsize', self.default_plot_style['legend_fontsize'])
                legend_pos = cfg.get('legend_pos', 'best')
                outside_map = {
                    'outside right':        ('upper left',   (1.02, 1)),
                    'outside left':         ('upper right',  (-0.02, 1)),
                    'outside top':          ('lower left',   (0, 1.02)),
                    'outside upper right':  ('upper left',   (1.02, 1)),
                    'outside lower right':  ('lower left',   (1.02, 0)),
                }
                if legend_pos in outside_map:
                    loc, bbox = outside_map[legend_pos]
                    ax.legend(loc=loc, bbox_to_anchor=bbox, borderaxespad=0, ncol=ncol, fontsize=legend_fs)
                else:
                    ax.legend(loc=legend_pos, ncol=ncol, fontsize=legend_fs)

            # Restore saved axis limits if available for this subplot
            if idx < len(saved_limits):
                ax.set_xlim(saved_limits[idx][0])
                ax.set_ylim(saved_limits[idx][1])

        self.fig.tight_layout()
        # Redraw measure lines if active
        if self._measure_active:
            self._draw_measure_lines()
            self._update_measure_dialog()
        self.canvas.draw()

    def on_randomize(self):
        # Randomize button removed; keep method no-op in case called elsewhere
        pass

    def _on_mouse_move(self, event):
        """Update status bar with mouse coordinates when hovering over a subplot."""
        if event.inaxes is not None:
            self._coord_label.setText(f'x = {event.xdata:.6g}   y = {event.ydata:.6g}')
        else:
            self._coord_label.setText('')

    def _home_autoscale(self, *args):
        """Reset all subplot axes to fit all plotted data."""
        for ax in getattr(self, 'current_axes', []):
            ax.relim()
            ax.autoscale(enable=True, axis='y', tight=False)
            ax.autoscale(enable=True, axis='x', tight=True)
        self.canvas.draw_idle()

    def _show_x_axis_dialog(self):
        """Open a dialog to select which column to use as the X axis."""
        if not self._all_columns:
            QtWidgets.QMessageBox.information(self, 'X Axis', 'No data loaded. Open a file first.')
            return
        if self._merged_mode:
            QtWidgets.QMessageBox.information(self, 'X Axis', 'X axis selection is not available in merge mode. Each file uses its own X axis.')
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Select X Axis')
        dlg.setMinimumWidth(300)
        layout = QtWidgets.QFormLayout(dlg)

        combo = QtWidgets.QComboBox()
        combo.addItems(list(self._all_columns.keys()))
        combo.setCurrentText(self._x_col_name)
        layout.addRow('X axis column:', combo)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addRow(buttons)

        def on_ok():
            selected = combo.currentText()
            if selected and selected != self._x_col_name:
                self._change_x_axis(selected)
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _change_x_axis(self, col_name):
        """Switch the x-axis to a different loaded column."""
        if not col_name or col_name not in self._all_columns:
            return
        new_x = self._all_columns[col_name]

        # Build a map from old series index -> series name
        old_names = {i: name for i, (name, *_rest) in enumerate(self.series_list)}

        self._x = new_x
        self._x_col_name = col_name

        # Rebuild series_list from all_columns, excluding the new x column
        self.series_list.clear()
        new_indices = []
        for name, data in self._all_columns.items():
            if name == col_name:
                continue
            idx = len(self.series_list)
            self.series_list.append((name, lambda x, f, _d=data: _d, new_x))
            new_indices.append(idx)

        # Update loaded file tracking
        if self._loaded_files:
            self._loaded_files[0]['series_indices'] = new_indices

        # Build a map from series name -> new index
        new_index_by_name = {name: i for i, (name, *_rest) in enumerate(self.series_list)}

        # Remap existing subplot assignments to the new indices
        new_subplot_series = []
        new_subplot_props = []
        new_subplot_labels = []
        new_subplot_config = []
        for sub_idx, old_indices in enumerate(self.subplot_series):
            remapped_indices = []
            remapped_props = []
            props = self.subplot_series_props[sub_idx] if sub_idx < len(self.subplot_series_props) else []
            for j, old_idx in enumerate(old_indices):
                name = old_names.get(old_idx)
                if name and name in new_index_by_name:
                    remapped_indices.append(new_index_by_name[name])
                    if j < len(props):
                        remapped_props.append(props[j])
            if remapped_indices:
                new_subplot_series.append(remapped_indices)
                new_subplot_props.append(remapped_props)
                new_subplot_labels.append(
                    self.subplot_axes_labels[sub_idx] if sub_idx < len(self.subplot_axes_labels)
                    else {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''}
                )
                new_subplot_config.append(
                    self.subplot_config[sub_idx] if sub_idx < len(self.subplot_config)
                    else self._make_default_subplot_config()
                )

        self.subplot_series = new_subplot_series
        self.subplot_series_props = new_subplot_props
        self.subplot_axes_labels = new_subplot_labels
        self.subplot_config = new_subplot_config

        # Reset x labels on all subplots so the new x column name is used
        for lbl in self.subplot_axes_labels:
            lbl['xlabel'] = ''

        self._skip_xlabel_capture = True
        self.update_plot()
        self._skip_xlabel_capture = False

    def _fit_y_autoscale(self, *args):
        """Fit Y data to axis while preserving the current X range."""
        for ax in getattr(self, 'current_axes', []):
            xlim = ax.get_xlim()
            ax.relim()
            ax.autoscale(enable=True, axis='y', tight=False)
            ax.set_xlim(xlim)
        self.canvas.draw_idle()

    def _apply_theme(self, theme):
        """Switch between 'dark' and 'light' themes."""
        self._current_theme = theme
        qdarktheme.setup_theme(theme)

        # Update navigation toolbar icons
        for action in self.nav_toolbar.actions():
            if action.text() in self._icons_buttons:
                icon_path = self._icons_buttons[action.text()][theme]
                if os.path.exists(icon_path):
                    action.setIcon(QtGui.QIcon(icon_path))

        # Update extra toolbar button icons
        self._add_subplot_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['add_subplot'][theme]))
        self._fit_y_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['fit_y'][theme]))
        self.measure_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['measure'][theme]))
        self._x_axis_btn.setIcon(QtGui.QIcon(self._extra_btn_icons['x_axis'][theme]))

        # Update theme menu checkmarks
        for t, a in self._theme_actions.items():
            a.setChecked(t == theme)

    def _make_default_subplot_config(self):
        return dict(self.default_plot_style)

    def show_plot_style_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Customize Plot Style')
        layout = QtWidgets.QFormLayout(dlg)

        preset_combo = QtWidgets.QComboBox()
        preset_combo.addItems(list(self.available_plot_presets.keys()))
        preset_combo.setCurrentText(self.selected_plot_preset)

        plot_mode_combo = QtWidgets.QComboBox()
        plot_mode_combo.addItems(['step', 'plot'])
        plot_mode_combo.setCurrentText(self.default_plot_style.get('plot_mode', 'step'))

        grid_show_check = QtWidgets.QCheckBox('Show grid')
        grid_show_check.setChecked(bool(self.default_plot_style.get('grid_show', True)))

        marker_combo = QtWidgets.QComboBox()
        marker_combo.addItems(['', 'o', 's', '^', 'v', 'x', '+', '*', '.', 'D', '|', '_'])
        marker_combo.setCurrentText(self.default_plot_style.get('marker', ''))

        legend_show_check = QtWidgets.QCheckBox('Show legend by default')
        legend_show_check.setChecked(bool(self.default_plot_style.get('legend_show', True)))

        legend_pos_combo = QtWidgets.QComboBox()
        legend_pos_combo.addItems(LEGEND_POSITIONS)
        legend_pos_combo.setCurrentText(self.default_plot_style.get('legend_pos', 'best'))

        legend_orient_combo = QtWidgets.QComboBox()
        legend_orient_combo.addItems(['vertical', 'horizontal'])
        legend_orient_combo.setCurrentText(self.default_plot_style.get('legend_orient', 'vertical'))

        text_size_spin = QtWidgets.QSpinBox()
        text_size_spin.setRange(6, 24)
        text_size_spin.setValue(int(self.default_plot_style.get('legend_fontsize', 12)))

        apply_existing_check = QtWidgets.QCheckBox('Apply to existing subplots now')
        apply_existing_check.setChecked(True)

        layout.addRow('Preset from styles.py', preset_combo)
        layout.addRow('Plot style', plot_mode_combo)
        layout.addRow('Marker', marker_combo)
        layout.addRow('Text size', text_size_spin)
        layout.addRow('', grid_show_check)
        layout.addRow('', legend_show_check)
        layout.addRow('Legend position', legend_pos_combo)
        layout.addRow('Legend orientation', legend_orient_combo)
        layout.addRow('', apply_existing_check)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel | QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        layout.addRow(buttons)

        def apply_style():
            selected_preset = preset_combo.currentText()
            preset_fn = self.available_plot_presets.get(selected_preset)
            if preset_fn is not None:
                try:
                    preset_fn()
                    self.selected_plot_preset = selected_preset
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, 'Style error', f'Failed to apply preset {selected_preset}:\n{e}')

            if grid_show_check.isChecked() is True:
                mpl.rcParams['axes.grid'] = True
                mpl.rcParams['grid.alpha'] = 1.0
                mpl.rcParams['grid.linewidth'] = 0.8
            mpl.rcParams['lines.markersize'] = mpl.rcParams['lines.linewidth'] * 2.0

            new_defaults = {
                'legend_show': legend_show_check.isChecked(),
                'legend_pos': legend_pos_combo.currentText(),
                'legend_orient': legend_orient_combo.currentText(),
                'legend_fontsize': int(text_size_spin.value()),
                'plot_mode': plot_mode_combo.currentText(),
                'grid_show': grid_show_check.isChecked(),
                'marker': marker_combo.currentText(),
            }
            self.default_plot_style = dict(new_defaults)

            if apply_existing_check.isChecked():
                for i in range(len(self.subplot_config)):
                    self.subplot_config[i] = dict(new_defaults)

            self.update_plot()

        def on_ok():
            apply_style()
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(apply_style)
        dlg.exec()

    def open_files(self, paths):
        """Load a list of file paths. The first data file is opened normally; any additional files are merged."""
        if not paths:
            return
        blf_files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.blf', '.trc', '.asc')]
        dbc_files = [p for p in paths if os.path.splitext(p)[1].lower() == '.dbc']
        csv_files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.csv', '.smv')]
        mf4_files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.mf4', '.mf4z')]

        first_loaded = False

        if blf_files and dbc_files:
            for blf_path in blf_files:
                if not first_loaded:
                    self._load_blf(blf_path, dbc_files)
                    first_loaded = True
                else:
                    self._merged_mode = True
                    self._merge_load_blf(blf_path, dbc_paths=dbc_files, prefix=os.path.basename(blf_path))

        for path in csv_files:
            if not first_loaded:
                self._load_csv(path)
                first_loaded = True
            else:
                self._merged_mode = True
                self._merge_load_csv(path, os.path.basename(path))

        for path in mf4_files:
            if not first_loaded:
                self._load_mf4(path)
                first_loaded = True
            else:
                self._merged_mode = True
                self._merge_load_mf4(path, os.path.basename(path))

        if self._merged_mode and self.series_list:
            file_names = [f['name'] for f in self._loaded_files]
            self.update_plot()
            self.setWindowTitle(f'Toucan-Plot — Merged: {", ".join(file_names)}')

    def open_file(self):
        file_filter = "All supported files (*.csv *.smv *.blf *.trc *.asc *.dbc *.mf4 *.mf4z);;CSV files (*.csv);;SMV files (*.smv);;MF4 files (*.mf4 *.mf4z);;CAN files (*.blf *.trc *.asc *.dbc);;All files (*)"
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, 'Open File', '', file_filter)
        self.open_files(paths)

    def merge_file(self):
        """Open additional files and append their series to the existing plot session."""
        file_filter = "All supported files (*.csv *.smv *.blf *.trc *.asc *.dbc *.mf4 *.mf4z);;CSV files (*.csv);;SMV files (*.smv);;MF4 files (*.mf4 *.mf4z);;CAN files (*.blf *.trc *.asc *.dbc);;All files (*)"
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, 'Merge Files', '', file_filter)
        if not paths:
            return

        self._merged_mode = True

        blf_files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.blf', '.trc', '.asc')]
        dbc_files = [p for p in paths if os.path.splitext(p)[1].lower() == '.dbc']
        csv_files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.csv', '.smv')]
        mf4_files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.mf4', '.mf4z')]

        for path in csv_files:
            basename = os.path.basename(path)
            self._merge_load_csv(path, basename)

        if blf_files and dbc_files:
            for blf_path in blf_files:
                basename = os.path.basename(blf_path)
                self._merge_load_blf(blf_path, dbc_paths=dbc_files, prefix=basename)

        for path in mf4_files:
            basename = os.path.basename(path)
            self._merge_load_mf4(path, basename)

        if self.series_list:
            file_names = [f['name'] for f in self._loaded_files]
            self.update_plot()
            self.setWindowTitle(f'Toucan-Plot — Merged: {", ".join(file_names)}')
            self.show_series_selector()

    def _merge_load_csv(self, path, prefix):
        """Load a CSV/SMV file and append its series (prefixed) to the existing series_list."""
        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(target=csv_load_worker, args=(path, queue))

        progress = QtWidgets.QProgressDialog(f'Loading {os.path.basename(path)}...', None, 0, 100, self)
        progress.setWindowTitle('Loading')
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        result_data = {}

        def poll():
            try:
                while not queue.empty():
                    msg = queue.get_nowait()
                    if msg[0] == 'progress':
                        pct = msg[1]
                        label = msg[2] if len(msg) > 2 else ''
                        if pct >= 0:
                            progress.setValue(pct)
                        if label:
                            progress.setLabelText(label)
                    elif msg[0] == 'result':
                        result_data['data'] = msg[1]
                        progress.setValue(100)
                        progress.close()
                    elif msg[0] == 'error':
                        result_data['error'] = msg[1]
                        progress.close()
            except Exception:
                pass

        timer = QtCore.QTimer(progress)
        timer.timeout.connect(poll)
        timer.start(50)
        proc.start()
        progress.exec()
        timer.stop()
        proc.join(timeout=10)

        if 'error' in result_data:
            QtWidgets.QMessageBox.warning(self, 'Error', result_data['error'])
            return
        if 'data' not in result_data:
            return

        x_col, all_columns = result_data['data']
        x_array = all_columns[x_col]

        # Use the first file's x as the default for measure cursor placement
        if len(self.series_list) == 0:
            self._x = x_array
            self._x_col_name = x_col

        # Append series with file prefix and track file
        file_entry = {'name': prefix, 'series_indices': []}
        for name in all_columns:
            if name == x_col:
                continue
            data = all_columns[name]
            prefixed_name = f'{prefix}: {name}'
            idx = len(self.series_list)
            self.series_list.append((prefixed_name, lambda x, f, _d=data: _d, x_array))
            file_entry['series_indices'].append(idx)
        self._loaded_files.append(file_entry)

    def _merge_load_blf(self, blf_path, dbc_paths, prefix):
        """Load a BLF/TRC/ASC file and append its series (prefixed) to the existing series_list."""
        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(target=can_log_load_worker, args=(blf_path, dbc_paths, queue))

        progress = QtWidgets.QProgressDialog(f'Loading {os.path.basename(blf_path)}...', None, 0, 100, self)
        progress.setWindowTitle('Loading')
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        result_data = {}

        def poll():
            try:
                while not queue.empty():
                    msg = queue.get_nowait()
                    if msg[0] == 'progress':
                        pct = msg[1]
                        label = msg[2] if len(msg) > 2 else ''
                        if pct >= 0:
                            progress.setValue(pct)
                        if label:
                            progress.setLabelText(label)
                    elif msg[0] == 'result':
                        result_data['data'] = msg[1]
                        progress.setValue(100)
                        progress.close()
                    elif msg[0] == 'error':
                        result_data['error'] = msg[1]
                        progress.close()
            except Exception:
                pass

        timer = QtCore.QTimer(progress)
        timer.timeout.connect(poll)
        timer.start(50)
        proc.start()
        progress.exec()
        timer.stop()
        proc.join(timeout=10)

        if 'error' in result_data:
            QtWidgets.QMessageBox.warning(self, 'Error', result_data['error'])
            return
        if 'data' not in result_data:
            return

        x_col, all_columns = result_data['data']
        x_array = all_columns[x_col]

        # Use the first file's x as the default for measure cursor placement
        if len(self.series_list) == 0:
            self._x = x_array
            self._x_col_name = x_col

        # Append series with file prefix and track file
        file_entry = {'name': prefix, 'series_indices': []}
        for name in all_columns:
            if name == x_col:
                continue
            data = all_columns[name]
            prefixed_name = f'{prefix}: {name}'
            idx = len(self.series_list)
            self.series_list.append((prefixed_name, lambda x, f, _d=data: _d, x_array))
            file_entry['series_indices'].append(idx)
        self._loaded_files.append(file_entry)

    def _load_csv(self, path):
        """Load a CSV/SMV file using a worker process with live progress."""
        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(target=csv_load_worker, args=(path, queue))

        progress = QtWidgets.QProgressDialog(f'Loading {os.path.basename(path)}...', None, 0, 100, self)
        progress.setWindowTitle('Loading')
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        result_data = {}

        def poll():
            try:
                while not queue.empty():
                    msg = queue.get_nowait()
                    if msg[0] == 'progress':
                        pct = msg[1]
                        label = msg[2] if len(msg) > 2 else ''
                        if pct >= 0:
                            progress.setValue(pct)
                        if label:
                            progress.setLabelText(label)
                    elif msg[0] == 'result':
                        result_data['data'] = msg[1]
                        progress.setValue(100)
                        progress.close()
                    elif msg[0] == 'error':
                        result_data['error'] = msg[1]
                        progress.close()
            except Exception:
                pass

        timer = QtCore.QTimer(progress)
        timer.timeout.connect(poll)
        timer.start(50)
        proc.start()
        progress.exec()
        timer.stop()
        proc.join(timeout=10)

        if 'error' in result_data:
            QtWidgets.QMessageBox.warning(self, 'Error', result_data['error'])
            return
        if 'data' not in result_data:
            return

        x_col, all_columns = result_data['data']
        x_array = all_columns[x_col]

        self._x = x_array
        self._all_columns = all_columns
        self._x_col_name = x_col
        self._merged_mode = False

        # Clear existing series and subplots
        self.series_list.clear()
        self.subplot_series.clear()
        self.subplot_series_props.clear()
        self.subplot_axes_labels.clear()
        self.subplot_config.clear()
        self._loaded_files.clear()

        # Build series_list from all_columns (lambdas can't cross process boundary)
        basename = os.path.basename(path)
        file_entry = {'name': basename, 'series_indices': []}
        for name in all_columns:
            if name == x_col:
                continue
            data = all_columns[name]
            idx = len(self.series_list)
            self.series_list.append((name, lambda x, f, _d=data: _d, x_array))
            file_entry['series_indices'].append(idx)
        self._loaded_files.append(file_entry)
        self._merge_action.setEnabled(True)

        self.update_plot()
        self.setWindowTitle(f'Toucan-Plot — {basename}')
        self.show_series_selector()

    def _load_blf(self, blf_path, dbc_paths):
        """Load a BLF file using a worker process with live progress."""
        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(target=can_log_load_worker, args=(blf_path, dbc_paths, queue))

        progress = QtWidgets.QProgressDialog(f'Loading {os.path.basename(blf_path)}...', None, 0, 100, self)
        progress.setWindowTitle('Loading')
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        result_data = {}

        def poll():
            try:
                while not queue.empty():
                    msg = queue.get_nowait()
                    if msg[0] == 'progress':
                        pct = msg[1]
                        label = msg[2] if len(msg) > 2 else ''
                        if pct >= 0:
                            progress.setValue(pct)
                        if label:
                            progress.setLabelText(label)
                    elif msg[0] == 'result':
                        result_data['data'] = msg[1]
                        progress.setValue(100)
                        progress.close()
                    elif msg[0] == 'error':
                        result_data['error'] = msg[1]
                        progress.close()
            except Exception:
                pass

        timer = QtCore.QTimer(progress)
        timer.timeout.connect(poll)
        timer.start(50)
        proc.start()
        progress.exec()
        timer.stop()
        proc.join(timeout=10)

        if 'error' in result_data:
            QtWidgets.QMessageBox.warning(self, 'Error', result_data['error'])
            return
        if 'data' not in result_data:
            return

        x_col, all_columns = result_data['data']
        x_array = all_columns[x_col]

        self._x = x_array
        self._all_columns = all_columns
        self._x_col_name = x_col
        self._merged_mode = False

        # Clear existing series and subplots
        self.series_list.clear()
        self.subplot_series.clear()
        self.subplot_series_props.clear()
        self.subplot_axes_labels.clear()
        self.subplot_config.clear()
        self._loaded_files.clear()

        # Build series_list from all_columns (lambdas can't cross process boundary)
        basename = os.path.basename(blf_path)
        file_entry = {'name': basename, 'series_indices': []}
        for name in all_columns:
            if name == x_col:
                continue
            data = all_columns[name]
            idx = len(self.series_list)
            self.series_list.append((name, lambda x, f, _d=data: _d, x_array))
            file_entry['series_indices'].append(idx)
        self._loaded_files.append(file_entry)
        self._merge_action.setEnabled(True)

        self.update_plot()
        self.setWindowTitle(f'Toucan-Plot — {basename}')
        self.show_series_selector()

    def _load_mf4(self, path):
        """Load an MF4 file using a worker process with live progress."""
        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(target=mf4_load_worker, args=(path, queue))

        progress = QtWidgets.QProgressDialog(f'Loading {os.path.basename(path)}...', None, 0, 100, self)
        progress.setWindowTitle('Loading')
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        result_data = {}

        def poll():
            try:
                while not queue.empty():
                    msg = queue.get_nowait()
                    if msg[0] == 'progress':
                        pct = msg[1]
                        label = msg[2] if len(msg) > 2 else ''
                        if pct >= 0:
                            progress.setValue(pct)
                        if label:
                            progress.setLabelText(label)
                    elif msg[0] == 'result':
                        result_data['data'] = msg[1]
                        progress.setValue(100)
                        progress.close()
                    elif msg[0] == 'error':
                        result_data['error'] = msg[1]
                        progress.close()
            except Exception:
                pass

        timer = QtCore.QTimer(progress)
        timer.timeout.connect(poll)
        timer.start(50)
        proc.start()
        progress.exec()
        timer.stop()
        proc.join(timeout=10)

        if 'error' in result_data:
            QtWidgets.QMessageBox.warning(self, 'Error', result_data['error'])
            return
        if 'data' not in result_data:
            return

        x_col, all_columns = result_data['data']
        x_array = all_columns[x_col]

        self._x = x_array
        self._all_columns = all_columns
        self._x_col_name = x_col
        self._merged_mode = False

        # Clear existing series and subplots
        self.series_list.clear()
        self.subplot_series.clear()
        self.subplot_series_props.clear()
        self.subplot_axes_labels.clear()
        self.subplot_config.clear()
        self._loaded_files.clear()

        # Build series_list from all_columns
        basename = os.path.basename(path)
        file_entry = {'name': basename, 'series_indices': []}
        for name in all_columns:
            if name == x_col:
                continue
            data = all_columns[name]
            idx = len(self.series_list)
            self.series_list.append((name, lambda x, f, _d=data: _d, x_array))
            file_entry['series_indices'].append(idx)
        self._loaded_files.append(file_entry)
        self._merge_action.setEnabled(True)

        self.update_plot()
        self.setWindowTitle(f'Toucan-Plot — {basename}')
        self.show_series_selector()

    def _merge_load_mf4(self, path, prefix):
        """Load an MF4 file and append its series (prefixed) to the existing series_list."""
        queue = multiprocessing.Queue()
        proc = multiprocessing.Process(target=mf4_load_worker, args=(path, queue))

        progress = QtWidgets.QProgressDialog(f'Loading {os.path.basename(path)}...', None, 0, 100, self)
        progress.setWindowTitle('Loading')
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        result_data = {}

        def poll():
            try:
                while not queue.empty():
                    msg = queue.get_nowait()
                    if msg[0] == 'progress':
                        pct = msg[1]
                        label = msg[2] if len(msg) > 2 else ''
                        if pct >= 0:
                            progress.setValue(pct)
                        if label:
                            progress.setLabelText(label)
                    elif msg[0] == 'result':
                        result_data['data'] = msg[1]
                        progress.setValue(100)
                        progress.close()
                    elif msg[0] == 'error':
                        result_data['error'] = msg[1]
                        progress.close()
            except Exception:
                pass

        timer = QtCore.QTimer(progress)
        timer.timeout.connect(poll)
        timer.start(50)
        proc.start()
        progress.exec()
        timer.stop()
        proc.join(timeout=10)

        if 'error' in result_data:
            QtWidgets.QMessageBox.warning(self, 'Error', result_data['error'])
            return
        if 'data' not in result_data:
            return

        x_col, all_columns = result_data['data']
        x_array = all_columns[x_col]

        if len(self.series_list) == 0:
            self._x = x_array
            self._x_col_name = x_col

        file_entry = {'name': prefix, 'series_indices': []}
        for name in all_columns:
            if name == x_col:
                continue
            data = all_columns[name]
            prefixed_name = f'{prefix}: {name}'
            idx = len(self.series_list)
            self.series_list.append((prefixed_name, lambda x, f, _d=data: _d, x_array))
            file_entry['series_indices'].append(idx)
        self._loaded_files.append(file_entry)

    # ---- Measure cursors ----

    def _toggle_measure(self, checked: bool):
        if checked:
            self._measure_active = True
            # Place two initial cursors at 1/3 and 2/3 of the visible x range
            if len(self.current_axes) > 0:
                xmin, xmax = self.current_axes[0].get_xlim()
                span = xmax - xmin
                self._measure_x = [xmin + span * 0.33, xmin + span * 0.66]
            else:
                self._measure_x = [0.0, 1.0]
            self._draw_measure_lines()
            self._show_measure_dialog()
            # Connect mouse events
            cid1 = self.canvas.mpl_connect('button_press_event', self._measure_press)
            cid2 = self.canvas.mpl_connect('motion_notify_event', self._measure_move)
            cid3 = self.canvas.mpl_connect('button_release_event', self._measure_release)
            self._measure_cids = [cid1, cid2, cid3]
        else:
            self._measure_active = False
            # Disconnect events
            for cid in self._measure_cids:
                self.canvas.mpl_disconnect(cid)
            self._measure_cids.clear()
            self._remove_measure_lines()
            if self._measure_dialog is not None:
                self._measure_dialog.close()
                self._measure_dialog = None
            self.canvas.draw_idle()

    def _draw_measure_lines(self):
        self._remove_measure_lines()
        self._measure_lines = []
        for ax in self.current_axes:
            lines_for_ax = []
            for i, xpos in enumerate(self._measure_x):
                color = 'red' if i == 0 else 'blue'
                line = ax.axvline(x=xpos, color=color, linestyle='--', linewidth=1.0, picker=5)
                lines_for_ax.append(line)
            self._measure_lines.append(lines_for_ax)
        self.canvas.draw_idle()

    def _remove_measure_lines(self):
        for lines_for_ax in self._measure_lines:
            for line in lines_for_ax:
                try:
                    line.remove()
                except Exception:
                    pass
        self._measure_lines.clear()

    def _measure_press(self, event):
        if event.inaxes is None or event.button != 1:
            return
        # Don't drag measure cursors when zoom or pan is active
        toolbar_mode = getattr(self.nav_toolbar, 'mode', '')
        if toolbar_mode:
            return
        # Find closest cursor
        best_idx = None
        best_dist = float('inf')
        for i, xpos in enumerate(self._measure_x):
            dist = abs(event.xdata - xpos)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        # Only start drag if close enough (within 2% of x range)
        if len(self.current_axes) > 0:
            xmin, xmax = self.current_axes[0].get_xlim()
            threshold = (xmax - xmin) * 0.02
        else:
            threshold = best_dist + 1
        if best_dist <= threshold:
            self._measure_dragging = best_idx

    def _measure_move(self, event):
        if self._measure_dragging is None or event.xdata is None:
            return
        self._measure_x[self._measure_dragging] = event.xdata
        self._draw_measure_lines()
        self._update_measure_dialog()

    def _measure_release(self, event):
        if self._measure_dragging is not None:
            self._measure_dragging = None

    def _show_measure_dialog(self):
        if self._measure_dialog is not None:
            self._measure_dialog.close()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Measure Values')
        dlg.setMinimumWidth(420)
        dlg.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        layout = QtWidgets.QVBoxLayout(dlg)
        self._measure_table = QtWidgets.QTableWidget()
        layout.addWidget(self._measure_table)
        dlg.setLayout(layout)
        self._measure_dialog = dlg
        dlg.show()
        self._update_measure_dialog()

    def _update_measure_dialog(self):
        if self._measure_dialog is None or not self._measure_dialog.isVisible():
            return
        x1, x2 = self._measure_x
        f = float(self.default_freq)
        table = self._measure_table
        # Columns: Series | Cursor 1 (x1) | Cursor 2 (x2) | Delta
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([
            'Series',
            f'Cursor 1 (x={x1:.4f})',
            f'Cursor 2 (x={x2:.4f})',
            'Delta',
        ])
        # Collect all plotted series across subplots
        rows = []
        for subplot_indices in self.subplot_series:
            for series_idx in subplot_indices:
                name, func, x_data = self.series_list[series_idx]
                y_data = func(x_data, f)
                y1 = float(np.interp(x1, x_data, y_data))
                y2 = float(np.interp(x2, x_data, y_data))
                rows.append((name, y1, y2, y2 - y1))
        table.setRowCount(len(rows))
        for r, (name, y1, y2, delta) in enumerate(rows):
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(f'{y1:.6f}'))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(f'{y2:.6f}'))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(f'{delta:.6f}'))
        table.resizeColumnsToContents()

    def show_series_selector(self):
        """Open the two-pane series editor to create a new subplot.

        The dialog shows Available series (left) and Plotted series (right).
        When OK is pressed the plotted list is appended as a new subplot.
        """
        def _on_accept(plotted_indices, props, axes_labels):
            if plotted_indices:
                self.subplot_series.append(list(plotted_indices))
                # store props (make a shallow copy)
                self.subplot_series_props.append([dict(p) for p in props])
                # store axes labels
                self.subplot_axes_labels.append(dict(axes_labels) if axes_labels is not None else {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''})
                self.subplot_config.append(self._make_default_subplot_config())
                self.update_plot()

        # For a new subplot, initial plotted list is empty
        self._open_series_editor(initial_plotted=[], on_accept=_on_accept, initial_props=[], initial_axes={})

    def _open_series_editor(self, initial_plotted, on_accept, initial_props=None, initial_axes=None):
        """Open a modal editor to select series for a subplot.

        When multiple files are loaded, the available series panel shows one tab per file.
        The plotted series list on the right is always a single unified list.

        initial_plotted: list of series indices that should appear on the right (plotted)
        on_accept: callable(plotted_indices_list, props_list, axes_labels) called when OK pressed
        initial_props: optional list of dicts describing properties for each plotted series (aligned)
        """
        if initial_props is None:
            initial_props = []
        if initial_axes is None:
            initial_axes = {}

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Edit series for subplot')
        dlg.setModal(True)
        dlg.resize(700, 420)

        main_layout = QtWidgets.QVBoxLayout(dlg)

        # --- Series: two-list editor ---
        series_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(series_layout)

        # Build per-file tab structure for available series (left side)
        avail_layout = QtWidgets.QVBoxLayout()
        series_layout.addLayout(avail_layout)
        avail_label = QtWidgets.QLabel('Available series')
        avail_layout.addWidget(avail_label)

        # Map from series index -> which file index it belongs to (for returning items)
        series_to_file = {}
        for file_idx, fentry in enumerate(self._loaded_files):
            for sidx in fentry['series_indices']:
                series_to_file[sidx] = file_idx

        plotted_set = set(initial_plotted)

        # Build file tabs (or single list if only one file)
        use_tabs = len(self._loaded_files) > 1
        avail_tabs = None
        avail_lists = []  # parallel to _loaded_files
        avail_filters = []

        if use_tabs:
            avail_tabs = QtWidgets.QTabWidget()
            avail_layout.addWidget(avail_tabs)
            for file_idx, fentry in enumerate(self._loaded_files):
                tab_widget = QtWidgets.QWidget()
                tab_layout = QtWidgets.QVBoxLayout(tab_widget)
                tab_layout.setContentsMargins(2, 2, 2, 2)
                filt = QtWidgets.QLineEdit()
                filt.setPlaceholderText('Filter...')
                filt.setClearButtonEnabled(True)
                tab_layout.addWidget(filt)
                lst = QtWidgets.QListWidget()
                lst.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
                tab_layout.addWidget(lst)
                avail_tabs.addTab(tab_widget, fentry['name'])
                avail_lists.append(lst)
                avail_filters.append(filt)

                # Populate this tab's list with the file's series (excluding already plotted)
                for sidx in fentry['series_indices']:
                    name = self.series_list[sidx][0]
                    item = QtWidgets.QListWidgetItem(name)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, sidx)
                    if sidx not in plotted_set:
                        lst.addItem(item)

                # Connect filter
                def make_filter_handler(list_widget):
                    def handler(text):
                        text_lower = text.lower()
                        for i in range(list_widget.count()):
                            it = list_widget.item(i)
                            it.setHidden(text_lower not in it.text().lower())
                    return handler
                filt.textChanged.connect(make_filter_handler(lst))

                # Connect double-click to add
                def make_dblclick_handler(list_widget):
                    def handler(item):
                        item.setSelected(True)
                        move_selected_from(list_widget)
                    return handler
                lst.itemDoubleClicked.connect(make_dblclick_handler(lst))
        else:
            # Single file or no files — flat list as before
            avail_filter = QtWidgets.QLineEdit()
            avail_filter.setPlaceholderText('Filter...')
            avail_filter.setClearButtonEnabled(True)
            avail_layout.addWidget(avail_filter)
            avail_list = QtWidgets.QListWidget()
            avail_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
            avail_layout.addWidget(avail_list)
            avail_lists.append(avail_list)
            avail_filters.append(avail_filter)

            for idx, (name, *_rest) in enumerate(self.series_list):
                item = QtWidgets.QListWidgetItem(name)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, idx)
                if idx not in plotted_set:
                    avail_list.addItem(item)

            def on_filter_changed(text):
                text_lower = text.lower()
                for i in range(avail_list.count()):
                    it = avail_list.item(i)
                    it.setHidden(text_lower not in it.text().lower())
            avail_filter.textChanged.connect(on_filter_changed)

        # --- Expression evaluator ---
        # Track last selected series name across all available lists
        last_selected_name = {'value': ''}

        def on_avail_selection_changed():
            """Track the last selected item from any available list."""
            for lst in avail_lists:
                selected = lst.selectedItems()
                if selected:
                    last_selected_name['value'] = selected[-1].text()

        for lst in avail_lists:
            lst.itemSelectionChanged.connect(on_avail_selection_changed)

        copy_to_expr_btn = QtWidgets.QPushButton('Copy selected to expression')
        copy_to_expr_btn.setToolTip('Insert the last selected series name into the expression field')
        avail_layout.addWidget(copy_to_expr_btn)

        expr_layout = QtWidgets.QHBoxLayout()
        avail_layout.addLayout(expr_layout)
        expr_field = QtWidgets.QLineEdit()
        expr_field.setPlaceholderText('e.g. sin("series_A") + "series_B" * 2')
        expr_field.setToolTip(
            'Math expression using series names in "quotes".\n'
            'Supported: +, -, *, /, **, abs(), sin(), cos(), tan(),\n'
            'sqrt(), exp(), log(), pi, e'
        )
        expr_layout.addWidget(expr_field)

        add_expr_btn = QtWidgets.QPushButton('Add')
        add_expr_btn.setToolTip('Evaluate expression and add as a new plotted series')
        expr_layout.addWidget(add_expr_btn)

        def copy_selected_to_expr():
            name = last_selected_name['value']
            if name:
                current = expr_field.text()
                cursor_pos = expr_field.cursorPosition()
                # If the name already contains quotes, it's an expression — insert as-is
                if '"' in name:
                    token = name
                else:
                    token = '"' + name + '"'
                new_text = current[:cursor_pos] + token + current[cursor_pos:]
                expr_field.setText(new_text)
                expr_field.setCursorPosition(cursor_pos + len(token))
                expr_field.setFocus()

        copy_to_expr_btn.clicked.connect(copy_selected_to_expr)

        def add_expression():
            expr_text = expr_field.text().strip()
            if not expr_text:
                return

            # Build a mapping of series name -> (data_array, x_array)
            series_map = {}
            for idx_s, (sname, sfunc, sx) in enumerate(self.series_list):
                y_data = sfunc(sx, float(self.default_freq))
                series_map[sname] = (y_data, sx)

            # Replace "series_name" tokens with placeholder variable names
            import re
            token_pattern = re.compile(r'"([^"]+)"')
            tokens_found = token_pattern.findall(expr_text)

            if not tokens_found:
                QtWidgets.QMessageBox.warning(dlg, 'Expression Error',
                    'No series references found.\nUse "series_name" to reference a series.')
                return

            # Validate all referenced series exist
            for tok in tokens_found:
                if tok not in series_map:
                    QtWidgets.QMessageBox.warning(dlg, 'Expression Error',
                        f'Series not found: {tok}')
                    return

            # Determine x_data: use the x from the first referenced series
            first_ref = tokens_found[0]
            expr_x = series_map[first_ref][1]

            # For series with different x-axes, interpolate onto the first one
            var_arrays = {}
            for i, tok in enumerate(tokens_found):
                y_data, tok_x = series_map[tok]
                var_name = f'_s{i}'
                if tok_x is expr_x or (len(tok_x) == len(expr_x) and np.allclose(tok_x, expr_x)):
                    var_arrays[var_name] = y_data
                else:
                    var_arrays[var_name] = np.interp(expr_x, tok_x, y_data)

            # Build the evaluable expression by replacing tokens with variable names
            eval_expr = expr_text
            for i, tok in enumerate(tokens_found):
                eval_expr = eval_expr.replace('"' + tok + '"', f'_s{i}')

            # Safe math namespace
            safe_ns = {
                '__builtins__': {},
                'sin': np.sin, 'cos': np.cos, 'tan': np.tan,
                'abs': np.abs, 'sqrt': np.sqrt, 'exp': np.exp,
                'log': np.log, 'log10': np.log10,
                'pi': np.pi, 'e': np.e,
                'arcsin': np.arcsin, 'arccos': np.arccos, 'arctan': np.arctan,
                'clip': np.clip, 'sign': np.sign,
            }
            safe_ns.update(var_arrays)

            try:
                result = eval(eval_expr, safe_ns)  # noqa: S307
                result = np.asarray(result, dtype=float)
                if result.shape != expr_x.shape:
                    result = np.broadcast_to(result, expr_x.shape).copy()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(dlg, 'Expression Error',
                    f'Failed to evaluate expression:\n{exc}')
                return

            # Create a new computed series and add to series_list
            expr_label = expr_text
            new_idx = len(self.series_list)
            self.series_list.append((expr_label, lambda x, f, _d=result: _d, expr_x))

            # Track in loaded files (add to a virtual "Expressions" file entry)
            expr_file = None
            for fe in self._loaded_files:
                if fe['name'] == '(Expressions)':
                    expr_file = fe
                    break
            if expr_file is None:
                expr_file = {'name': '(Expressions)', 'series_indices': []}
                self._loaded_files.append(expr_file)
            expr_file['series_indices'].append(new_idx)
            series_to_file[new_idx] = self._loaded_files.index(expr_file)

            # Also add to the tabs if using tabs (add a new tab if needed)
            if use_tabs and avail_tabs is not None:
                expr_tab_idx = None
                for ti in range(len(avail_lists)):
                    if ti < len(self._loaded_files) and self._loaded_files[ti]['name'] == '(Expressions)':
                        expr_tab_idx = ti
                        break
                if expr_tab_idx is None or expr_tab_idx >= len(avail_lists):
                    # Create a new tab for expressions
                    tab_widget = QtWidgets.QWidget()
                    tab_lay = QtWidgets.QVBoxLayout(tab_widget)
                    tab_lay.setContentsMargins(2, 2, 2, 2)
                    filt = QtWidgets.QLineEdit()
                    filt.setPlaceholderText('Filter...')
                    filt.setClearButtonEnabled(True)
                    tab_lay.addWidget(filt)
                    lst = QtWidgets.QListWidget()
                    lst.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
                    tab_lay.addWidget(lst)
                    avail_tabs.addTab(tab_widget, '(Expressions)')
                    avail_lists.append(lst)
                    avail_filters.append(filt)
                    filt.textChanged.connect(make_filter_handler(lst))
                    lst.itemDoubleClicked.connect(make_dblclick_handler(lst))
                    lst.itemSelectionChanged.connect(on_avail_selection_changed)
                    expr_tab_idx = len(avail_lists) - 1

            # Add directly to plotted list
            item = QtWidgets.QListWidgetItem(expr_label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, new_idx)
            plotted_list.addItem(item)

            expr_field.clear()

        add_expr_btn.clicked.connect(add_expression)

        # Buttons between lists
        btns_layout = QtWidgets.QVBoxLayout()
        series_layout.addLayout(btns_layout)
        btns_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        add_btn = QtWidgets.QPushButton('>>')
        remove_btn = QtWidgets.QPushButton('<<')
        add_all_btn = QtWidgets.QPushButton('All >>')
        remove_all_btn = QtWidgets.QPushButton('<< All')
        btns_layout.addWidget(add_btn)
        btns_layout.addWidget(remove_btn)
        btns_layout.addSpacing(10)
        btns_layout.addWidget(add_all_btn)
        btns_layout.addWidget(remove_all_btn)

        # Plotted list (right)
        plotted_layout = QtWidgets.QVBoxLayout()
        series_layout.addLayout(plotted_layout)
        plotted_label = QtWidgets.QLabel('Plotted series')
        plotted_layout.addWidget(plotted_label)
        plotted_list = QtWidgets.QListWidget()
        plotted_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        plotted_layout.addWidget(plotted_list)

        # Populate plotted list with initial_plotted items
        for sidx in initial_plotted:
            name = self.series_list[sidx][0]
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, sidx)
            plotted_list.addItem(item)

        # --- Move helpers ---
        def get_active_avail_list():
            """Return the currently visible available list."""
            if use_tabs and avail_tabs is not None:
                idx = avail_tabs.currentIndex()
                if 0 <= idx < len(avail_lists):
                    return avail_lists[idx]
            return avail_lists[0] if avail_lists else None

        def move_selected_from(src: QtWidgets.QListWidget):
            """Move selected items from an available list to the plotted list."""
            items = src.selectedItems()
            for it in items:
                row = src.row(it)
                src.takeItem(row)
                plotted_list.addItem(it)

        def _avail_list_has_index(lst, sidx):
            """Check if a QListWidget already contains an item with the given series index."""
            for i in range(lst.count()):
                it = lst.item(i)
                if it is not None and int(it.data(QtCore.Qt.ItemDataRole.UserRole)) == sidx:
                    return True
            return False

        def move_selected_to_avail():
            """Move selected items from plotted list back to their original file tab."""
            items = plotted_list.selectedItems()
            for it in items:
                row = plotted_list.row(it)
                plotted_list.takeItem(row)
                sidx = int(it.data(QtCore.Qt.ItemDataRole.UserRole))
                file_idx = series_to_file.get(sidx, 0)
                target = avail_lists[file_idx] if file_idx < len(avail_lists) else (avail_lists[0] if avail_lists else None)
                if target is not None and not _avail_list_has_index(target, sidx):
                    target.addItem(it)

        def move_all_to_plotted():
            """Move all items from the active available list to plotted."""
            src = get_active_avail_list()
            if src is None:
                return
            while src.count() > 0:
                it = src.takeItem(0)
                plotted_list.addItem(it)

        def move_all_to_avail():
            """Move all items from plotted list back to their original file tabs."""
            while plotted_list.count() > 0:
                it = plotted_list.takeItem(0)
                sidx = int(it.data(QtCore.Qt.ItemDataRole.UserRole))
                file_idx = series_to_file.get(sidx, 0)
                target = avail_lists[file_idx] if file_idx < len(avail_lists) else (avail_lists[0] if avail_lists else None)
                if target is not None and not _avail_list_has_index(target, sidx):
                    target.addItem(it)

        add_btn.clicked.connect(lambda: move_selected_from(get_active_avail_list()) if get_active_avail_list() else None)
        remove_btn.clicked.connect(move_selected_to_avail)
        add_all_btn.clicked.connect(move_all_to_plotted)
        remove_all_btn.clicked.connect(move_all_to_avail)

        if not use_tabs:
            # Single-list double-click handlers
            avail_lists[0].itemDoubleClicked.connect(lambda item: (item.setSelected(True), move_selected_from(avail_lists[0])))

        def on_plotted_double_click(item):
            item.setSelected(True)
            move_selected_to_avail()

        plotted_list.itemDoubleClicked.connect(on_plotted_double_click)

        # Dialog buttons
        dlg_buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        main_layout.addWidget(dlg_buttons)

        def on_ok():
            # collect plotted indices in order
            plotted_indices = []
            for i in range(plotted_list.count()):
                it = plotted_list.item(i)
                idx = it.data(QtCore.Qt.ItemDataRole.UserRole)
                plotted_indices.append(int(idx))
            # Preserve existing props where available, create defaults for new series
            existing_props_map = {}
            for j, sidx in enumerate(initial_plotted):
                if j < len(initial_props):
                    existing_props_map[sidx] = initial_props[j]
            props = []
            for sidx in plotted_indices:
                if sidx in existing_props_map:
                    props.append(dict(existing_props_map[sidx]))
                else:
                    name = self.series_list[sidx][0]
                    props.append({'label': name, 'color': '', 'linewidth': 1.5, 'linestyle': '', 'marker': '', 'yaxis': 1})
            axes_labels = dict(initial_axes) if initial_axes else {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''}
            on_accept(plotted_indices, props, axes_labels)
            dlg.accept()

        def on_cancel():
            dlg.reject()

        dlg_buttons.accepted.connect(on_ok)
        dlg_buttons.rejected.connect(on_cancel)

        dlg.exec()

    def on_canvas_click(self, event):
        """Handle mouse clicks on the Matplotlib canvas. On double-click inside an axes, open series dialog to add a line to that subplot."""
        # event.dblclick is True for double clicks
        if event.inaxes is None:
            return

        # Find which axes was clicked
        try:
            ax_index = self.current_axes.index(event.inaxes)
        except Exception:
            return

        # Double-click: edit the subplot's series
        if getattr(event, 'dblclick', False):
            def _on_accept(plotted_indices, props, axes_labels):
                # Replace the subplot's series, properties and axes labels with the returned values
                if plotted_indices is not None:
                    self.subplot_series[ax_index] = list(plotted_indices)
                    # ensure props list stored
                    if ax_index < len(self.subplot_series_props):
                        self.subplot_series_props[ax_index] = [dict(p) for p in props]
                    else:
                        # extend props list accordingly
                        while len(self.subplot_series_props) < ax_index:
                            self.subplot_series_props.append([])
                        self.subplot_series_props.insert(ax_index, [dict(p) for p in props])
                    # store axes labels
                    if ax_index < len(self.subplot_axes_labels):
                        self.subplot_axes_labels[ax_index] = dict(axes_labels) if axes_labels is not None else {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''}
                    else:
                        while len(self.subplot_axes_labels) < ax_index:
                            self.subplot_axes_labels.append({'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''})
                        self.subplot_axes_labels.insert(ax_index, dict(axes_labels) if axes_labels is not None else {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''})
                    self.update_plot()

            # provide existing props if available
            existing_props = []
            if ax_index < len(self.subplot_series_props):
                existing_props = self.subplot_series_props[ax_index]

            existing_axes = {}
            if ax_index < len(self.subplot_axes_labels):
                existing_axes = self.subplot_axes_labels[ax_index]
            self._open_series_editor(initial_plotted=self.subplot_series[ax_index], on_accept=_on_accept, initial_props=existing_props, initial_axes=existing_axes)
            return

        # Right-click: show context menu for subplot actions
        # Matplotlib's event.guiEvent (for QTAgg) contains the underlying Qt event
        # But only if zoom/pan is not active
        if getattr(event, 'button', None) == 3:
            # Check if zoom or pan mode is active (compatible across Matplotlib versions)
            toolbar_mode = getattr(self.nav_toolbar, 'mode', '')
            actions = getattr(self.nav_toolbar, '_actions', {})
            pan_action = actions.get('pan') if isinstance(actions, dict) else None
            zoom_action = actions.get('zoom') if isinstance(actions, dict) else None
            pan_active = bool(pan_action.isChecked()) if pan_action is not None else False
            zoom_active = bool(zoom_action.isChecked()) if zoom_action is not None else False
            if toolbar_mode or pan_active or zoom_active:
                # Zoom or pan is active, don't show context menu
                return
            
            # Build a QMenu with actions: Delete subplot, Add above, Add below
            menu = QtWidgets.QMenu(self)

            delete_action = QtGui.QAction('Delete subplot', self)
            add_above_action = QtGui.QAction('Add subplot above', self)
            add_below_action = QtGui.QAction('Add subplot below', self)

            menu.addAction(add_above_action)
            menu.addAction(add_below_action)
            menu.addSeparator()

            # --- Legend submenu ---
            # ensure config exists for this subplot
            while len(self.subplot_config) <= ax_index:
                self.subplot_config.append(self._make_default_subplot_config())
            cur_cfg = self.subplot_config[ax_index]

            legend_menu = menu.addMenu('Legend')

            show_legend_action = QtGui.QAction('Show legend', self)
            show_legend_action.setCheckable(True)
            show_legend_action.setChecked(cur_cfg.get('legend_show', True))
            def toggle_legend(checked):
                self.subplot_config[ax_index]['legend_show'] = checked
                self.default_plot_style['legend_show'] = checked
                self.update_plot()
            show_legend_action.toggled.connect(toggle_legend)
            legend_menu.addAction(show_legend_action)

            # Position submenu
            pos_menu = legend_menu.addMenu('Position')
            current_pos = cur_cfg.get('legend_pos', 'best')
            pos_group = QtGui.QActionGroup(pos_menu)
            for p in LEGEND_POSITIONS:
                a = QtGui.QAction(p, self)
                a.setCheckable(True)
                a.setChecked(p == current_pos)
                pos_group.addAction(a)
                pos_menu.addAction(a)
                def make_pos_handler(pos_val):
                    def handler():
                        self.subplot_config[ax_index]['legend_pos'] = pos_val
                        self.default_plot_style['legend_pos'] = pos_val
                        self.update_plot()
                    return handler
                a.triggered.connect(make_pos_handler(p))

            # Orientation submenu
            orient_menu = legend_menu.addMenu('Orientation')
            current_orient = cur_cfg.get('legend_orient', 'vertical')
            orient_group = QtGui.QActionGroup(orient_menu)
            for ori in ('vertical', 'horizontal'):
                a = QtGui.QAction(ori.capitalize(), self)
                a.setCheckable(True)
                a.setChecked(ori == current_orient)
                orient_group.addAction(a)
                orient_menu.addAction(a)
                def make_orient_handler(ori_val):
                    def handler():
                        self.subplot_config[ax_index]['legend_orient'] = ori_val
                        self.default_plot_style['legend_orient'] = ori_val
                        self.update_plot()
                    return handler
                a.triggered.connect(make_orient_handler(ori))

            # Text size submenu
            size_menu = legend_menu.addMenu('Text size')
            current_fontsize = cur_cfg.get('legend_fontsize', 12)
            size_group = QtGui.QActionGroup(size_menu)
            for sz in (6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20):
                a = QtGui.QAction(str(sz), self)
                a.setCheckable(True)
                a.setChecked(sz == current_fontsize)
                size_group.addAction(a)
                size_menu.addAction(a)
                def make_size_handler(sz_val):
                    def handler():
                        self.subplot_config[ax_index]['legend_fontsize'] = sz_val
                        self.default_plot_style['legend_fontsize'] = sz_val
                        self.update_plot()
                    return handler
                a.triggered.connect(make_size_handler(sz))

            # --- Plot style submenu ---
            plot_style_line_menu = menu.addMenu('Plot style')
            current_mode = cur_cfg.get('plot_mode', 'step')
            mode_group = QtGui.QActionGroup(plot_style_line_menu)
            for mode in ('plot', 'step'):
                a = QtGui.QAction(mode.capitalize(), self)
                a.setCheckable(True)
                a.setChecked(mode == current_mode)
                mode_group.addAction(a)
                plot_style_line_menu.addAction(a)
                def make_mode_handler(mode_val):
                    def handler():
                        self.subplot_config[ax_index]['plot_mode'] = mode_val
                        self.default_plot_style['plot_mode'] = mode_val
                        self.update_plot()
                    return handler
                a.triggered.connect(make_mode_handler(mode))

            menu.addSeparator()
            menu.addAction(delete_action)

            # Helper to get global position robustly across PyQt/Matplotlib versions
            pos = None
            ge = getattr(event, 'guiEvent', None)
            if ge is not None:
                # Prefer globalPosition (QPointF) if available, else globalPos(), else map from local position
                try:
                    gp = ge.globalPosition()
                    # QPointF -> QPoint
                    pos = QtCore.QPoint(int(gp.x()), int(gp.y()))
                except Exception:
                    try:
                        gp = ge.globalPos()
                        pos = gp
                    except Exception:
                        try:
                            # fallback to local position on the widget
                            lp = ge.position()
                            pos = self.canvas.mapToGlobal(QtCore.QPoint(int(lp.x()), int(lp.y())))
                        except Exception:
                            pos = None
            if pos is None:
                # Final fallback: map matplotlib event display coords to global
                try:
                    # event.x, event.y are display coords (floats); map directly
                    pos = self.canvas.mapToGlobal(QtCore.QPoint(int(event.x), int(event.y)))
                except Exception:
                    pos = None

            # Action handlers
            def do_delete():
                # remove the subplot at ax_index
                if 0 <= ax_index < len(self.subplot_series):
                    self.subplot_series.pop(ax_index)
                    # also remove properties if present
                    if ax_index < len(self.subplot_series_props):
                        self.subplot_series_props.pop(ax_index)
                    if ax_index < len(self.subplot_axes_labels):
                        self.subplot_axes_labels.pop(ax_index)
                    if ax_index < len(self.subplot_config):
                        self.subplot_config.pop(ax_index)
                    self.update_plot()

            def do_add(insert_pos):
                # Open series editor to choose initial plotted series for new subplot
                def _on_accept(plotted_indices, props, axes_labels):
                    if plotted_indices is None:
                        return
                    # Insert the new subplot at insert_pos
                    self.subplot_series.insert(insert_pos, list(plotted_indices))
                    # insert props
                    self.subplot_series_props.insert(insert_pos, [dict(p) for p in props])
                    # insert axes labels
                    self.subplot_axes_labels.insert(insert_pos, dict(axes_labels) if axes_labels is not None else {'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''})
                    self.subplot_config.insert(insert_pos, self._make_default_subplot_config())
                    self.update_plot()

                # Call editor
                self._open_series_editor(initial_plotted=[], on_accept=_on_accept, initial_props=[], initial_axes={})

            delete_action.triggered.connect(do_delete)
            add_above_action.triggered.connect(lambda: do_add(ax_index))
            add_below_action.triggered.connect(lambda: do_add(ax_index + 1))

            # Show the menu at the computed position
            if pos is not None:
                menu.exec(pos)
            else:
                menu.exec(self.mapToGlobal(self.rect().center()))


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog='toucan-plot',
        description='Toucan-Plot — Interactive plotting tool for CSV, SMV, and CAN log (BLF/TRC/ASC) files.',
        epilog='BLF, TRC, and ASC files require at least one DBC file for signal decoding.\n'
               'Example: toucan-plot log.blf signals.dbc',
    )
    parser.add_argument(
        'files', nargs='*', metavar='FILE',
        help='Data files to open on startup.\nCSV and SMV files are loaded directly.\n'
             'BLF, TRC, and ASC files must be provided together with one or more DBC files.',
    )
    args = parser.parse_args()

    # Set AppUserModelID so Windows taskbar shows the correct icon
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('toucan-plot')
    except Exception:
        pass
    qdarktheme.enable_hi_dpi()
    app = QtWidgets.QApplication(sys.argv)
    qdarktheme.setup_theme('dark')
    win = MainWindow()
    win.show()
    if args.files:
        win.open_files(args.files)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
