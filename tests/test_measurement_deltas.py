import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from toucan_plot.main import MainWindow


class MeasurementDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        x = np.array([0.0, 5.0, 10.0])
        self.window._x_col_name = "Time"
        self.window.series_list = [("Positive", lambda x, f: 2*x, x),
                                   ("Negative", lambda x, f: -x, x)]
        self.window.subplot_series = [[0, 1]]
        self.window.subplot_series_props = [[{}, {}]]
        self.window.update_plot()
        self.window._measure_x = [1.25, 4.5]
        self.window._show_measure_dialog()

    def test_measurements_show_delta_symbol_and_time_difference_for_every_signal(self):
        table = self.window._measure_table
        self.assertEqual(6, table.columnCount())
        self.assertEqual("Δ", table.horizontalHeaderItem(3).text())
        self.assertEqual("Δt", table.horizontalHeaderItem(4).text())
        self.assertEqual("1/Δt", table.horizontalHeaderItem(5).text())
        self.assertEqual(2, table.rowCount())
        self.assertEqual(6.5, float(table.item(0, 3).text()))
        self.assertEqual(-3.25, float(table.item(1, 3).text()))
        for row in range(table.rowCount()):
            self.assertEqual(3.25, float(table.item(row, 4).text()))
            self.assertAlmostEqual(0.307692, float(table.item(row, 5).text()))

    def test_delta_columns_update_and_keep_sign_when_cursors_are_reversed(self):
        self.window._measure_x = [4.5, 1.25]
        self.window._update_measure_dialog()
        table = self.window._measure_table
        self.assertEqual(-6.5, float(table.item(0, 3).text()))
        self.assertEqual(3.25, float(table.item(1, 3).text()))
        self.assertEqual(6, table.columnCount())
        for row in range(table.rowCount()):
            self.assertEqual(-3.25, float(table.item(row, 4).text()))
            self.assertAlmostEqual(-0.307692, float(table.item(row, 5).text()))

    def test_reciprocal_is_undefined_when_cursors_coincide(self):
        self.window._measure_x = [2.0, 2.0]
        self.window._update_measure_dialog()
        table = self.window._measure_table
        for row in range(table.rowCount()):
            self.assertEqual(0.0, float(table.item(row, 4).text()))
            self.assertEqual("—", table.item(row, 5).text())

    def test_small_cursor_spacing_keeps_reciprocal_precision(self):
        self.window._measure_x = [0.0, 0.00000001]
        self.window._update_measure_dialog()
        self.assertEqual(100000000.0, float(self.window._measure_table.item(0, 5).text()))

    def test_dialog_opens_wide_enough_for_columns_within_screen(self):
        self.app.processEvents()
        table = self.window._measure_table
        dialog = self.window._measure_dialog
        if table.viewport().width() < table.horizontalHeader().length():
            self.assertGreater(table.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(dialog.width(), dialog.screen().availableGeometry().width())

    def test_long_signal_names_keep_dialog_within_screen(self):
        _, func, data = self.window.series_list[0]
        self.window.series_list[0] = ('Signal' * 100, func, data)
        self.window._show_measure_dialog()
        self.app.processEvents()
        dialog = self.window._measure_dialog
        self.assertLessEqual(dialog.width(), dialog.screen().availableGeometry().width())
        self.assertGreater(self.window._measure_table.horizontalScrollBar().maximum(), 0)

    def test_non_time_x_axis_labels_coordinate_difference_as_delta_x(self):
        self.window._x_col_name = "Position"
        self.window._update_measure_dialog()
        table = self.window._measure_table
        self.assertEqual(6, table.columnCount())
        self.assertEqual("Δx", table.horizontalHeaderItem(4).text())
        self.assertEqual("1/Δx", table.horizontalHeaderItem(5).text())
        self.assertEqual(3.25, float(table.item(0, 4).text()))
        self.assertAlmostEqual(0.307692, float(table.item(0, 5).text()))

    def test_time_column_with_unit_keeps_delta_t_label(self):
        self.window._x_col_name = "Time [ms]"
        self.window._update_measure_dialog()
        table = self.window._measure_table
        self.assertEqual(6, table.columnCount())
        self.assertEqual("Δt", table.horizontalHeaderItem(4).text())
        self.assertEqual("1/Δt", table.horizontalHeaderItem(5).text())
        self.assertEqual(3.25, float(table.item(0, 4).text()))


if __name__ == "__main__":
    unittest.main()
