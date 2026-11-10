import os
import unittest
from types import SimpleNamespace

import matplotlib as mpl
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from toucan_plot.main import MainWindow


class PlotStyleControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.rc_context = mpl.rc_context()
        self.rc_context.__enter__()
        self.addCleanup(self.rc_context.__exit__, None, None, None)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        x = np.array([0.0, 0.5, 1.0])
        self.window.series_list = [
            ("Speed", lambda x, f: x * 10, x),
            ("Torque", lambda x, f: x * 2, x),
        ]
        self.window._loaded_files = [{"name": "recording.blf", "series_indices": [0, 1]}]
        self.window.subplot_series = [[0, 1]]
        self.window.subplot_series_props = [[
            {"marker": "o", "yaxis": 1},
            {"marker": "^", "yaxis": 2},
        ]]
        self.window.subplot_config = [self.window._make_default_subplot_config()]
        self.window.update_plot()

    def apply_style(self, marker="", grid=True, existing=True, preset="Default"):
        errors = []

        def interact():
            dialog = self.app.activeModalWidget()
            try:
                layout = dialog.layout()
                combos = {}
                for combo in dialog.findChildren(QtWidgets.QComboBox):
                    combos[layout.labelForField(combo).text()] = combo
                combos["Marker"].setCurrentText(marker)
                combos["Preset from styles.py"].setCurrentText(preset)
                for check in dialog.findChildren(QtWidgets.QCheckBox):
                    if check.text() == "Show grid":
                        check.setChecked(grid)
                    elif check.text() == "Apply to existing subplots now":
                        check.setChecked(existing)
                dialog.findChild(QtWidgets.QDialogButtonBox).button(
                    QtWidgets.QDialogButtonBox.StandardButton.Apply,
                ).click()
            except Exception as exc:
                errors.append(exc)
            finally:
                dialog.reject()

        QtCore.QTimer.singleShot(0, interact)
        self.window.show_plot_style_dialog()
        if errors:
            raise errors[0]

    def markers(self):
        return [line.get_marker() for line in self.window._plotted_line_artists[0]]

    def assert_grid(self, visible):
        primary = self.window.current_axes[0]
        for axis in self.window.fig.axes:
            ticks = [tick for coord in (axis.xaxis, axis.yaxis)
                     for tick in coord.get_major_ticks() + coord.get_minor_ticks()]
            lines = [tick.gridline for tick in ticks]
            self.assertTrue(lines)
            self.assertEqual(visible and axis is primary, any(line.get_visible() for line in lines))

    def test_global_marker_change_replaces_existing_curve_markers_and_survives_redraw(self):
        self.window._plotted_line_artists[0][0].set_color("red")
        self.apply_style(marker="s")
        self.assertEqual(["s", "s"], self.markers())
        self.assertEqual("red", self.window._plotted_line_artists[0][0].get_color())
        self.window.update_plot()
        self.assertEqual(["s", "s"], self.markers())

    def assert_curve_colors(self, subplot, expected):
        lines = self.window._plotted_line_artists[subplot]
        self.assertEqual([mpl.colors.to_rgba(color) for color in expected],
                         [mpl.colors.to_rgba(line.get_color()) for line in lines])

    def test_changing_preset_recolors_every_subplot_and_survives_redraw(self):
        self.window.subplot_series.append([1, 0])
        self.window.subplot_series_props.append([
            {"color": "purple", "linewidth": 2.5, "label": "Torque label"},
            {"color": "pink", "yaxis": 2},
        ])
        self.window.subplot_config.append(self.window._make_default_subplot_config())
        self.window.update_plot()
        self.window._plotted_line_artists[0][0].set_color("cyan")
        self.apply_style(preset="Style 1")
        self.assert_curve_colors(0, ["b", "r"])
        self.assert_curve_colors(1, ["b", "r"])
        self.window.update_plot()
        self.assert_curve_colors(0, ["b", "r"])
        self.assert_curve_colors(1, ["b", "r"])
        self.assertEqual(2.5, self.window._plotted_line_artists[1][0].get_linewidth())
        self.assertEqual("Torque label", self.window._plotted_line_artists[1][0].get_label())
        self.assertEqual(2, self.window.subplot_series_props[1][1]["yaxis"])

    def test_switching_presets_reloads_each_palette_including_default(self):
        for preset, colors in (
            ("Style 2", ["#2962ff", "r"]),
            ("Style 1", ["b", "r"]),
            ("Default", ["blue", "orange"]),
            ("IEEE", ["k", "r"]),
        ):
            with self.subTest(preset=preset):
                self.window._plotted_line_artists[0][0].set_color("pink")
                self.apply_style(preset=preset)
                self.assert_curve_colors(0, colors)

    def test_preset_change_recolors_curves_when_other_settings_are_defaults_only(self):
        self.window._plotted_line_artists[0][0].set_color("pink")
        self.apply_style(preset="Style 2", marker="s", grid=False, existing=False)
        self.assert_curve_colors(0, ["#2962ff", "r"])
        self.assertEqual(["o", "^"], self.markers())
        self.assert_grid(True)

    def test_global_marker_deactivation_removes_existing_curve_markers(self):
        self.apply_style(marker="")
        self.assertEqual(["None", "None"], self.markers())
        self.window.update_plot()
        self.assertEqual(["None", "None"], self.markers())

    def test_explicit_curve_marker_deactivation_overrides_subplot_default(self):
        self.window.subplot_config[0]["marker"] = "s"
        self.window.subplot_series_props[0][0]["marker"] = ""
        self.window._skip_runtime_style_capture = True
        self.window.update_plot()
        self.assertEqual(["None", "^"], self.markers())

    def test_defaults_only_keeps_existing_markers_and_grid(self):
        self.apply_style(marker="s", grid=False, existing=False)
        self.assertEqual(["o", "^"], self.markers())
        self.assert_grid(True)
        self.assertEqual("s", self.window.default_plot_style["marker"])
        self.assertFalse(self.window.default_plot_style["grid_show"])

    def test_new_subplot_uses_marker_and_grid_defaults_from_style_dialog(self):
        self.apply_style(marker="s", grid=False, existing=False)
        errors = []

        def select_series():
            dialog = self.app.activeModalWidget()
            try:
                source = next(widget for widget in dialog.findChildren(QtWidgets.QListWidget)
                              if widget.count())
                source.itemDoubleClicked.emit(source.item(0))
                dialog.findChild(QtWidgets.QDialogButtonBox).button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok,
                ).click()
            except Exception as exc:
                errors.append(exc)
                dialog.reject()

        QtCore.QTimer.singleShot(0, select_series)
        self.window.show_series_selector()
        if errors:
            raise errors[0]
        self.assertEqual("s", self.window._plotted_line_artists[1][0].get_marker())
        self.assertFalse(any(line.get_visible() for line in self.window.current_axes[1].get_xgridlines()))

    def test_grid_can_be_disabled_and_reenabled_with_each_preset(self):
        for preset in ("Default", "Style 1", "Style 2", "IEEE"):
            with self.subTest(preset=preset):
                self.apply_style(grid=False, preset=preset)
                self.assert_grid(False)
                self.window.update_plot()
                self.assert_grid(False)
                self.apply_style(grid=True, preset=preset)
                self.assert_grid(True)


    def test_adding_curve_to_existing_subplot_preserves_its_marker_default(self):
        self.window.subplot_series = [[0]]
        self.window.subplot_series_props = [[{"marker": "o"}]]
        self.window.update_plot()
        self.apply_style(marker="s", existing=False)
        errors = []

        def add_curve():
            dialog = self.app.activeModalWidget()
            try:
                source = next(widget for widget in dialog.findChildren(QtWidgets.QListWidget)
                              if widget.count() and widget.item(0).text() == "Torque")
                source.itemDoubleClicked.emit(source.item(0))
                dialog.findChild(QtWidgets.QDialogButtonBox).button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok,
                ).click()
            except Exception as exc:
                errors.append(exc)
                dialog.reject()

        QtCore.QTimer.singleShot(0, add_curve)
        self.window.on_canvas_click(SimpleNamespace(inaxes=self.window.current_axes[0], dblclick=True))
        if errors:
            raise errors[0]
        self.assertEqual(["o", "None"], self.markers())


if __name__ == "__main__":
    unittest.main()
