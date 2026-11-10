import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import can
import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
from asammdf import MDF, Signal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from toucan_plot.main import MainWindow


class FileLoadAutoscaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name)
        self.columns = {
            "Time": np.array([0.0, 5.0, 10.0]),
            "Speed": np.array([100.0, 200.0, 300.0]),
            "Torque": np.array([1000.0, 3000.0, 5000.0]),
            "Current": np.array([-5.0, 0.0, 10.0]),
        }
        self.csv_path = self.path / "data.csv"
        self.csv_path.write_text("Time,Speed,Torque,Current\n0,100,1000,-5\n5,200,3000,0\n10,300,5000,10\n", encoding="utf-8")

    def make_window(self):
        window = MainWindow()
        self.addCleanup(window.close)
        return window

    def write_zoomed_settings(self, data_path, prefix=""):
        root = ET.Element("toucan_plot_settings", version="1", x_axis_column="Time")
        subplots = ET.SubElement(root, "subplots")
        subplot = ET.SubElement(subplots, "subplot")
        ET.SubElement(subplot, "limits", x_min="4", x_max="6", y_min="150", y_max="160")
        ET.SubElement(subplot, "labels", xlabel="Recorded time", ylabel_primary="Speed label")
        axes = ET.SubElement(subplot, "y_axes")
        for axis_id, label, low, high in ((1, "Speed label", 150, 160), (2, "Torque label", 2500, 2600), (3, "Current label", -1, 1)):
            ET.SubElement(axes, "y_axis", id=str(axis_id), label=label, scale="linear", y_min=str(low), y_max=str(high))
        series = ET.SubElement(subplot, "series")
        for axis_id, name in enumerate(("Speed", "Torque", "Current"), 1):
            ET.SubElement(series, "item", name=prefix+name, yaxis=str(axis_id), label=name+" curve", color="red")
        ET.ElementTree(root).write(data_path.with_suffix(".xml"), encoding="utf-8")

    def assert_fitted(self, window):
        self.assertEqual(1, len(window.current_axes))
        axis_map = window._subplot_axes_map[0]
        for axis_id, low, high in ((1, 100.0, 300.0), (2, 1000.0, 5000.0), (3, -5.0, 10.0)):
            axis = axis_map[axis_id]
            np.testing.assert_allclose([0.0, 10.0], axis.get_xlim())
            ymin, ymax = axis.get_ylim()
            self.assertLessEqual(ymin, low)
            self.assertGreaterEqual(ymax, high)
            self.assertLess(ymax-ymin, (high-low)*1.5)
        self.assertEqual("Recorded time", window.current_axes[0].get_xlabel())
        self.assertEqual("Torque label", axis_map[2].get_ylabel())
        self.assertTrue(all(line.get_color() == "red" for line in window._plotted_line_artists[0]))

    def test_csv_saved_settings_fit_primary_and_all_secondary_axes(self):
        self.write_zoomed_settings(self.csv_path)
        window = self.make_window()
        window._load_csv(str(self.csv_path))
        self.assert_fitted(window)
        window.update_plot()
        self.assert_fitted(window)

    def test_feather_and_mf4_saved_settings_also_fit_both_axes(self):
        feather_path = self.path / "data.feather"
        feather.write_feather(pa.table(self.columns), feather_path)
        mf4_path = self.path / "data.mf4"
        with MDF() as recording:
            recording.append([Signal(samples=values, timestamps=self.columns["Time"], name=name)
                              for name, values in self.columns.items() if name != "Time"])
            recording.save(mf4_path, overwrite=True)
        for data_path, method in ((feather_path, "_load_feather"), (mf4_path, "_load_mf4")):
            with self.subTest(format=data_path.suffix):
                self.write_zoomed_settings(data_path)
                window = self.make_window()
                getattr(window, method)(str(data_path))
                self.assert_fitted(window)

    def test_can_saved_settings_fit_native_samples_on_every_y_axis(self):
        log_path = self.path / "data.blf"
        dbc_path = self.path / "signals.dbc"
        dbc_path.write_text('''VERSION ""

NS_ :

BS_:

BU_: Logger

BO_ 256 Status: 8 Logger
 SG_ Speed : 0|16@1+ (1,0) [0|65535] "" Logger
 SG_ Torque : 16|16@1+ (1,0) [0|65535] "" Logger
 SG_ Current : 32|16@1- (1,0) [-32768|32767] "" Logger
''', encoding="utf-8")
        with can.BLFWriter(log_path) as writer:
            for offset, speed, torque, current in zip(*self.columns.values()):
                data = int(speed).to_bytes(2, "little") + int(torque).to_bytes(2, "little") + int(current).to_bytes(2, "little", signed=True) + bytes(2)
                writer.on_message_received(can.Message(timestamp=1_700_000_000.0+offset, arbitration_id=256,
                                                      is_extended_id=False, data=data))
        self.write_zoomed_settings(log_path, prefix="Status.")
        window = self.make_window()
        with patch.object(window, "_show_can_statistics"):
            window._load_blf(str(log_path), [str(dbc_path)])
        self.assert_fitted(window)

    def test_files_without_settings_fit_after_series_selection(self):
        window = self.make_window()
        def select_series():
            indices = {name: idx for idx, (name, _, _) in enumerate(window.series_list)}
            window.subplot_series = [[indices[name] for name in ("Speed", "Torque", "Current")]]
            window.subplot_series_props = [[{"yaxis": axis_id, "color": "red"} for axis_id in (1, 2, 3)]]
            window.subplot_axes_labels = [{"xlabel": "Recorded time", "ylabel_primary": "Speed label"}]
            window.subplot_yaxis_settings = [{axis_id: dict(window._make_default_yaxis_settings(axis_id), label=label)
                                             for axis_id, label in ((1, "Speed label"), (2, "Torque label"), (3, "Current label"))}]
            window.update_plot()
            for axis in window.fig.axes:
                axis.set_xlim(4, 6)
                axis.set_ylim(0, 1)
        with patch.object(window, "show_series_selector", side_effect=select_series):
            window._load_csv(str(self.csv_path))
        self.assert_fitted(window)

    def test_home_fit_ignores_measure_cursors_outside_the_data_range(self):
        self.write_zoomed_settings(self.csv_path)
        window = self.make_window()
        window._load_csv(str(self.csv_path))
        window._measure_x = [-100.0, 200.0]
        window._measure_active = True
        window._draw_measure_lines()
        window._home_autoscale()
        self.assert_fitted(window)
        self.assertTrue(all(line.get_visible() for group in window._measure_lines for line in group))

    def test_merge_fits_new_file_data_beyond_previous_zoom(self):
        self.write_zoomed_settings(self.csv_path)
        window = self.make_window()
        window._load_csv(str(self.csv_path))
        window.current_axes[0].set_xlim(4, 6)
        second_path = self.path / "additional.csv"
        second_path.write_text("Time,Value\n20,9000\n30,10000\n", encoding="utf-8")
        def add_merged_signal():
            window.subplot_series[0].append(len(window.series_list)-1)
            window.subplot_series_props[0].append({"yaxis": 1})
            window.update_plot()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileNames", return_value=([str(second_path)], "")), patch.object(
            window, "show_series_selector", side_effect=add_merged_signal,
        ):
            window.merge_file()
        np.testing.assert_allclose([0.0, 30.0], window.current_axes[0].get_xlim())
        self.assertLessEqual(window.current_axes[0].get_ylim()[0], 100.0)
        self.assertGreaterEqual(window.current_axes[0].get_ylim()[1], 10000.0)


    def test_failed_load_in_merged_session_keeps_current_zoom(self):
        self.write_zoomed_settings(self.csv_path)
        missing_path = str(self.path / "missing.csv")
        for merge in (False, True):
            with self.subTest(merge=merge):
                window = self.make_window()
                window._load_csv(str(self.csv_path))
                window._enable_merged_mode()
                window.current_axes[0].set_xlim(4, 6)
                window.current_axes[0].set_ylim(150, 160)
                with patch.object(QtWidgets.QMessageBox, "warning"), patch.object(
                    window, "show_series_selector",
                ), patch.object(QtWidgets.QFileDialog, "getOpenFileNames", return_value=([missing_path], "")):
                    if merge:
                        window.merge_file()
                    else:
                        window.open_files([missing_path])
                np.testing.assert_allclose([4.0, 6.0], window.current_axes[0].get_xlim())
                np.testing.assert_allclose([150.0, 160.0], window.current_axes[0].get_ylim())


if __name__ == "__main__":
    unittest.main()
