import os
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import can

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from toucan_plot.main import MainWindow
from toucan_plot.utils.loaders import can_log_load_worker

DBC_TEXT = '''VERSION ""

NS_ :

BS_:

BU_: Logger

BO_ 256 Status: 8 Logger
 SG_ Value : 0|16@1+ (1,0) [0|65535] "" Logger
'''


class CanStatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.blf_path = Path(self.temp_dir.name) / "recording.blf"
        self.dbc_path = Path(self.temp_dir.name) / "signals.dbc"
        self.dbc_path.write_text(DBC_TEXT, encoding="utf-8")

    def write_frames(self, frames):
        with can.BLFWriter(self.blf_path) as writer:
            for offset, options in frames:
                fields = dict(
                    timestamp=1_700_000_000.0 + offset,
                    arbitration_id=0x100,
                    is_extended_id=False,
                    data=[1, 0, 0, 0, 0, 0, 0, 0],
                    channel=0,
                )
                fields.update(options)
                writer.on_message_received(can.Message(**fields))

    def worker_messages(self):
        messages = queue.Queue()
        can_log_load_worker(str(self.blf_path), [str(self.dbc_path)], messages)
        result = []
        while not messages.empty():
            result.append(messages.get_nowait())
        return result

    def test_statistics_include_frames_excluded_from_decoding(self):
        self.write_frames([
            (0, {"is_error_frame": True}),
            (1, {}),
            (2, {"arbitration_id": 0x200, "channel": 1}),
            (3, {"data": [1]}),
            (4, {"is_remote_frame": True}),
            (5, {}),
            (6, {"is_error_frame": True}),
        ])
        messages = self.worker_messages()
        self.assertFalse(any(m[0] == "error" for m in messages))
        statistics = [m[1] for m in messages if m[0] == "can_statistics"]
        self.assertEqual(1, len(statistics))
        stats = statistics[0]
        self.assertEqual(7, stats["total_frames"])
        self.assertEqual(2, stats["decoded_frames"])
        self.assertEqual(1, stats["unknown_id_frames"])
        self.assertEqual(1, stats["decode_error_frames"])
        self.assertEqual(2, stats["error_frames"])
        self.assertEqual(1, stats["remote_frames"])
        self.assertEqual(2, stats["unique_ids"])
        self.assertEqual([0, 1], stats["channels"])
        self.assertAlmostEqual(6.0, stats["duration"])
        self.assertEqual(1, stats["decoded_signals"])
        self.assertEqual(3, len(next(m[1] for m in messages if m[0] == "result")))

    def test_single_frame_has_zero_duration(self):
        self.write_frames([(0, {})])
        statistics = [m[1] for m in self.worker_messages() if m[0] == "can_statistics"]
        self.assertEqual(1, len(statistics))
        self.assertEqual(0.0, statistics[0]["duration"])

    def test_successful_load_opens_statistics_window_in_normal_and_merge_mode(self):
        cases = (
            (False, [(0, {}), (2, {})], "2", "2.000 s", "1.00 frames/s"),
            (True, [(0, {}), (2, {})], "2", "2.000 s", "1.00 frames/s"),
            (False, [(0, {})], "1", "0.000 s", "N/A"),
        )
        for merge, frames, count, duration, rate in cases:
            with self.subTest(merge=merge, frames=len(frames)):
                self.write_frames(frames)
                window = MainWindow()
                dialogs = []

                def close_message_boxes():
                    for widget in self.app.topLevelWidgets():
                        if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                            dialogs.append((widget.windowTitle(), widget.text()))
                            widget.accept()

                timer = QtCore.QTimer()
                timer.timeout.connect(close_message_boxes)
                timer.start(10)
                try:
                    with patch.object(window, "show_series_selector"):
                        if merge:
                            window._merge_load_blf(
                                str(self.blf_path), [str(self.dbc_path)], "recording.blf",
                            )
                        else:
                            window._load_blf(str(self.blf_path), [str(self.dbc_path)])
                    self.assertEqual(1, len(dialogs))
                    title, text = dialogs[0]
                    self.assertEqual("CAN statistics", title)
                    self.assertIn("recording.blf", text)
                    self.assertIn(f"Total frames: {count}", text)
                    self.assertIn(f"Decoded frames: {count}", text)
                    self.assertIn(f"Duration: {duration}", text)
                    self.assertIn(f"Average frame rate: {rate}", text)
                    self.assertEqual(1, len(window.series_list))
                finally:
                    timer.stop()
                    window.close()


if __name__ == "__main__":
    unittest.main()
