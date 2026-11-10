import os
from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import can
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from toucan_plot.main import MainWindow


DBC_HEADER = '''VERSION ""

NS_ :

BS_:

BU_: Logger

'''


class DbcFileSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name)
        self.log_path = self.path / "recording.blf"
        self.dbc_paths = []
        for frame_id, message in ((256, "Fast"), (512, "Slow")):
            dbc_path = self.path / (message + ".dbc")
            dbc_path.write_text(DBC_HEADER +
                f'BO_ {frame_id} {message}: 8 Logger\n'
                ' SG_ Value : 0|16@1+ (1,0) [0|65535] "" Logger\n',
                encoding="utf-8")
            self.dbc_paths.append(str(dbc_path))
        with can.BLFWriter(self.log_path) as writer:
            for offset, frame_id, value in ((0, 256, 10), (1, 512, 20)):
                writer.on_message_received(can.Message(
                    timestamp=1_700_000_000.0 + offset,
                    arbitration_id=frame_id, is_extended_id=False,
                    data=[value, 0, 0, 0, 0, 0, 0, 0],
                ))
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        for method in ("_show_can_statistics", "show_series_selector"):
            patcher = patch.object(self.window, method)
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextmanager
    def choose_dbc_action(self, label):
        def choose(dialog):
            button = next(button for button in dialog.buttons() if button.text() == label)
            button.click()
            return 0

        with patch.object(QtWidgets.QMessageBox, "exec", choose):
            yield

    def load_initial_can_log(self):
        self.window.open_files([str(self.log_path), *self.dbc_paths])
        next_log = self.path / "next.blf"
        next_log.write_bytes(self.log_path.read_bytes())
        return str(next_log)

    def assert_decoded_signals(self, prefix=""):
        signals = {name: func(x, 1.0) for name, func, x in self.window.series_list}
        self.assertIn(prefix + "Fast.Value", signals)
        self.assertIn(prefix + "Slow.Value", signals)
        np.testing.assert_array_equal([10, 10], signals[prefix + "Fast.Value"])
        np.testing.assert_array_equal([np.nan, 20], signals[prefix + "Slow.Value"])

    def test_opening_can_log_alone_asks_for_dbcs_and_decodes_with_all_selected_files(self):
        for extension, writer_type in (("blf", None), ("trc", can.TRCWriter), ("asc", can.ASCWriter)):
            with self.subTest(extension=extension):
                log_path = self.path / ("recording." + extension)
                if writer_type is not None:
                    with can.BLFReader(self.log_path) as reader, writer_type(log_path) as writer:
                        for frame in reader:
                            writer.on_message_received(frame)
                with self.choose_dbc_action("Reuse DBC files"), patch.object(
                    QtWidgets.QFileDialog, "getOpenFileNames", return_value=(self.dbc_paths, "DBC files (*.dbc)"),
                ):
                    self.window.open_files([str(log_path)])
                self.assert_decoded_signals()

    def test_provided_dbcs_load_without_asking_again(self):
        with patch.object(QtWidgets.QFileDialog, "getOpenFileNames",
                          side_effect=AssertionError("DBC picker should not open")):
            self.window.open_files([str(self.log_path), *self.dbc_paths])
        self.assert_decoded_signals()

    def test_merging_can_log_alone_asks_for_dbcs_and_appends_decoded_signals(self):
        self.window._append_merged_columns(
            "Time", {"Time": np.array([1_700_000_000.0, 1_700_000_001.0]),
                     "Temperature": np.array([5.0, 6.0])}, "data.csv",
        )
        with patch.object(QtWidgets.QFileDialog, "getOpenFileNames", side_effect=[
            ([str(self.log_path)], ""), (self.dbc_paths, "DBC files (*.dbc)"),
        ]):
            self.window.merge_file()
        self.assert_decoded_signals(prefix="recording.blf: ")
        self.assertEqual("data.csv: Temperature", self.window.series_list[0][0])
        self.assertTrue(self.window._merged_mode)

    def test_cancelling_dbc_selection_keeps_existing_session_unchanged(self):
        self.window._append_merged_columns(
            "Time", {"Time": np.array([0.0, 1.0]), "Value": np.array([5.0, 6.0])}, "data.csv",
        )
        for merge in (False, True):
            with self.subTest(merge=merge):
                replies = [([], "")]
                if merge:
                    replies.insert(0, ([str(self.log_path)], ""))
                with patch.object(QtWidgets.QFileDialog, "getOpenFileNames", side_effect=replies):
                    if merge:
                        self.window.merge_file()
                    else:
                        self.window.open_files([str(self.log_path)])
                self.assertFalse(self.window._merged_mode)
                self.assertEqual(["data.csv: Value"], [name for name, _, _ in self.window.series_list])
                self.assertEqual(["data.csv"], [entry["name"] for entry in self.window._loaded_files])


    def test_subsequent_can_log_can_reuse_all_previous_dbcs_without_file_picker(self):
        next_log = self.load_initial_can_log()
        with self.choose_dbc_action("Reuse DBC files"), patch.object(
            QtWidgets.QFileDialog, "getOpenFileNames", return_value=([], ""),
        ):
            self.window.open_files([next_log])
        self.assertEqual(next_log, self.window._main_opened_file_path)
        self.assert_decoded_signals()

    def test_chosen_replacement_dbcs_are_used_and_remembered_for_later_logs(self):
        next_log = self.load_initial_can_log()
        replacements = []
        for old_path in self.dbc_paths:
            old_file = Path(old_path)
            new_file = self.path / ("other_" + old_file.name)
            new_file.write_text(old_file.read_text(encoding="utf-8").replace(
                old_file.stem + ":", "Other" + old_file.stem + ":"), encoding="utf-8")
            replacements.append(str(new_file))
        with self.choose_dbc_action("Choose other DBC files"), patch.object(
            QtWidgets.QFileDialog, "getOpenFileNames", return_value=(replacements, ""),
        ):
            self.window.open_files([next_log])
        self.assertEqual(["OtherFast.Value", "OtherSlow.Value"],
                         [name for name, _, _ in self.window.series_list])
        with self.choose_dbc_action("Reuse DBC files"), patch.object(
            QtWidgets.QFileDialog, "getOpenFileNames", return_value=([], ""),
        ):
            self.window.open_files([str(self.log_path)])
        self.assertEqual(str(self.log_path), self.window._main_opened_file_path)
        self.assertEqual(["OtherFast.Value", "OtherSlow.Value"],
                         [name for name, _, _ in self.window.series_list])

    def test_cancelling_reuse_prompt_or_replacement_keeps_previous_dbcs(self):
        next_log = self.load_initial_can_log()
        for action in ("Cancel", "Choose other DBC files"):
            with self.subTest(action=action):
                with self.choose_dbc_action(action), patch.object(
                    QtWidgets.QFileDialog, "getOpenFileNames", return_value=([], ""),
                ):
                    self.window.open_files([next_log])
                self.assertEqual(str(self.log_path), self.window._main_opened_file_path)
                self.assertEqual(self.dbc_paths, self.window._dbc_paths)
                self.assertFalse(self.window._merged_mode)
                self.assert_decoded_signals()

    def test_merging_another_can_log_can_reuse_previous_dbcs(self):
        next_log = self.load_initial_can_log()
        with self.choose_dbc_action("Reuse DBC files"), patch.object(
            QtWidgets.QFileDialog, "getOpenFileNames", side_effect=[([next_log], "")],
        ):
            self.window.merge_file()
        self.assert_decoded_signals(prefix="next.blf: ")
        self.assertEqual(["recording.blf", "next.blf"],
                         [entry["name"] for entry in self.window._loaded_files])

    def test_explicit_dbcs_bypass_previous_dbc_prompt(self):
        next_log = self.load_initial_can_log()
        with patch.object(QtWidgets.QMessageBox, "exec", side_effect=AssertionError("Unexpected reuse prompt")):
            self.window.open_files([next_log, *self.dbc_paths])
        self.assertEqual(next_log, self.window._main_opened_file_path)
        self.assert_decoded_signals()

    def test_failed_replacement_load_preserves_previous_dbc_selection(self):
        next_log = self.load_initial_can_log()
        invalid_dbc = self.path / "invalid.dbc"
        invalid_dbc.write_text("invalid DBC contents", encoding="utf-8")
        with self.choose_dbc_action("Choose other DBC files"), patch.object(
            QtWidgets.QFileDialog, "getOpenFileNames", return_value=([str(invalid_dbc)], ""),
        ), patch.object(QtWidgets.QMessageBox, "warning"):
            self.window.open_files([next_log])
        self.assertEqual(str(self.log_path), self.window._main_opened_file_path)
        self.assertEqual(self.dbc_paths, self.window._dbc_paths)
        self.assert_decoded_signals()


if __name__ == "__main__":
    unittest.main()
