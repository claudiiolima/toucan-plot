import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib as mpl
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from toucan_plot.main import MainWindow


class SavedPlotLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.rc_context = mpl.rc_context()
        self.rc_context.__enter__()
        self.addCleanup(self.rc_context.__exit__, None, None, None)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_path = Path(self.temp_dir.name) / "recording.blf"
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        x = np.linspace(0.0, 180.0, 100)
        self.window._all_columns = {"Time": x}
        self.window._x_col_name = "Time"
        for idx in range(4):
            name = f"Signal{idx}"
            values = np.sin(x / (idx + 1))
            self.window._all_columns[name] = values
            self.window.series_list.append((name, lambda x, f, values=values: values, x))

    def write_settings(self, secondary=False, outside_legend=False):
        root = ET.Element("toucan_plot_settings", version="1", x_axis_column="Time")
        subplots = ET.SubElement(root, "subplots")
        for count in (4, 4, 4, 4, 4):
            subplot = ET.SubElement(subplots, "subplot")
            ET.SubElement(subplot, "config", legend_pos="outside right" if outside_legend else "upper right")
            series = ET.SubElement(subplot, "series")
            for idx in range(count):
                ET.SubElement(series, "item", name=f"Signal{idx}", label=f"Signal {idx}",
                              yaxis="2" if secondary and idx == 1 else "1")
        ET.ElementTree(root).write(self.data_path.with_suffix(".xml"), encoding="utf-8")

    def assert_plots_use_available_height(self):
        axes = self.window.current_axes
        self.assertEqual(5, len(axes))
        for upper, lower in zip(axes, axes[1:]):
            upper_box = upper.get_position()
            lower_box = lower.get_position()
            gap = upper_box.y0 - lower_box.y1
            self.assertGreaterEqual(gap, 0.0)
            self.assertLess(gap, min(upper_box.height, lower_box.height),
                            "The space between restored plots must not exceed the plot height")

    def test_saved_plots_reflow_when_canvas_grows_after_loading(self):
        self.write_settings()
        self.assertTrue(self.window._try_load_plot_settings(str(self.data_path)))
        self.window.fig.set_size_inches(18.8, 8.5)
        self.window.canvas.draw()
        self.assert_plots_use_available_height()

    def test_redraw_and_resize_keep_saved_plots_compact(self):
        self.write_settings()
        self.assertTrue(self.window._try_load_plot_settings(str(self.data_path)))
        self.window.fig.set_size_inches(18.8, 8.5)
        self.window.update_plot()
        self.assert_plots_use_available_height()
        self.window.fig.set_size_inches(12.0, 6.0)
        self.window.canvas.draw()
        self.window.fig.set_size_inches(18.8, 8.5)
        self.window.canvas.draw()
        self.assert_plots_use_available_height()

    def test_secondary_axes_and_outside_legends_fit_after_saved_layout_load(self):
        self.write_settings(secondary=True, outside_legend=True)
        self.assertTrue(self.window._try_load_plot_settings(str(self.data_path)))
        self.window.fig.set_size_inches(18.8, 8.5)
        self.window.canvas.draw()
        self.assert_plots_use_available_height()
        renderer = self.window.canvas.get_renderer()
        for line_axes in self.window._subplot_axes_map:
            legend = next(reversed(line_axes.values())).get_legend()
            self.assertIsNotNone(legend)
            box = legend.get_window_extent(renderer)
            self.assertGreaterEqual(box.x0, self.window.fig.bbox.x0)
            self.assertLessEqual(box.x1, self.window.fig.bbox.x1)


if __name__ == "__main__":
    unittest.main()
