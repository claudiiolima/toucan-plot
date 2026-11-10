import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from toucan_plot.main import MainWindow


class ExpressionSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_path = Path(self.temp_dir.name) / "recording.blf"

    def make_window(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._main_opened_file_path = str(self.data_path)
        window._x_col_name = "Time"
        window._all_columns = {
            "Time": np.array([0.0, 0.5, 1.0]),
            "Torque": np.array([2.0, -4.0, 6.0]),
            "Speed": np.array([10.0, 20.0, 30.0]),
        }
        x = window._all_columns["Time"]
        for name in ("Torque", "Speed"):
            data = window._all_columns[name]
            window.series_list.append((name, lambda x, f, data=data: data, x))
        window._loaded_files = [{"name": "recording.blf", "series_indices": [0, 1]}]
        return window

    def write_settings(self, subplots, x_column="Time"):
        root = ET.Element("toucan_plot_settings", version="1", x_axis_column=x_column)
        plots = ET.SubElement(root, "subplots")
        for names in subplots:
            series = ET.SubElement(ET.SubElement(plots, "subplot"), "series")
            for name in names:
                ET.SubElement(series, "item", name=name)
        ET.ElementTree(root).write(self.data_path.with_suffix(".xml"), encoding="utf-8")

    def plotted_names(self, window):
        return [[window.series_list[i][0] for i in indices] for indices in window.subplot_series]

    def test_expression_saved_through_editor_is_plotted_after_reload(self):
        window = self.make_window()
        expression = '-"Torque"'
        editor_errors = []

        def add_expression():
            dialog = self.app.activeModalWidget()
            try:
                field = next(field for field in dialog.findChildren(QtWidgets.QLineEdit)
                             if field.placeholderText().startswith("e.g."))
                field.setText(expression)
                button = next(button for button in dialog.findChildren(QtWidgets.QPushButton)
                              if button.text() == "Add")
                button.click()
                dialog.findChild(QtWidgets.QDialogButtonBox).button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok,
                ).click()
            except Exception as exc:
                editor_errors.append(exc)
                dialog.reject()

        QtCore.QTimer.singleShot(0, add_expression)
        window.show_series_selector()
        self.assertEqual([], editor_errors)
        self.assertEqual([[expression]], self.plotted_names(window))
        window.subplot_series_props[0][0].update(
            label="Negative torque", color="red", linewidth=2.5, linestyle="--", yaxis=2,
        )
        window._skip_runtime_style_capture = True
        window.update_plot()
        window._skip_runtime_style_capture = False
        with patch.object(QtWidgets.QMessageBox, "information"):
            window.save_plot_settings()
        self.assertTrue(self.data_path.with_suffix(".xml").exists())

        reloaded = self.make_window()
        self.assertTrue(reloaded._try_load_plot_settings(str(self.data_path)))
        self.assertEqual([[expression]], self.plotted_names(reloaded))
        index = reloaded.subplot_series[0][0]
        name, func, x = reloaded.series_list[index]
        np.testing.assert_array_equal([-2.0, 4.0, -6.0], func(x, 1))
        props = reloaded.subplot_series_props[0][0]
        self.assertEqual("Negative torque", props["label"])
        self.assertEqual("red", props["color"])
        self.assertEqual(2.5, props["linewidth"])
        self.assertEqual("--", props["linestyle"])
        self.assertEqual(2, props["yaxis"])
        line = reloaded._plotted_line_artists[0][0]
        np.testing.assert_array_equal([-2.0, 4.0, -6.0], line.get_ydata())
        expressions = next(entry for entry in reloaded._loaded_files if entry["name"] == "(Expressions)")
        self.assertEqual([index], expressions["series_indices"])

    def test_legacy_expression_is_reused_across_subplots_and_repeated_loads(self):
        expression = '"Torque" * 2 + "Torque"'
        self.write_settings([["Speed", expression], [expression]])
        window = self.make_window()
        for _ in range(2):
            self.assertTrue(window._try_load_plot_settings(str(self.data_path)))
            self.assertEqual([["Speed", expression], [expression]], self.plotted_names(window))
            self.assertEqual(3, len(window.series_list))
            np.testing.assert_array_equal([6.0, -12.0, 18.0], window._plotted_line_artists[1][0].get_ydata())

    def test_missing_or_invalid_expressions_do_not_hide_valid_saved_series(self):
        expression = 'sqrt(abs("Torque"))'
        self.write_settings([['"Missing" * 2', '"Torque" +', "Speed", expression]])
        window = self.make_window()
        self.assertTrue(window._try_load_plot_settings(str(self.data_path)))
        self.assertEqual([["Speed", expression]], self.plotted_names(window))
        np.testing.assert_allclose([np.sqrt(2), 2.0, np.sqrt(6)], window._plotted_line_artists[0][1].get_ydata())

    def test_saved_expression_cannot_overwrite_recording_signals(self):
        for expression in ('sin("Torque", out="Torque")', 'sin("Torque", "Speed")'):
            with self.subTest(expression=expression):
                self.write_settings([["Torque", expression]])
                window = self.make_window()
                self.assertTrue(window._try_load_plot_settings(str(self.data_path)))
                np.testing.assert_array_equal([2.0, -4.0, 6.0], window._all_columns["Torque"])
                np.testing.assert_array_equal([10.0, 20.0, 30.0], window._all_columns["Speed"])
                self.assertEqual([["Torque"]], self.plotted_names(window))
                np.testing.assert_array_equal([2.0, -4.0, 6.0], window._plotted_line_artists[0][0].get_ydata())
                self.assertEqual(2, len(window.series_list))
                self.assertEqual(1, len(window._loaded_files))

    def test_restored_expression_uses_saved_x_axis(self):
        expression = '"Torque" / 2'
        self.write_settings([[expression]], x_column="Speed")
        window = self.make_window()
        self.assertTrue(window._try_load_plot_settings(str(self.data_path)))
        self.assertEqual([[expression]], self.plotted_names(window))
        line = window._plotted_line_artists[0][0]
        np.testing.assert_array_equal([10.0, 20.0, 30.0], line.get_xdata())
        np.testing.assert_array_equal([1.0, -2.0, 3.0], line.get_ydata())


if __name__ == "__main__":
    unittest.main()
