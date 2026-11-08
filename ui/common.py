# -*- coding: utf-8 -*-
"""
Common utilities and UI helper components for CD-RIP Tool.
"""

import os
import threading
from pathlib import Path
import flet as ft


def format_mm_ss(seconds: float) -> str:
    """Format seconds into mm:ss string."""
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"


def send_native_notification(title: str, message: str, icon_path: str = None):
    """Sends native Windows Toast notification via winotify with PowerShell fallback."""
    def _send():
        try:
            from winotify import Notification
            use_icon = icon_path if icon_path and os.path.exists(icon_path) else ""
            toast = Notification(
                app_id="CD-RIP Tool",
                title=title,
                msg=message,
                icon=use_icon
            )
            toast.show()
        except Exception:
            try:
                import subprocess
                clean_title = title.replace("'", "''")
                clean_msg = message.replace("'", "''")
                ps_script = f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                $xml = $template.GetXml()
                $textNodes = $template.GetElementsByTagName("text")
                $textNodes.Item(0).AppendChild($template.CreateTextNode('{clean_title}')) > $null
                $textNodes.Item(1).AppendChild($template.CreateTextNode('{clean_msg}')) > $null
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("CD-RIP Tool")
                $notifier.Show($toast)
                '''
                subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps_script])
            except Exception as e:
                print(f"[Notice] Failed to send toast notification: {e}")

    threading.Thread(target=_send, daemon=True).start()


def create_progress_cell(prog: float) -> ft.DataCell:
    """Creates a compact percentage progress bar cell for the track table."""
    if prog <= 0:
        return ft.DataCell(
            ft.Row(
                [
                    ft.ProgressBar(value=0.0, width=90, height=8, border_radius=ft.BorderRadius.all(4), color=ft.Colors.GREY_400),
                    ft.Text("0%", size=11, color=ft.Colors.OUTLINE),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    elif prog >= 1.0:
        return ft.DataCell(
            ft.Row(
                [
                    ft.ProgressBar(value=1.0, width=90, height=8, border_radius=ft.BorderRadius.all(4), color=ft.Colors.GREEN),
                    ft.Text("100%", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    else:
        pct = int(prog * 100)
        return ft.DataCell(
            ft.Row(
                [
                    ft.ProgressBar(value=prog, width=90, height=8, border_radius=ft.BorderRadius.all(4), color=ft.Colors.PRIMARY),
                    ft.Text(f"{pct}%", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
