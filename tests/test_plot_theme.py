import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib as mpl
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from toucan_plot.main import MainWindow


def luminance(color):
    rgb = np.array(mpl.colors.to_rgb(color))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return float(np.dot(linear, [0.2126, 0.7152, 0.0722]))


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


class PlotThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.rc_context = mpl.rc_context()
        self.rc_context.__enter__()
        self.addCleanup(self.rc_context.__exit__, None, None, None)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        x = np.linspace(0.0, 10.0, 11)
        self.window._x_col_name = "Time"
        self.window._all_columns = {"Time": x}
        self.window.series_list = [(f"Signal{idx}", lambda x, f, idx=idx: x*(idx+1), x) for idx in range(6)]
        self.window.subplot_series = [[0, 1, 2, 3, 4, 5]]
        self.window.subplot_series_props = [[{"yaxis": 2 if idx == 1 else 1} for idx in range(6)]]
        self.window.subplot_config = [self.window._make_default_subplot_config()]
        self.window.update_plot()

    def apply_preset(self, preset):
        errors = []
        def interact():
            dialog = self.app.activeModalWidget()
            try:
                combo = next(combo for combo in dialog.findChildren(QtWidgets.QComboBox)
                             if dialog.layout().labelForField(combo).text() == "Preset from styles.py")
                combo.setCurrentText(preset)
                dialog.findChild(QtWidgets.QDialogButtonBox).button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok,
                ).click()
            except Exception as exc:
                errors.append(exc)
                dialog.reject()
        QtCore.QTimer.singleShot(0, interact)
        self.window.show_plot_style_dialog()
        if errors:
            raise errors[0]

    def assert_dark_readable(self):
        self.assertLess(luminance(self.window.fig.get_facecolor()), 0.05)
        for axis in self.window.fig.axes:
            background = axis.get_facecolor()
            self.assertLess(luminance(background), 0.05)
            self.assertGreater(contrast(axis.xaxis.label.get_color(), background), 4.5)
            self.assertGreater(contrast(axis.yaxis.label.get_color(), background), 4.5)
            for label in axis.get_xticklabels() + axis.get_yticklabels():
                self.assertGreater(contrast(label.get_color(), background), 4.5)
            legend = axis.get_legend()
            if legend is not None:
                legend_background = legend.get_frame().get_facecolor()
                self.assertLess(luminance(legend_background), 0.08)
                for label in legend.get_texts():
                    self.assertGreater(contrast(label.get_color(), legend_background), 4.5)
        for lines in self.window._plotted_line_artists:
            for line in lines:
                self.assertGreater(contrast(line.get_color(), line.axes.get_facecolor()), 3.0)

    def test_dark_theme_covers_canvas_axes_legends_and_uses_readable_series_palette(self):
        self.window._apply_theme("dark")
        self.assert_dark_readable()
        self.window.update_plot()
        self.assert_dark_readable()

    def test_theme_switch_restores_light_palette_and_preserves_zoom_and_series(self):
        self.window.current_axes[0].set_xscale("log")
        self.window.current_axes[0].set_xlim(2.0, 7.0)
        self.window.current_axes[0].set_ylim(1.0, 8.0)
        before = [line.get_ydata().copy() for line in self.window._plotted_line_artists[0]]
        self.window._subplot_axes_map[0][2].set_yscale("log")
        self.window._plotted_line_artists[0][0].set_linewidth(3.0)
        self.window._plotted_line_artists[0][0].set_linestyle("--")
        self.window._apply_theme("dark")
        self.assert_dark_readable()
        self.assertEqual("log", self.window.current_axes[0].get_xscale())
        self.window._apply_theme("light")
        self.assertGreater(luminance(self.window.fig.get_facecolor()), 0.9)
        self.assertEqual("log", self.window.current_axes[0].get_xscale())
        for axis in self.window.fig.axes:
            self.assertGreater(luminance(axis.get_facecolor()), 0.9)
            self.assertGreater(contrast(axis.yaxis.label.get_color(), axis.get_facecolor()), 4.5)
        self.assertEqual([mpl.colors.to_rgba(color) for color in ("blue", "orange", "green", "red", "purple", "brown")],
                         [mpl.colors.to_rgba(line.get_color()) for line in self.window._plotted_line_artists[0]])
        self.assertEqual("log", self.window._subplot_axes_map[0][2].get_yscale())
        self.assertEqual(3.0, self.window._plotted_line_artists[0][0].get_linewidth())
        self.assertEqual("--", self.window._plotted_line_artists[0][0].get_linestyle())
        np.testing.assert_allclose([2.0, 7.0], self.window.current_axes[0].get_xlim())
        np.testing.assert_allclose([1.0, 8.0], self.window.current_axes[0].get_ylim())
        for old, line in zip(before, self.window._plotted_line_artists[0]):
            np.testing.assert_array_equal(old, line.get_ydata())

    def test_dark_canvas_and_palette_survive_every_preset_change(self):
        self.window._apply_theme("dark")
        for preset in ("Style 1", "Style 2", "IEEE", "Default"):
            with self.subTest(preset=preset):
                self.apply_preset(preset)
                self.assert_dark_readable()
                self.window.update_plot()
                self.assert_dark_readable()

    def test_new_curves_continue_dark_palette_after_another_subplot_is_added(self):
        self.window._apply_theme("dark")
        self.window.subplot_series = [[0], [1]]
        self.window.subplot_series_props = [[{}], [{}]]
        self.window.update_plot()
        first_color = self.window._plotted_line_artists[0][0].get_color()
        self.window.subplot_series[0].append(2)
        self.window.subplot_series_props[0].append({})
        self.window.update_plot()
        colors = [line.get_color() for line in self.window._plotted_line_artists[0]]
        self.assertEqual(first_color, colors[0])
        self.assertNotEqual(mpl.colors.to_rgba(colors[0]), mpl.colors.to_rgba(colors[1]))
        self.assert_dark_readable()

    def test_saved_settings_load_keeps_the_canvas_dark(self):
        self.window._apply_theme("dark")
        with tempfile.TemporaryDirectory() as temp:
            data_path = Path(temp) / "recording.csv"
            root = ET.Element("toucan_plot_settings", version="1", x_axis_column="Time")
            series = ET.SubElement(ET.SubElement(ET.SubElement(root, "subplots"), "subplot"), "series")
            ET.SubElement(series, "item", name="Signal0", color="blue", linewidth="2.5")
            ET.ElementTree(root).write(data_path.with_suffix(".xml"))
            self.assertTrue(self.window._try_load_plot_settings(str(data_path)))
        self.assert_dark_readable()

    def test_measurement_cursors_are_visible_in_dark_theme(self):
        self.window._apply_theme("dark")
        self.window._measure_x = [2.0, 7.0]
        self.window._measure_active = True
        self.window._draw_measure_lines()
        for lines in self.window._measure_lines:
            for line in lines:
                self.assertGreater(contrast(line.get_color(), line.axes.get_facecolor()), 3.0)


if __name__ == "__main__":
    unittest.main()
