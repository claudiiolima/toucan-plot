import os
import unittest
from types import SimpleNamespace

import matplotlib as mpl
import numpy as np
from cycler import cycler

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from toucan_plot.main import MainWindow


class SubplotColorSequenceTests(unittest.TestCase):
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
        self.window.series_list = [(f"Signal{idx}", lambda x, f: x, x) for idx in range(6)]
        self.window._loaded_files = [{"name": "data.csv", "series_indices": list(range(6))}]

    def select_series(self, indices, subplot=None):
        errors = []

        def interact():
            dialog = self.app.activeModalWidget()
            try:
                for index in indices:
                    for widget in dialog.findChildren(QtWidgets.QListWidget):
                        item = next((widget.item(row) for row in range(widget.count())
                                     if widget.item(row).data(QtCore.Qt.ItemDataRole.UserRole) == index), None)
                        if item is not None:
                            widget.itemDoubleClicked.emit(item)
                            break
                    else:
                        raise AssertionError(f"Available signal {index} not found")
                dialog.findChild(QtWidgets.QDialogButtonBox).button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok,
                ).click()
            except Exception as exc:
                errors.append(exc)
                dialog.reject()

        QtCore.QTimer.singleShot(0, interact)
        if subplot is None:
            self.window.show_series_selector()
        else:
            self.window.on_canvas_click(SimpleNamespace(
                inaxes=self.window.current_axes[subplot], dblclick=True,
            ))
        if errors:
            raise errors[0]

    def assert_colors(self, subplot, expected):
        actual = [mpl.colors.to_rgba(line.get_color())
                  for line in self.window._plotted_line_artists[subplot]]
        self.assertEqual([mpl.colors.to_rgba(color) for color in expected], actual)

    def test_adding_series_to_previous_subplot_continues_color_sequence(self):
        self.select_series([0, 1])
        self.select_series([5])
        self.select_series([2], subplot=0)
        self.assert_colors(0, ["blue", "orange", "green"])
        self.assert_colors(1, ["blue"])

    def test_repeated_additions_and_redraws_do_not_restart_color_sequence(self):
        self.select_series([0])
        self.select_series([5])
        self.select_series([1], subplot=0)
        self.window.update_plot()
        self.assert_colors(0, ["blue", "orange"])
        self.select_series([2], subplot=0)
        self.window.update_plot()
        self.assert_colors(0, ["blue", "orange", "green"])

    def test_custom_curve_color_is_preserved_while_new_series_gets_next_color(self):
        self.select_series([0])
        self.window._plotted_line_artists[0][0].set_color("#13579b")
        self.select_series([5])
        self.select_series([1], subplot=0)
        self.assert_colors(0, ["#13579b", "orange"])

    def test_color_sequence_follows_active_palette_and_wraps(self):
        mpl.rcParams["axes.prop_cycle"] = cycler("color", ["#123456", "#abcdef"])
        self.select_series([0])
        self.select_series([5])
        self.select_series([1, 2], subplot=0)
        self.assert_colors(0, ["#123456", "#abcdef", "#123456"])
        self.assert_colors(1, ["#123456"])

    def test_primary_and_secondary_curves_share_subplot_color_sequence(self):
        self.select_series([0, 1])
        self.window.subplot_series_props[0][1]["yaxis"] = 2
        self.window._skip_runtime_style_capture = True
        self.window.update_plot()
        self.window._skip_runtime_style_capture = False
        self.select_series([5])
        self.select_series([2], subplot=0)
        self.assert_colors(0, ["blue", "orange", "green"])
        self.assertEqual(2, self.window.subplot_series_props[0][1]["yaxis"])


if __name__ == "__main__":
    unittest.main()
