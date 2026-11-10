import os
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import can
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from toucan_plot.main import MainWindow
from toucan_plot.utils.loaders import can_log_load_worker


DBC_TEXT = '''VERSION ""

NS_ :

BS_:

BU_: Logger

BO_ 256 Fast: 8 Logger
 SG_ Value : 0|16@1+ (1,0) [0|65535] "" Logger

BO_ 512 Slow: 8 Logger
 SG_ Value : 0|16@1+ (1,0) [0|65535] "" Logger
'''


class CanSignalSamplesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name)
        self.dbc_path = self.path / "signals.dbc"
        self.dbc_path.write_text(DBC_TEXT, encoding="utf-8")
        self.blf_path = self.path / "recording.blf"
        with can.BLFWriter(self.blf_path) as writer:
            for offset, frame_id, value in (
                (0.0, 0x100, 10), (0.25, 0x200, 50),
                (0.5, 0x100, 10), (0.75, 0x200, 60),
                (1.0, 0x100, 20), (1.0, 0x100, 30),
            ):
                writer.on_message_received(can.Message(
                    timestamp=1_700_000_000.0 + offset,
                    arbitration_id=frame_id,
                    is_extended_id=False,
                    data=[value, 0, 0, 0, 0, 0, 0, 0],
                ))

    def test_decoder_preserves_native_samples_including_repeats_and_equal_timestamps(self):
        messages = queue.Queue()
        can_log_load_worker(str(self.blf_path), [str(self.dbc_path)], messages)
        output = []
        while not messages.empty():
            output.append(messages.get_nowait())
        self.assertFalse(any(item[0] == "error" for item in output), output)
        samples = [item[1] for item in output if item[0] == "can_samples"]
        self.assertEqual(1, len(samples), "Decoder must retain native per-signal samples")
        fast_x, fast_y = samples[0]["Fast.Value"]
        slow_x, slow_y = samples[0]["Slow.Value"]
        np.testing.assert_array_equal([0.0, 0.5, 1.0, 1.0], fast_x)
        np.testing.assert_array_equal([10, 10, 20, 30], fast_y)
        np.testing.assert_array_equal([0.25, 0.75], slow_x)
        np.testing.assert_array_equal([50, 60], slow_y)


    def load_window(self):
        window = MainWindow()
        self.addCleanup(window.close)
        with patch.object(window, "_show_can_statistics"), patch.object(window, "show_series_selector"):
            window._load_blf(str(self.blf_path), [str(self.dbc_path)])
        return window

    def plot_signals(self, window, mode="step"):
        window.subplot_series = [list(range(len(window.series_list)))]
        window.subplot_series_props = [[{"marker": "o"} for _ in window.series_list]]
        window.subplot_config = [dict(window._make_default_subplot_config(), plot_mode=mode)]
        window._skip_runtime_style_capture = True
        window.update_plot()
        window._skip_runtime_style_capture = False
        return {name: line for (name, _, _), line in
                zip(window.series_list, window._plotted_line_artists[0])}

    def assert_native_curves(self, lines, prefix="", origin=0.0):
        fast = lines[prefix + "Fast.Value"]
        slow = lines[prefix + "Slow.Value"]
        np.testing.assert_allclose(origin + np.array([0.0, 0.5, 1.0, 1.0]), fast.get_xdata(), rtol=0, atol=1e-7)
        np.testing.assert_array_equal([10, 10, 20, 30], fast.get_ydata())
        np.testing.assert_allclose(origin + np.array([0.25, 0.75]), slow.get_xdata(), rtol=0, atol=1e-7)
        np.testing.assert_array_equal([50, 60], slow.get_ydata())
        self.assertEqual("o", fast.get_marker())
        self.assertEqual("o", slow.get_marker())

    def test_can_curves_and_markers_use_only_the_signals_own_samples_in_both_plot_modes(self):
        window = self.load_window()
        for mode in ("step", "plot"):
            with self.subTest(mode=mode):
                self.assert_native_curves(self.plot_signals(window, mode))

    def test_merged_can_curves_keep_native_samples_on_absolute_time(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._append_merged_columns(
            "Time", {"Time": np.array([1_700_000_000.0, 1_700_000_001.0]),
                     "Temperature": np.array([5.0, 6.0])}, "data.csv",
        )
        window._enable_merged_mode()
        with patch.object(window, "_show_can_statistics"):
            window._merge_load_blf(str(self.blf_path), [str(self.dbc_path)], "recording.blf")
        lines = self.plot_signals(window)
        self.assert_native_curves(lines, prefix="recording.blf: ", origin=1_700_000_000.0)
        np.testing.assert_array_equal([5.0, 6.0], lines["data.csv: Temperature"].get_ydata())

    def test_changing_x_axis_preserves_native_signal_samples(self):
        window = self.load_window()
        window._change_x_axis("Slow.Value")
        lines = self.plot_signals(window)
        np.testing.assert_array_equal([np.nan, 50, 60, 60], lines["Fast.Value"].get_xdata())
        np.testing.assert_array_equal([10, 10, 20, 30], lines["Fast.Value"].get_ydata())
        window._change_x_axis("Time")
        self.assert_native_curves(self.plot_signals(window))

    def test_merge_transition_preserves_native_samples_after_custom_axis_and_expression(self):
        window = self.load_window()
        window._change_x_axis("Slow.Value")
        window._add_expression_series('"Fast.Value" * 2')
        window._enable_merged_mode()
        lines = self.plot_signals(window)
        self.assert_native_curves(lines, origin=1_700_000_000.0)
        self.assertIn('"Fast.Value" * 2', lines)

    def test_expressions_keep_existing_aligned_calculation_values(self):
        window = self.load_window()
        expression = window._add_expression_series('"Fast.Value" + "Slow.Value"')
        name, func, x = window.series_list[expression]
        np.testing.assert_array_equal([0.0, 0.25, 0.5, 0.75, 1.0], x)
        np.testing.assert_array_equal([np.nan, 60, 60, 70, 90], func(x, 1.0))


    def test_measure_cursors_follow_each_signals_native_plot_mode(self):
        window = self.load_window()
        for mode, expected in (("step", 50.0), ("plot", 55.0)):
            with self.subTest(mode=mode):
                self.plot_signals(window, mode)
                window._measure_x = [0.5, 0.75]
                window._show_measure_dialog()
                slow_row = next(row for row in range(window._measure_table.rowCount())
                                if window._measure_table.item(row, 0).text() == "Slow.Value")
                self.assertEqual(expected, float(window._measure_table.item(slow_row, 1).text()))
                self.assertEqual(60.0, float(window._measure_table.item(slow_row, 2).text()))
                window._measure_x = [0.0, 1.0]
                window._update_measure_dialog()
                self.assertTrue(np.isnan(float(window._measure_table.item(slow_row, 1).text())))
                self.assertTrue(np.isnan(float(window._measure_table.item(slow_row, 2).text())))
                window._measure_dialog.close()

    def test_measure_cursors_skip_unavailable_custom_x_samples(self):
        window = self.load_window()
        window._change_x_axis("Slow.Value")
        self.plot_signals(window)
        window._measure_x = [50.0, 60.0]
        window._show_measure_dialog()
        fast_row = next(row for row in range(window._measure_table.rowCount())
                        if window._measure_table.item(row, 0).text() == "Fast.Value")
        self.assertEqual(10.0, float(window._measure_table.item(fast_row, 1).text()))
        self.assertEqual(30.0, float(window._measure_table.item(fast_row, 2).text()))
        window._measure_dialog.close()

    def test_native_samples_survive_saved_settings_reload(self):
        window = self.load_window()
        self.plot_signals(window)
        with patch.object(QtWidgets.QMessageBox, "information"):
            window.save_plot_settings()
        reloaded = self.load_window()
        lines = {reloaded.series_list[idx][0]: line for idx, line in
                 zip(reloaded.subplot_series[0], reloaded._plotted_line_artists[0])}
        self.assert_native_curves(lines)

    def test_asc_and_trc_plots_preserve_native_signal_samples(self):
        for extension, writer_type in (("asc", can.ASCWriter), ("trc", can.TRCWriter)):
            with self.subTest(extension=extension):
                log_path = self.path / ("recording." + extension)
                with can.BLFReader(self.blf_path) as reader, writer_type(log_path) as writer:
                    for frame in reader:
                        writer.on_message_received(frame)
                window = MainWindow()
                self.addCleanup(window.close)
                with patch.object(window, "_show_can_statistics"), patch.object(window, "show_series_selector"):
                    window._load_blf(str(log_path), [str(self.dbc_path)])
                self.assert_native_curves(self.plot_signals(window))


if __name__ == "__main__":
    unittest.main()
