import os
import unittest

import matplotlib as mpl
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtTest, QtWidgets

from toucan_plot.main import MainWindow


class ThemeToggleButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.rc_context = mpl.rc_context()
        self.rc_context.__enter__()
        self.addCleanup(self.rc_context.__exit__, None, None, None)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        x = np.array([0.0, 1.0, 2.0])
        self.window.series_list = [("Signal", lambda x, f: x, x)]
        self.window.subplot_series = [[0]]
        self.window.subplot_series_props = [[{}]]
        self.window.update_plot()
        self.window.resize(1000, 650)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()

    def button(self):
        button = self.window.findChild(QtWidgets.QToolButton, "theme_toggle_button")
        self.assertIsNotNone(button, "Theme switching must be available from the top toolbar")
        return button

    def test_theme_icon_is_visible_at_top_right_of_plot_toolbar(self):
        button = self.button()
        self.assertTrue(button.isVisible())
        self.assertFalse(button.icon().isNull())
        button_right = button.mapTo(self.window, button.rect().topRight())
        canvas_right = self.window.canvas.mapTo(self.window, self.window.canvas.rect().topRight())
        self.assertLessEqual(abs(button_right.x()-canvas_right.x()), 16)
        self.assertLess(button_right.y(), canvas_right.y())
        toolbar_center = self.window.nav_toolbar.mapTo(self.window, self.window.nav_toolbar.rect().center())
        button_center = button.mapTo(self.window, button.rect().center())
        self.assertLessEqual(abs(button_center.y()-toolbar_center.y()), 4)

    def test_clicking_theme_icon_switches_canvas_palette_and_available_action(self):
        button = self.button()
        light_icon = button.icon().cacheKey()
        light_color = mpl.colors.to_rgba(self.window._plotted_line_artists[0][0].get_color())
        QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual("dark", self.window._current_theme)
        self.assertLess(max(self.window.fig.get_facecolor()[:3]), 0.2)
        self.assertNotEqual(light_color, mpl.colors.to_rgba(self.window._plotted_line_artists[0][0].get_color()))
        self.assertIn("light", button.toolTip().lower())
        self.assertIn("light", button.accessibleName().lower())
        self.assertNotEqual(light_icon, button.icon().cacheKey())
        QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual("light", self.window._current_theme)
        self.assertGreater(min(self.window.fig.get_facecolor()[:3]), 0.9)
        self.assertIn("dark", button.toolTip().lower())

    def test_applying_theme_updates_toolbar_icon_and_next_click(self):
        button = self.button()
        self.window._apply_theme("dark")
        self.app.processEvents()
        self.assertIn("light", button.toolTip().lower())
        self.assertFalse(button.icon().isNull())
        QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
        self.assertEqual("light", self.window._current_theme)

    def test_theme_icon_can_be_activated_with_keyboard(self):
        button = self.button()
        button.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(button, QtCore.Qt.Key.Key_Space)
        self.app.processEvents()
        self.assertEqual("dark", self.window._current_theme)
        self.assertIn("light", button.accessibleName().lower())


if __name__ == "__main__":
    unittest.main()
