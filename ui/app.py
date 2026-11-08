# -*- coding: utf-8 -*-
"""
Main Application Shell and Layout Orchestration.
Integrates Tab 1 (Rip) and Tab 2 (Archive) into a Material 3 Desktop GUI
with multi-language (i18n) support, OS language auto-detection, and theme toggling.
"""

import threading
import flet as ft

from config import cfg
from i18n import t, set_locale, get_locale, get_available_locales, init_locale, subscribe
from ui.tab_rip import build_rip_tab
from ui.tab_archive import build_archive_tab


def create_app():
    """Factory creating the main Flet application entry function."""
    def main(page: ft.Page):
        # 0. Initialize Language (Config preference or OS auto-detect)
        init_locale(cfg.language)

        # 1. Page & Window Configuration
        page.title = t("app.title")
        page.window.width = 1260
        page.window.height = 840
        page.window.min_width = 1000
        page.window.min_height = 700
        page.padding = 0

        # Material 3 Theme setup
        page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.INDIGO,
            use_material3=True,
        )
        page.dark_theme = ft.Theme(
            color_scheme_seed=ft.Colors.INDIGO,
            use_material3=True,
        )
        page.theme_mode = ft.ThemeMode.SYSTEM

        # 2. FilePicker Service Registration
        file_picker = ft.FilePicker()
        page.services.append(file_picker)

        # Thread-safe UI update dispatcher using page.run_task
        async def dispatch_ui_task(fn):
            fn()
            page.update()

        def post_ui(fn):
            """Safely post a UI update callable to Flet's event loop."""
            page.run_task(dispatch_ui_task, fn)

        # SnackBar notification helper
        def show_notification(message: str, is_error: bool = False):
            page.overlay[:] = [ctl for ctl in page.overlay if not isinstance(ctl, ft.SnackBar)]

            snack = ft.SnackBar(
                content=ft.Text(message, color=ft.Colors.WHITE, size=13),
                bgcolor=ft.Colors.RED_700 if is_error else ft.Colors.INDIGO_700,
                duration=4000,
                show_close_icon=True,
                close_icon_color=ft.Colors.WHITE,
            )
            page.overlay.append(snack)
            snack.open = True
            page.update()

        # 3. Build Modular Tabs
        tab2_view, refresh_pending_albums, on_keyboard_event = build_archive_tab(
            page=page,
            file_picker=file_picker,
            show_notification=show_notification,
            post_ui=post_ui,
        )

        tab1_view, tab1_initial_check = build_rip_tab(
            page=page,
            file_picker=file_picker,
            show_notification=show_notification,
            post_ui=post_ui,
            on_rip_completed=refresh_pending_albums,
        )

        # Keyboard event hook
        page.on_keyboard_event = on_keyboard_event

        # 4. Main Tabs Shell
        tab1_tab = ft.Tab(
            label=t("app.tab_rip"),
            icon=ft.Icons.ALBUM_OUTLINED,
        )
        tab2_tab = ft.Tab(
            label=t("app.tab_archive"),
            icon=ft.Icons.FOLDER_SPECIAL_OUTLINED,
        )

        app_tabs = ft.Tabs(
            content=ft.Column(
                [
                    ft.TabBar(
                        tabs=[
                            tab1_tab,
                            tab2_tab,
                        ],
                        divider_color=ft.Colors.OUTLINE_VARIANT,
                        indicator_color=ft.Colors.PRIMARY,
                    ),
                    ft.TabBarView(
                        controls=[
                            tab1_view,
                            tab2_view,
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            length=2,
            selected_index=0,
            expand=True,
        )

        def is_dark_active():
            if page.theme_mode == ft.ThemeMode.DARK:
                return True
            if page.theme_mode == ft.ThemeMode.LIGHT:
                return False
            return getattr(page, "platform_brightness", None) == ft.Brightness.DARK

        def update_theme_ui():
            if is_dark_active():
                theme_btn.icon = ft.Icons.LIGHT_MODE_OUTLINED
                theme_btn.tooltip = t("app.theme_switch_light")
            else:
                theme_btn.icon = ft.Icons.DARK_MODE_OUTLINED
                theme_btn.tooltip = t("app.theme_switch_dark")

        def toggle_theme(e):
            if is_dark_active():
                page.theme_mode = ft.ThemeMode.LIGHT
            else:
                page.theme_mode = ft.ThemeMode.DARK
            update_theme_ui()
            page.update()

        theme_btn = ft.IconButton(
            icon=ft.Icons.LIGHT_MODE_OUTLINED if is_dark_active() else ft.Icons.DARK_MODE_OUTLINED,
            tooltip=t("app.theme_switch_light") if is_dark_active() else t("app.theme_switch_dark"),
            on_click=toggle_theme,
        )

        # Language dropdown in AppBar
        def on_lang_change(e=None):
            new_lang = None
            if e is not None:
                if hasattr(e, "control") and getattr(e.control, "value", None):
                    new_lang = e.control.value
                elif hasattr(e, "data") and e.data:
                    new_lang = e.data
            if not new_lang:
                new_lang = getattr(lang_dd, "value", None)

            if new_lang:
                lang_dd.value = new_lang
                set_locale(new_lang)
                cfg.set_language(new_lang)

        lang_options = [
            ft.DropdownOption(key=loc["code"], text=loc["name"])
            for loc in get_available_locales()
        ]

        lang_dd = ft.Dropdown(
            options=lang_options,
            value=get_locale(),
            width=185,
            dense=True,
            leading_icon=ft.Icons.LANGUAGE,
            tooltip=t("app.language"),
            on_select=on_lang_change,
        )
        lang_dd.on_change = on_lang_change  # Compatibility with unit test invocation and on_change callers

        appbar_title = ft.Text(t("app.appbar_title"), size=18, weight=ft.FontWeight.W_600)

        page.appbar = ft.AppBar(
            leading=ft.Icon(icon=ft.Icons.ALBUM_ROUNDED, color=ft.Colors.PRIMARY),
            title=appbar_title,
            center_title=False,
            bgcolor=ft.Colors.SURFACE,
            actions=[
                lang_dd,
                theme_btn,
                ft.Container(width=8),
            ],
        )

        page.add(app_tabs)

        # Retranslate shell elements when language changes
        def retranslate_shell():
            page.title = t("app.title")
            appbar_title.value = t("app.appbar_title")
            tab1_tab.label = t("app.tab_rip")
            tab2_tab.label = t("app.tab_archive")
            update_theme_ui()
            lang_dd.tooltip = t("app.language")
            lang_dd.value = get_locale()
            page.update()

        subscribe(retranslate_shell)

        # 5. Background Initial Boot
        def initial_boot():
            tab1_initial_check()
            refresh_pending_albums()
            page.update()

        threading.Thread(target=initial_boot, daemon=True).start()

    return main


def run_gui():
    """Launch Desktop App."""
    app_fn = create_app()
    ft.run(app_fn)
