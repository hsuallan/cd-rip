# -*- coding: utf-8 -*-
"""
CD-RIP Tool - Material 3 Desktop GUI Application
Entrypoint and backward-compatibility module re-exporting from the modular ui package.
"""

from ui import (
    format_mm_ss,
    send_native_notification,
    create_progress_cell,
    build_rip_tab,
    build_archive_tab,
    create_app,
    run_gui,
)

__all__ = [
    "format_mm_ss",
    "send_native_notification",
    "create_progress_cell",
    "build_rip_tab",
    "build_archive_tab",
    "create_app",
    "run_gui",
]

if __name__ == "__main__":
    run_gui()
