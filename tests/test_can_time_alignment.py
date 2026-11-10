import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import can
import numpy as np
from PySide6 import QtWidgets

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from toucan_plot.main import MainWindow
from toucan_plot.utils.loaders import can_log_load_worker


DBC_TEXT = """VERSION ""

NS_ :

BS_:

BU_: Logger

BO_ 256 Status: 8 Logger
 SG_ Value : 0|16@1+ (1,0) [0|65535] "" Logger
"""


class RecordingQueue:
    def __init__(self):
        self.messages = []

    def put(self, message):
        self.messages.append(message)


class MergeState:
    def __init__(self, series_list, can_time_origin):
        self.series_list = series_list
        self._can_time_origin = can_time_origin
        self._merged_mode = False
        self._x_col_name = ""
        self._all_columns = {}
        self._loaded_files = []
        self.subplot_series = []
        self.subplot_series_props = []
        self.subplot_axes_labels = []
        self.subplot_yaxis_settings = []
        self.subplot_config = []

    def _change_x_axis(self, column_name):
        MainWindow._change_x_axis(self, column_name)

    def _restore_existing_can_time_axis(self, time_origin):
        MainWindow._restore_existing_can_time_axis(self, time_origin)

    def update_plot(self):
        pass


class CanTimeAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_can_worker_keeps_elapsed_axis_and_reports_original_time_origin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dbc_path = temp_path / "signals.dbc"
            blf_path = temp_path / "recording.blf"
            dbc_path.write_text(DBC_TEXT, encoding="utf-8")

            with can.BLFWriter(blf_path) as writer:
                writer.on_message_received(can.Message(
                    timestamp=1_700_000_000.25,
                    arbitration_id=0x100,
                    data=[1, 0, 0, 0, 0, 0, 0, 0],
                ))
                writer.on_message_received(can.Message(
                    timestamp=1_700_000_000.75,
                    arbitration_id=0x100,
                    data=[2, 0, 0, 0, 0, 0, 0, 0],
                ))

            queue = RecordingQueue()
            can_log_load_worker(str(blf_path), [str(dbc_path)], queue)

        errors = [message for message in queue.messages if message[0] == "error"]
        self.assertEqual([], errors)
        payload = next(message[1] for message in queue.messages if message[0] == "result")
        self.assertEqual(3, len(payload))
        x_column, columns, time_origin = payload
        self.assertEqual("Time", x_column)
        np.testing.assert_allclose([0.0, 0.5], columns["Time"], atol=1e-7, rtol=0)
        self.assertAlmostEqual(1_700_000_000.25, time_origin, places=6)

    def test_can_worker_reports_absolute_origin_from_asc_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dbc_path = temp_path / "signals.dbc"
            asc_path = temp_path / "recording.asc"
            dbc_path.write_text(DBC_TEXT, encoding="utf-8")
            asc_path.write_text(
                "date Tue Nov 14 22:13:20.250 2023\n"
                "base hex timestamps absolute\n"
                "no internal events logged\n"
                "0.000000 1 100 Rx d 8 01 00 00 00 00 00 00 00\n"
                "0.500000 1 100 Rx d 8 02 00 00 00 00 00 00 00\n",
                encoding="utf-8",
            )

            queue = RecordingQueue()
            can_log_load_worker(str(asc_path), [str(dbc_path)], queue)

        errors = [message for message in queue.messages if message[0] == "error"]
        self.assertEqual([], errors)
        payload = next(message[1] for message in queue.messages if message[0] == "result")
        _, columns, time_origin = payload
        expected_origin = datetime(2023, 11, 14, 22, 13, 20, 250000).timestamp()
        np.testing.assert_allclose([0.0, 0.5], columns["Time"], atol=1e-7, rtol=0)
        self.assertAlmostEqual(expected_origin, time_origin, places=6)

    def test_enabling_merge_restores_can_origin_once(self):
        enable_merged_mode = getattr(MainWindow, "_enable_merged_mode", None)
        self.assertIsNotNone(enable_merged_mode)
        state = MergeState(
            [("Speed", lambda x, f: x, np.array([0.0, 0.5]))],
            can_time_origin=1_700_000_000.25,
        )

        enable_merged_mode(state)
        enable_merged_mode(state)

        self.assertTrue(state._merged_mode)
        self.assertIsNone(state._can_time_origin)
        np.testing.assert_allclose(
            [1_700_000_000.25, 1_700_000_000.75],
            state.series_list[0][2],
            atol=1e-7,
            rtol=0,
        )

    def test_enabling_merge_does_not_shift_an_absolute_csv_axis(self):
        enable_merged_mode = getattr(MainWindow, "_enable_merged_mode", None)
        self.assertIsNotNone(enable_merged_mode)
        timestamp = np.array([1_700_000_000.25, 1_700_000_000.75])
        state = MergeState(
            [("Temperature", lambda x, f: x, timestamp)],
            can_time_origin=None,
        )

        enable_merged_mode(state)

        self.assertTrue(state._merged_mode)
        np.testing.assert_array_equal(timestamp, state.series_list[0][2])

    def test_enabling_merge_restores_canonical_time_after_custom_x_axis(self):
        state = MergeState(
            [
                ("Time", lambda x, f: x, np.array([10.0, 20.0])),
                ("Torque", lambda x, f: x, np.array([10.0, 20.0])),
            ],
            can_time_origin=1_700_000_000.25,
        )
        state._x_col_name = "Speed"
        state._all_columns = {
            "Time": np.array([0.0, 0.5]),
            "Speed": np.array([10.0, 20.0]),
            "Torque": np.array([1.0, 2.0]),
        }
        state._loaded_files = [{"name": "recording.blf", "series_indices": [0, 1]}]
        state._measure_active = True
        state._measure_x = [10.0, 20.0]

        MainWindow._enable_merged_mode(state)

        self.assertEqual("Time", state._x_col_name)
        self.assertEqual(["Speed", "Torque"], [series[0] for series in state.series_list])
        for _, _, x_data in state.series_list:
            np.testing.assert_allclose(
                [1_700_000_000.25, 1_700_000_000.75],
                x_data,
                atol=1e-7,
                rtol=0,
            )
        np.testing.assert_allclose(
            [1_700_000_000.415, 1_700_000_000.58],
            state._measure_x,
            atol=1e-7,
            rtol=0,
        )

    def test_custom_x_axis_restoration_preserves_expression_ownership(self):
        state = MergeState(
            [
                ("Time", lambda x, f: np.array([0.0, 0.5]), np.array([10.0, 20.0])),
                ("Torque", lambda x, f: np.array([1.0, 2.0]), np.array([10.0, 20.0])),
                ('"Torque" * 2', lambda x, f: np.array([2.0, 4.0]), np.array([10.0, 20.0])),
            ],
            can_time_origin=1_700_000_000.25,
        )
        state._x_col_name = "Speed"
        state._all_columns = {
            "Time": np.array([0.0, 0.5]),
            "Speed": np.array([10.0, 20.0]),
            "Torque": np.array([1.0, 2.0]),
        }
        state._loaded_files = [
            {"name": "recording.blf", "series_indices": [0, 1]},
            {"name": "(Expressions)", "series_indices": [2]},
        ]

        MainWindow._enable_merged_mode(state)

        self.assertEqual(
            ["Speed", "Torque", '"Torque" * 2'],
            [series[0] for series in state.series_list],
        )
        self.assertEqual([0, 1], state._loaded_files[0]["series_indices"])
        self.assertEqual([2], state._loaded_files[1]["series_indices"])
        np.testing.assert_allclose(
            [1_700_000_000.25, 1_700_000_000.75],
            state.series_list[2][2],
            atol=1e-7,
            rtol=0,
        )

    def test_merge_transition_autoscales_shifted_can_timestamps(self):
        window = MainWindow()
        try:
            elapsed_time = np.array([0.0, 0.5])
            window._all_columns = {
                "Time": elapsed_time,
                "Speed": np.array([10.0, 20.0]),
            }
            window._x_col_name = "Time"
            window._can_time_origin = 1_700_000_000.25
            window.series_list = [
                ("Speed", lambda x, f: np.array([10.0, 20.0]), elapsed_time),
            ]
            window._loaded_files = [
                {"name": "recording.blf", "series_indices": [0]},
            ]
            window.subplot_series = [[0]]
            window.subplot_series_props = [[]]
            window.subplot_axes_labels = [
                {"xlabel": "", "ylabel_primary": "", "ylabel_secondary": ""},
            ]
            window.subplot_yaxis_settings = [
                {1: window._make_default_yaxis_settings(1)},
            ]
            window.subplot_config = [window._make_default_subplot_config()]
            window._measure_active = True
            window._measure_x = [0.1, 0.4]
            window.update_plot()

            window._enable_merged_mode()
            window.update_plot()

            np.testing.assert_allclose(
                [1_700_000_000.35, 1_700_000_000.65],
                window._measure_x,
                atol=1e-7,
                rtol=0,
            )
            x_min, x_max = window.current_axes[0].get_xlim()
            self.assertLessEqual(x_min, 1_700_000_000.25)
            self.assertGreaterEqual(x_max, 1_700_000_000.75)
        finally:
            window.close()

    def test_appending_can_data_restores_its_original_time_origin(self):
        append_merged_columns = getattr(MainWindow, "_append_merged_columns", None)
        self.assertIsNotNone(append_merged_columns)
        state = MergeState([], can_time_origin=None)

        append_merged_columns(
            state,
            "Time",
            {"Time": np.array([0.0, 0.5]), "Speed": np.array([10.0, 20.0])},
            "recording.blf",
            time_origin=1_700_000_000.25,
        )

        np.testing.assert_allclose(
            [1_700_000_000.25, 1_700_000_000.75],
            state.series_list[0][2],
            atol=1e-7,
            rtol=0,
        )

    def test_appending_csv_data_preserves_its_absolute_timestamps(self):
        append_merged_columns = getattr(MainWindow, "_append_merged_columns", None)
        self.assertIsNotNone(append_merged_columns)
        state = MergeState([], can_time_origin=None)
        timestamp = np.array([1_700_000_000.25, 1_700_000_000.75])

        append_merged_columns(
            state,
            "timestamp",
            {"timestamp": timestamp, "Temperature": np.array([30.0, 31.0])},
            "measurements.csv",
        )

        np.testing.assert_array_equal(timestamp, state.series_list[0][2])


if __name__ == "__main__":
    unittest.main()
