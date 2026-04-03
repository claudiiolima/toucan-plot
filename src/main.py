import sys
import random
import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
import qdarktheme


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Matplotlib in PyQt6 (Light theme)')
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

        # light theme: set a simple stylesheet with white background
        # self.setStyleSheet('QWidget { background-color: white; color: #111; }')

        # Menu bar: add an action to create a new subplot from a chosen series
        menubar = self.menuBar()
        plot_menu = menubar.addMenu('Plot')
        add_subplot_action = QtGui.QAction('Add subplot', self)
        add_subplot_action.triggered.connect(self.show_series_selector)
        plot_menu.addAction(add_subplot_action)

        # Put canvas and the full Matplotlib navigation toolbar in a vertical widget
        plot_widget = QtWidgets.QWidget()
        self.nav_toolbar = NavigationToolbar(self.canvas, self)
        plot_vlayout = QtWidgets.QVBoxLayout(plot_widget)
        plot_vlayout.setContentsMargins(0, 0, 0, 0)
        plot_vlayout.addWidget(self.nav_toolbar)
        plot_vlayout.addWidget(self.canvas)
        layout.addWidget(plot_widget, stretch=3)


        # default frequency used for series that depend on f
        self.default_freq = 1.0

        # Prepare series definitions (5 series). x is shared.
        self.x = np.linspace(0, 2 * np.pi, 400)
        # Each series is a callable that accepts x and freq and returns y
        self.series_list = [
            ("sin(f*x)", lambda x, f: np.sin(f * x)),
            ("cos(x)", lambda x, f: np.cos(x)),
            ("sin(2*x)", lambda x, f: np.sin(2 * x)),
            ("sin(3*x)", lambda x, f: np.sin(3 * x)),
            ("sin(x + pi/4)", lambda x, f: np.sin(x + np.pi / 4)),
        ]

        # Keep track of series per subplot: a list of lists. Each sublist contains indices into series_list.
        # Start with no subplots (user requested the app start with none)
        self.subplot_series = []
        # Parallel structure to hold per-curve properties for each subplot.
        # Each entry is a list of dicts matching the series in `subplot_series`.
        self.subplot_series_props = []
        # Per-subplot axes labels: a list of dicts with keys 'xlabel','ylabel_primary','ylabel_secondary'
        self.subplot_axes_labels = []

        # Connect matplotlib double-clicks on the canvas to allow adding series to a clicked subplot
        # Use mpl_connect to listen for mouse button press events; event.dblclick indicates a double-click.
        self.canvas.mpl_connect('button_press_event', self.on_canvas_click)

        # initial plot
        self.update_plot()

    def update_plot(self):
        # Recreate subplots based on self.subplot_series
        f = float(self.default_freq)
        nsubs = len(self.subplot_series)
        # Clear and create new axes array with shared x
        self.fig.clear()
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

        # Colors to cycle through for multiple lines in a subplot
        colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple', 'tab:brown']

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
            # Plot each series assigned to this subplot
            for j, series_idx in enumerate(series_indices):
                name, func = self.series_list[series_idx]
                y = func(self.x, f)
                # get curve properties if present
                if j < len(props_list):
                    p = props_list[j]
                    color = p.get('color', colors[j % len(colors)])
                    lw = p.get('linewidth', 1.5)
                    marker = p.get('marker', '')
                    label = p.get('label', name)
                else:
                    color = colors[j % len(colors)]
                    lw = 1.5
                    marker = ''
                    label = name
                # choose axis
                yaxis = 1
                if j < len(props_list):
                    yaxis = props_list[j].get('yaxis', 1)

                if yaxis == 1:
                    ax.plot(self.x, y, color=color, linewidth=lw, marker=marker, label=label)
                else:
                    # plot on twin axis
                    ax_t = ax.twinx()
                    ax_t.plot(self.x, y, color=color, linewidth=lw, marker=marker, label=label)
                    # if a secondary ylabel was provided for this subplot, set it
                    if ax_labels.get('ylabel_secondary'):
                        ax_t.set_ylabel(ax_labels.get('ylabel_secondary'))
            # Configure axis
            if idx == 0:
                ax.set_title(f'Sine wave — frequency {f:.2f} Hz')
            else:
                # If multiple series, join names for title
                names = ', '.join(self.series_list[s][0] for s in series_indices)
                ax.set_title(names)
            # apply y label (primary) or default
            if ax_labels.get('ylabel_primary'):
                ax.set_ylabel(ax_labels.get('ylabel_primary'))
            else:
                ax.set_ylabel('amplitude')
            # apply xlabel if any
            if ax_labels.get('xlabel'):
                ax.set_xlabel(ax_labels.get('xlabel'))
            ax.grid(True, color='0.95')
            if len(series_indices) > 1:
                # add legend on primary axis; twin axes may need their own legends but keep simple
                ax.legend()

        self.fig.tight_layout()
        self.canvas.draw()

    def on_randomize(self):
        # Randomize button removed; keep method no-op in case called elsewhere
        pass

    def _toggle_zoom(self, checked: bool):
        """Toggle Matplotlib zoom tool via the NavigationToolbar."""
        # ensure pan is off when zoom is enabled
        try:
            if checked and getattr(self, 'pan_action', None) and self.pan_action.isChecked():
                self.pan_action.setChecked(False)
            # NavigationToolbar.zoom() toggles the zoom mode
            self.nav_toolbar.zoom()
        except Exception:
            # ignore if toolbar not available
            return

    def _toggle_pan(self, checked: bool):
        """Toggle Matplotlib pan tool via the NavigationToolbar."""
        try:
            if checked and getattr(self, 'zoom_action', None) and self.zoom_action.isChecked():
                self.zoom_action.setChecked(False)
            # NavigationToolbar.pan() toggles the pan mode
            self.nav_toolbar.pan()
        except Exception:
            return

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
                self.update_plot()

        # For a new subplot, initial plotted list is empty
        self._open_series_editor(initial_plotted=[], on_accept=_on_accept, initial_props=[], initial_axes={})

    def _open_series_editor(self, initial_plotted, on_accept, initial_props=None, initial_axes=None):
        """Open a modal editor with three tabs: Series, Curves, and Axes.

        initial_plotted: list of series indices that should appear on the right (plotted)
        on_accept: callable(plotted_indices_list, props_list, axes_labels) called when OK pressed
        initial_props: optional list of dicts describing properties for each plotted series (aligned)
        """
        if initial_props is None:
            initial_props = []
        # allow passing initial axis labels via kwargs in future; for backwards compat keep separate
        initial_axes = None

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Edit series for subplot')
        dlg.setModal(True)
        dlg.resize(700, 380)

        main_layout = QtWidgets.QVBoxLayout(dlg)

        tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(tabs)

        # --- Series tab: two-list editor ---
        series_tab = QtWidgets.QWidget()
        series_layout = QtWidgets.QHBoxLayout(series_tab)

        # Available list (left)
        avail_layout = QtWidgets.QVBoxLayout()
        series_layout.addLayout(avail_layout)
        avail_label = QtWidgets.QLabel('Available series')
        avail_layout.addWidget(avail_label)
        avail_list = QtWidgets.QListWidget()
        avail_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        avail_layout.addWidget(avail_list)

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

        tabs.addTab(series_tab, 'Series')

        # Populate lists: available = all except those in initial_plotted (preserve order)
        plotted_set = set(initial_plotted)
        for idx, (name, _) in enumerate(self.series_list):
            item = QtWidgets.QListWidgetItem(name)
            # store series index on the item
            item.setData(QtCore.Qt.ItemDataRole.UserRole, idx)
            if idx in plotted_set:
                plotted_list.addItem(item)
            else:
                avail_list.addItem(item)

        # Maintain a props_list aligned to plotted_list order
        props_list = [dict(p) for p in initial_props]

        # Helper to create default properties for a series index
        def make_default_props(series_idx, pos_index=None):
            name = self.series_list[series_idx][0]
            # simple default color cycle
            default_colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple', 'tab:brown']
            color = default_colors[(pos_index or 0) % len(default_colors)]
            return {'label': name, 'color': color, 'linewidth': 1.5, 'marker': '', 'yaxis': 1}

        # Move helpers must update props_list when moving to/from plotted_list
        def move_selected(src: QtWidgets.QListWidget, dst: QtWidgets.QListWidget):
            # moving from avail -> plotted: append default props
            if src is avail_list and dst is plotted_list:
                items = src.selectedItems()
                for it in items:
                    row = src.row(it)
                    src.takeItem(row)
                    dst.addItem(it)
                    sidx = it.data(QtCore.Qt.ItemDataRole.UserRole)
                    props_list.append(make_default_props(int(sidx), pos_index=len(props_list)))
            elif src is plotted_list and dst is avail_list:
                # remove from plotted and remove corresponding props
                items = src.selectedItems()
                # remove from highest index first to keep indices correct
                rows = sorted([src.row(it) for it in items], reverse=True)
                for row in rows:
                    it = src.takeItem(row)
                    dst.addItem(it)
                    if 0 <= row < len(props_list):
                        props_list.pop(row)
            else:
                # generic fallback
                items = src.selectedItems()
                for it in items:
                    row = src.row(it)
                    src.takeItem(row)
                    dst.addItem(it)
            refresh_curves_list()

        def move_all(src: QtWidgets.QListWidget, dst: QtWidgets.QListWidget):
            if src is avail_list and dst is plotted_list:
                # move all, creating default props
                while src.count() > 0:
                    it = src.takeItem(0)
                    dst.addItem(it)
                    sidx = it.data(QtCore.Qt.ItemDataRole.UserRole)
                    props_list.append(make_default_props(int(sidx), pos_index=len(props_list)))
            elif src is plotted_list and dst is avail_list:
                # move all back, clear props
                while src.count() > 0:
                    it = src.takeItem(0)
                    dst.addItem(it)
                props_list.clear()
            else:
                while src.count() > 0:
                    it = src.takeItem(0)
                    dst.addItem(it)
            refresh_curves_list()

        add_btn.clicked.connect(lambda: move_selected(avail_list, plotted_list))
        remove_btn.clicked.connect(lambda: move_selected(plotted_list, avail_list))
        add_all_btn.clicked.connect(lambda: move_all(avail_list, plotted_list))
        remove_all_btn.clicked.connect(lambda: move_all(plotted_list, avail_list))

        # --- Curves tab: per-curve properties editor ---
        curves_tab = QtWidgets.QWidget()
        curves_layout = QtWidgets.QHBoxLayout(curves_tab)

        # Left: list of plotted curves (same order as plotted_list)
        curves_list = QtWidgets.QListWidget()
        curves_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        curves_layout.addWidget(curves_list, stretch=1)

        # Right: properties editor
        prop_layout = QtWidgets.QFormLayout()
        prop_widget = QtWidgets.QWidget()
        prop_widget.setLayout(prop_layout)
        curves_layout.addWidget(prop_widget, stretch=2)

        label_edit = QtWidgets.QLineEdit()
        color_btn = QtWidgets.QPushButton('Choose color')
        color_preview = QtWidgets.QLabel()
        color_preview.setFixedSize(40, 20)
        lw_spin = QtWidgets.QDoubleSpinBox()
        lw_spin.setRange(0.1, 10.0)
        lw_spin.setSingleStep(0.1)
        marker_combo = QtWidgets.QComboBox()
        marker_combo.addItems(['', 'o', 's', '^', 'x', '+', '*', '.'])
        yaxis_combo = QtWidgets.QComboBox()
        yaxis_combo.addItems(['Primary', 'Secondary'])

        prop_layout.addRow('Label', label_edit)
        color_h = QtWidgets.QHBoxLayout()
        color_h.addWidget(color_btn)
        color_h.addWidget(color_preview)
        prop_layout.addRow('Color', color_h)
        prop_layout.addRow('Line width', lw_spin)
        prop_layout.addRow('Marker', marker_combo)
        prop_layout.addRow('Y axis', yaxis_combo)

        tabs.addTab(curves_tab, 'Curves')

        # --- Axes tab: per-subplot axis labels ---
        axes_tab = QtWidgets.QWidget()
        axes_layout = QtWidgets.QFormLayout(axes_tab)
        xlabel_edit = QtWidgets.QLineEdit()
        ylabel_primary_edit = QtWidgets.QLineEdit()
        ylabel_secondary_edit = QtWidgets.QLineEdit()
        axes_layout.addRow('X label', xlabel_edit)
        axes_layout.addRow('Y label (primary)', ylabel_primary_edit)
        axes_layout.addRow('Y label (secondary)', ylabel_secondary_edit)
        tabs.addTab(axes_tab, 'Axes')

        # populate axes fields from initial_axes if provided by caller
        if initial_axes is not None and isinstance(initial_axes, dict):
            xlabel_edit.setText(initial_axes.get('xlabel', ''))
            ylabel_primary_edit.setText(initial_axes.get('ylabel_primary', ''))
            ylabel_secondary_edit.setText(initial_axes.get('ylabel_secondary', ''))

        # Helper to refresh curves_list to match plotted_list
        def refresh_curves_list():
            curves_list.clear()
            for i in range(plotted_list.count()):
                it = plotted_list.item(i)
                name = it.text()
                li = QtWidgets.QListWidgetItem(name)
                li.setData(QtCore.Qt.ItemDataRole.UserRole, it.data(QtCore.Qt.ItemDataRole.UserRole))
                curves_list.addItem(li)

        refresh_curves_list()

        # Helpers to load/save props into the widgets
        def load_props_for_index(i):
            if i is None or i < 0 or i >= len(props_list):
                label_edit.setText('')
                color_preview.setStyleSheet('')
                lw_spin.setValue(1.5)
                marker_combo.setCurrentIndex(0)
                yaxis_combo.setCurrentIndex(0)
                return
            p = props_list[i]
            label_edit.setText(p.get('label', ''))
            col = p.get('color', '')
            if col:
                color_preview.setStyleSheet(f'background:{col};')
            else:
                color_preview.setStyleSheet('')
            lw_spin.setValue(float(p.get('linewidth', 1.5)))
            marker = p.get('marker', '')
            idx = marker_combo.findText(marker)
            marker_combo.setCurrentIndex(idx if idx >= 0 else 0)
            yaxis_combo.setCurrentIndex(0 if p.get('yaxis', 1) == 1 else 1)

        def save_props_for_index(i):
            if i is None or i < 0 or i >= len(props_list):
                return
            p = props_list[i]
            p['label'] = label_edit.text()
            p['color'] = color_preview.styleSheet().split(':', 1)[1].rstrip(';') if ':' in color_preview.styleSheet() else p.get('color', '')
            p['linewidth'] = float(lw_spin.value())
            p['marker'] = marker_combo.currentText()
            p['yaxis'] = 1 if yaxis_combo.currentIndex() == 0 else 2

        # when user selects an item in curves_list, load its props
        def on_curves_selection_changed():
            i = curves_list.currentRow()
            load_props_for_index(i)

        curves_list.currentRowChanged.connect(on_curves_selection_changed)

        # color chooser
        def choose_color():
            col = QtWidgets.QColorDialog.getColor(parent=dlg)
            if col.isValid():
                css = f'background: {col.name()};'
                color_preview.setStyleSheet(css)
                # immediately save to current selection
                i = curves_list.currentRow()
                if 0 <= i < len(props_list):
                    props_list[i]['color'] = col.name()

        color_btn.clicked.connect(choose_color)

        # Save edits when widgets change
        def on_prop_changed():
            i = curves_list.currentRow()
            save_props_for_index(i)
            # also update the plotted_list display text to reflect label change
            if 0 <= i < plotted_list.count():
                it = plotted_list.item(i)
                it.setText(props_list[i].get('label', it.text()))
                refresh_curves_list()

        label_edit.editingFinished.connect(on_prop_changed)
        lw_spin.valueChanged.connect(lambda v: on_prop_changed())
        marker_combo.currentIndexChanged.connect(lambda v: on_prop_changed())
        yaxis_combo.currentIndexChanged.connect(lambda v: on_prop_changed())

        # when plotted_list selection changes, mirror to curves_list selection
        def on_plotted_selection_changed():
            r = plotted_list.currentRow()
            curves_list.setCurrentRow(r)
            # load props for this row
            load_props_for_index(r)

        plotted_list.currentRowChanged.connect(on_plotted_selection_changed)

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
            # ensure props_list length matches plotted_indices
            # if props_list shorter, extend with defaults
            while len(props_list) < len(plotted_indices):
                sidx = plotted_indices[len(props_list)]
                props_list.append(make_default_props(int(sidx), pos_index=len(props_list)))
            # collect axes labels from fields
            axes_labels = {
                'xlabel': xlabel_edit.text().strip(),
                'ylabel_primary': ylabel_primary_edit.text().strip(),
                'ylabel_secondary': ylabel_secondary_edit.text().strip(),
            }
            on_accept(plotted_indices, props_list, axes_labels)
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
        if getattr(event, 'button', None) == 3:
            # Build a QMenu with actions: Delete subplot, Add above, Add below
            menu = QtWidgets.QMenu(self)

            delete_action = QtGui.QAction('Delete subplot', self)
            add_above_action = QtGui.QAction('Add subplot above', self)
            add_below_action = QtGui.QAction('Add subplot below', self)

            menu.addAction(add_above_action)
            menu.addAction(add_below_action)
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
                    if len(self.subplot_series) == 0:
                        # ensure at least one subplot remains
                        self.subplot_series = [[0]]
                        self.subplot_series_props = [[{'label': self.series_list[0][0], 'color': 'tab:blue', 'linewidth': 1.5, 'marker': '', 'yaxis': 1}]]
                        self.subplot_axes_labels = [{'xlabel': '', 'ylabel_primary': '', 'ylabel_secondary': ''}]
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
    qdarktheme.enable_hi_dpi()
    app = QtWidgets.QApplication(sys.argv)
    #qdarktheme.setup_theme("light")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
