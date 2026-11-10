import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtTest, QtWidgets

from toucan_plot.main import MainWindow


class NavigationShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        x = np.array([0.0, 1.0, 2.0])
        self.window.series_list = [("Signal", lambda x, f: x, x)]
        self.window.subplot_series = [[0]]
        self.window.subplot_series_props = [[{}]]
        self.window.update_plot()
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.assertTrue(self.window.isActiveWindow())

    def press(self, key):
        QtTest.QTest.keyClick(self.window.canvas, key)
        self.app.processEvents()

    def assert_mode(self, mode):
        self.assertEqual(mode, self.window.current_axes[0].get_navigate_mode())
        for name, selected_mode in (("Pan", "PAN"), ("Zoom", "ZOOM")):
            action = next(action for action in self.window.nav_toolbar.actions() if action.text() == name)
            self.assertEqual(mode == selected_mode, action.isChecked())

    def test_p_toggles_pan_mode_and_toolbar_button(self):
        self.press(QtCore.Qt.Key.Key_P)
        self.assert_mode("PAN")
        self.press(QtCore.Qt.Key.Key_P)
        self.assert_mode(None)

    def test_z_toggles_zoom_mode_and_toolbar_button(self):
        self.press(QtCore.Qt.Key.Key_Z)
        self.assert_mode("ZOOM")
        self.press(QtCore.Qt.Key.Key_Z)
        self.assert_mode(None)

    def test_o_is_an_alternative_zoom_shortcut(self):
        self.press(QtCore.Qt.Key.Key_O)
        self.assert_mode("ZOOM")
        self.press(QtCore.Qt.Key.Key_O)
        self.assert_mode(None)

    def test_switching_shortcuts_keeps_pan_and_zoom_mutually_exclusive(self):
        self.press(QtCore.Qt.Key.Key_P)
        self.assert_mode("PAN")
        self.press(QtCore.Qt.Key.Key_Z)
        self.assert_mode("ZOOM")
        self.press(QtCore.Qt.Key.Key_P)
        self.assert_mode("PAN")

    def test_typing_in_dialog_does_not_activate_navigation_shortcuts(self):
        dialog = QtWidgets.QDialog(self.window)
        self.addCleanup(dialog.close)
        dialog.setModal(True)
        field = QtWidgets.QLineEdit(dialog)
        QtWidgets.QVBoxLayout(dialog).addWidget(field)
        dialog.show()
        dialog.activateWindow()
        field.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClicks(field, "pzo")
        self.app.processEvents()
        self.assertEqual("pzo", field.text())
        self.assert_mode(None)


if __name__ == "__main__":
    unittest.main()
