# -*- coding: utf-8 -*-
import unittest
import flet as ft
from ui_app import create_app
from pathlib import Path
from i18n import t, clear_subscribers


class TestFletAppLifecycle(unittest.TestCase):
    def tearDown(self):
        clear_subscribers()
    def test_app_view_building(self):
        """Simulate creating the Flet page and verifying all controls render without errors."""
        app_main = create_app()

        # Create a mock Page
        class MockPage:
            def __init__(self):
                self.title = ""
                self.window = type("MockWindow", (), {"width": 0, "height": 0, "min_width": 0, "min_height": 0})()
                self.padding = 0
                self.theme = None
                self.dark_theme = None
                self.theme_mode = None
                self.services = []
                self.overlay = []
                self.appbar = None
                self.controls = []

            def add(self, control):
                self.controls.append(control)

            def update(self):
                pass

            def run_task(self, coro):
                pass

        page = MockPage()

        # Run the app main function
        app_main(page)

        # Verify page properties
        self.assertEqual(page.title, t("app.title"))
        self.assertEqual(len(page.services), 1)  # FilePicker registered
        self.assertIsNotNone(page.appbar)
        self.assertEqual(len(page.controls), 1)  # app_tabs added

        # Check tabs
        tabs = page.controls[0]
        self.assertIsInstance(tabs, ft.Tabs)
        self.assertEqual(tabs.length, 2)

    def test_snack_bar_single_close_icon(self):
        """Verify show_notification produces SnackBar with only the right close icon and no duplicate action."""
        app_main = create_app()

        class MockPage:
            def __init__(self):
                self.title = ""
                self.window = type("MockWindow", (), {"width": 0, "height": 0, "min_width": 0, "min_height": 0})()
                self.padding = 0
                self.theme = None
                self.dark_theme = None
                self.theme_mode = None
                self.services = []
                self.overlay = []
                self.appbar = None
                self.controls = []

            def add(self, control):
                self.controls.append(control)

            def update(self):
                pass

            def run_task(self, coro):
                pass

        page = MockPage()
        app_main(page)

        # Trigger notification via template button in tab 2
        tab2 = page.controls[0].content.controls[1].controls[1]

        def find_buttons(ctrl):
            btns = []
            if hasattr(ctrl, "content") and ctrl.content:
                btns.extend(find_buttons(ctrl.content))
            if hasattr(ctrl, "controls") and ctrl.controls:
                for c in ctrl.controls:
                    btns.extend(find_buttons(c))
            if isinstance(ctrl, (ft.TextButton, ft.IconButton)):
                btns.append(ctrl)
            return btns

        template_btn = None
        target_template_text = t("archive.btn_template_csv")
        for b in find_buttons(tab2):
            text = getattr(b, "text", "")
            if hasattr(b, "content") and hasattr(b.content, "controls"):
                text = " ".join(getattr(c, "value", "") for c in b.content.controls)
            if target_template_text in text or "填入標籤範本" in text:
                template_btn = b
                break

        self.assertIsNotNone(template_btn)
        template_btn.on_click(None)

        self.assertEqual(len(page.overlay), 1)
        snack = page.overlay[0]
        self.assertIsInstance(snack, ft.SnackBar)
        self.assertTrue(snack.show_close_icon)
        self.assertEqual(snack.close_icon_color, ft.Colors.WHITE)
        self.assertIsNone(snack.action)
        self.assertIsInstance(snack.content, ft.Text)
        self.assertEqual(snack.content.value, t("archive.notify_template_filled"))
        self.assertEqual(snack.bgcolor, ft.Colors.INDIGO_700)
        self.assertEqual(snack.duration, 4000)
        self.assertTrue(snack.open)

    def test_snack_bar_error_and_overlay_cleanup(self):
        """Verify error notification styling, overlay deduplication, and preservation of other overlay controls."""
        app_main = create_app()

        class MockPage:
            def __init__(self):
                self.title = ""
                self.window = type("MockWindow", (), {"width": 0, "height": 0, "min_width": 0, "min_height": 0})()
                self.padding = 0
                self.theme = None
                self.dark_theme = None
                self.theme_mode = None
                self.services = []
                self.overlay = []
                self.appbar = None
                self.controls = []

            def add(self, control):
                self.controls.append(control)

            def update(self):
                pass

            def run_task(self, coro, fn=None):
                if fn:
                    fn()
                elif callable(coro):
                    coro()

        page = MockPage()
        app_main(page)

        tab1 = page.controls[0].content.controls[1].controls[0]
        tab2 = page.controls[0].content.controls[1].controls[1]

        def find_buttons(ctrl):
            btns = []
            if hasattr(ctrl, "content") and ctrl.content:
                btns.extend(find_buttons(ctrl.content))
            if hasattr(ctrl, "controls") and ctrl.controls:
                for c in ctrl.controls:
                    btns.extend(find_buttons(c))
            if isinstance(ctrl, (ft.TextButton, ft.IconButton, ft.Button, ft.OutlinedButton, ft.FilledButton)):
                btns.append(ctrl)
            return btns

        # 1. Trigger error notification via read_toc in Tab 1
        read_btn = None
        target_read_text = t("rip.read_toc")
        for b in find_buttons(tab1):
            text = getattr(b, "text", "")
            if hasattr(b, "content") and hasattr(b.content, "controls"):
                text = " ".join(getattr(c, "value", "") for c in b.content.controls)
            if target_read_text in text or "讀取" in text:
                read_btn = b
                break

        self.assertIsNotNone(read_btn)
        read_btn.on_click(None)

        self.assertEqual(len(page.overlay), 1)
        err_snack = page.overlay[0]
        self.assertIsInstance(err_snack, ft.SnackBar)
        self.assertTrue(err_snack.show_close_icon)
        self.assertEqual(err_snack.close_icon_color, ft.Colors.WHITE)
        self.assertIsNone(err_snack.action)
        self.assertEqual(err_snack.bgcolor, ft.Colors.RED_700)
        self.assertTrue(err_snack.open)

        # 2. Add an unrelated control into overlay (e.g. modal dialog placeholder)
        dummy_dialog = ft.Container()
        page.overlay.append(dummy_dialog)
        self.assertEqual(len(page.overlay), 2)

        # 3. Trigger success notification via template button in Tab 2
        template_btn = None
        target_template_text = t("archive.btn_template_csv")
        for b in find_buttons(tab2):
            text = getattr(b, "text", "")
            if hasattr(b, "content") and hasattr(b.content, "controls"):
                text = " ".join(getattr(c, "value", "") for c in b.content.controls)
            if target_template_text in text or "填入標籤範本" in text:
                template_btn = b
                break

        self.assertIsNotNone(template_btn)
        template_btn.on_click(None)

        # Overlay should contain the dummy_dialog and the new success snack (previous error snack removed)
        self.assertEqual(len(page.overlay), 2)
        self.assertIn(dummy_dialog, page.overlay)
        new_snack = [ctl for ctl in page.overlay if isinstance(ctl, ft.SnackBar)][0]
        self.assertEqual(new_snack.bgcolor, ft.Colors.INDIGO_700)
        self.assertTrue(new_snack.show_close_icon)
        self.assertEqual(new_snack.close_icon_color, ft.Colors.WHITE)
        self.assertIsNone(new_snack.action)
        self.assertIsInstance(new_snack.content, ft.Text)


if __name__ == '__main__':
    unittest.main()
