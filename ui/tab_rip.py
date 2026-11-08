# -*- coding: utf-8 -*-
"""
Tab 1: Continuous Transcoding Mode (連續轉檔模式)
Dedicated module for high-speed CD ripping, TOC reading, and disc batching.
"""

from datetime import datetime
from pathlib import Path
import flet as ft

from config import cfg
from i18n import t, subscribe
from ripper import read_cd_toc, CDRipperTask, eject_cd_drive
from ui.common import format_mm_ss, create_progress_cell, send_native_notification


def build_rip_tab(page: ft.Page, file_picker: ft.FilePicker, show_notification, post_ui, on_rip_completed=None):
    """
    Constructs and returns the Continuous Transcoding tab view and its initial boot handler.
    """
    rip_state = {
        "cd_count": 1,
        "is_ripping": False,
        "current_task": None,
        "toc": [],
        "status_key": "status_idle",
        "status_color": ft.Colors.ON_SURFACE_VARIANT,
        "status_fallback": None,
        "last_error": None,
        "disc_info_state": ("empty", {}),
    }

    # UI Controls
    drive_dd = ft.Dropdown(
        label=t("rip.drive_letter"),
        value=cfg.drive_letter,
        width=130,
        options=[
            ft.DropdownOption(key="D:", text="D:"),
            ft.DropdownOption(key="E:", text="E:"),
            ft.DropdownOption(key="F:", text="F:"),
            ft.DropdownOption(key="G:", text="G:"),
            ft.DropdownOption(key="H:", text="H:"),
            ft.DropdownOption(key="I:", text="I:"),
        ],
        dense=True,
    )

    cd_batch_label = ft.Text(t("rip.batch_code"), size=13, color=ft.Colors.ON_SURFACE_VARIANT)
    cd_count_text = ft.Text(f"CD #{rip_state['cd_count']:02d}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)

    target_dir_field = ft.TextField(
        label=t("rip.target_dir"),
        value=str(cfg.unprocessed_dir),
        expand=True,
        dense=True,
        read_only=False,
    )

    eject_switch = ft.Switch(
        label=t("rip.eject_switch"),
        value=cfg.eject_after_rip,
    )

    compression_field = ft.Dropdown(
        label=t("rip.flac_compression"),
        value=str(cfg.flac_compression_level),
        width=140,
        options=[
            ft.DropdownOption(key="5", text=t("rip.flac_level_5")),
            ft.DropdownOption(key="8", text=t("rip.flac_level_8")),
        ],
        dense=True,
    )

    disc_status_badge = ft.Container(
        content=ft.Text(t("rip.status_idle"), size=12, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE_VARIANT),
        padding=ft.Padding(left=10, top=4, right=10, bottom=4),
        border_radius=ft.BorderRadius.all(12),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )

    def set_disc_status(status_key: str, color, fallback_text: str = None):
        rip_state["status_key"] = status_key
        rip_state["status_color"] = color
        rip_state["status_fallback"] = fallback_text
        label = t(f"rip.{status_key}") if status_key else (fallback_text or "")
        disc_status_badge.content = ft.Text(label, size=12, weight=ft.FontWeight.W_500, color=color)

    disc_info_text = ft.Text(t("rip.disc_info_empty"), size=13, color=ft.Colors.OUTLINE)

    track_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text(t("rip.table_track"), weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text(t("rip.table_duration"), weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text(t("rip.table_start_lba"), weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text(t("rip.table_end_lba"), weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text(t("rip.table_status"), weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
        heading_row_height=36,
        data_row_min_height=32,
        data_row_max_height=36,
        column_spacing=28,
    )

    track_table_container = ft.Container(
        content=ft.Column(
            [track_table],
            scroll=ft.ScrollMode.AUTO,
        ),
        height=210,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=ft.BorderRadius.all(8),
        padding=ft.Padding(left=12, top=8, right=12, bottom=8),
    )

    # Progress elements
    current_track_progress_text = ft.Text(t("rip.track_progress_idle"), size=13, color=ft.Colors.ON_SURFACE_VARIANT)
    current_track_bar = ft.ProgressBar(value=0.0, height=8, border_radius=ft.BorderRadius.all(4))

    disc_progress_text = ft.Text(t("rip.disc_progress_idle"), size=13, weight=ft.FontWeight.W_500)
    disc_progress_bar = ft.ProgressBar(value=0.0, height=10, color=ft.Colors.INDIGO, border_radius=ft.BorderRadius.all(5))

    # Log viewer
    log_column = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=4,
        auto_scroll=True,
    )
    log_container = ft.Container(
        content=log_column,
        height=140,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=ft.BorderRadius.all(8),
        padding=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
    )

    def append_rip_log(msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_column.controls.append(
            ft.Text(f"[{timestamp}] {msg}", size=12, selectable=True)
        )
        page.update()

    # Action Buttons
    btn_start_rip_text = ft.Text(t("rip.start_rip"))
    btn_start_rip = ft.FilledButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.PLAY_ARROW_ROUNDED, size=18), btn_start_rip_text], spacing=4),
    )
    btn_cancel_rip_text = ft.Text(t("rip.cancel_rip"))
    btn_cancel_rip = ft.OutlinedButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.STOP_ROUNDED, size=18), btn_cancel_rip_text], spacing=4),
        disabled=True,
    )
    btn_eject_text = ft.Text(t("rip.eject_tray"))
    btn_eject = ft.OutlinedButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.EJECT_OUTLINED, size=18), btn_eject_text], spacing=4),
    )
    btn_next_cd_text = ft.Text(t("rip.next_cd"))
    btn_next_cd = ft.FilledTonalButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.SKIP_NEXT_ROUNDED, size=18), btn_next_cd_text], spacing=4),
    )
    btn_read_toc_text = ft.Text(t("rip.read_toc"))
    btn_read_toc = ft.OutlinedButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.REFRESH_ROUNDED, size=18), btn_read_toc_text], spacing=4),
    )

    async def pick_unprocessed_dir(e):
        selected = await file_picker.get_directory_path(
            dialog_title=t("rip.dialog_target_dir"),
            initial_directory=target_dir_field.value,
        )
        if selected:
            target_dir_field.value = selected
            cfg.set_value("PATHS", "unprocessed_dir", selected)
            cfg.save()
            page.update()

    def do_read_toc(show_snack: bool = True):
        drive = drive_dd.value
        append_rip_log(t("rip.log_checking_drive", drive=drive))
        set_disc_status("status_reading_toc", ft.Colors.BLUE_700)
        page.update()
        try:
            toc = read_cd_toc(drive)
            rip_state["toc"] = toc
            rip_state["last_error"] = None
            total_duration = sum(t_tr["duration_sec"] for t_tr in toc)
            dur_str = format_mm_ss(total_duration)
            rip_state["disc_info_state"] = ("detected", {"count": len(toc), "duration": dur_str})
            disc_info_text.value = t("rip.disc_info_detected", count=len(toc), duration=dur_str)
            set_disc_status("status_ready", ft.Colors.GREEN_700)

            track_table.rows.clear()
            for t_item in toc:
                track_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(f"{t_item['track_num']:02d}")),
                            ft.DataCell(ft.Text(format_mm_ss(t_item['duration_sec']))),
                            ft.DataCell(ft.Text(str(t_item['start_lba']))),
                            ft.DataCell(ft.Text(str(t_item['end_lba']))),
                            create_progress_cell(0.0),
                        ]
                    )
                )
            append_rip_log(t("rip.log_toc_success", count=len(toc), duration=dur_str))
            if show_snack:
                show_notification(t("rip.notify_read_success", count=len(toc), duration=dur_str))
        except Exception as ex:
            rip_state["toc"] = []
            rip_state["last_error"] = str(ex)
            rip_state["disc_info_state"] = ("fail", {"error": str(ex)})
            track_table.rows.clear()
            disc_info_text.value = t("rip.disc_info_fail", error=str(ex))
            set_disc_status("status_no_disc_or_fail", ft.Colors.RED_700)
            append_rip_log(t("rip.log_toc_fail", error=str(ex), drive=drive))
            if show_snack:
                show_notification(t("rip.notify_read_fail", error=str(ex)), is_error=True)
        page.update()

    def do_eject(e=None):
        drive = drive_dd.value
        ok = eject_cd_drive(drive)
        if ok:
            append_rip_log(t("rip.log_ejected", drive=drive))
            show_notification(t("rip.notify_ejected", drive=drive))
        else:
            append_rip_log(t("rip.log_eject_fail", drive=drive))

    def prepare_next_cd(e=None):
        rip_state["cd_count"] += 1
        rip_state["last_error"] = None
        cd_count_text.value = f"CD #{rip_state['cd_count']:02d}"
        current_track_bar.value = 0.0
        current_track_progress_text.value = t("rip.track_progress_idle")
        disc_progress_bar.value = 0.0
        disc_progress_text.value = t("rip.disc_progress_idle")
        track_table.rows.clear()
        rip_state["disc_info_state"] = ("prep", {"count": rip_state['cd_count']})
        disc_info_text.value = t("rip.disc_info_prep", count=rip_state['cd_count'])
        set_disc_status("status_idle", ft.Colors.ON_SURFACE_VARIANT)
        append_rip_log(t("rip.log_switched_cd", count=rip_state['cd_count']))
        page.update()

    def do_cancel_rip(e=None):
        task = rip_state.get("current_task")
        if task:
            task.cancel()
            btn_cancel_rip.disabled = True
            set_disc_status("status_cancelling", ft.Colors.AMBER_800)
            append_rip_log(t("rip.log_cancelling"))
            page.update()

    def start_continuous_rip(e=None):
        if rip_state["is_ripping"]:
            return

        drive = drive_dd.value
        base_dir = Path(target_dir_field.value.strip())
        base_dir.mkdir(parents=True, exist_ok=True)

        try:
            toc = read_cd_toc(drive)
            rip_state["toc"] = toc
            rip_state["last_error"] = None
        except Exception as ex:
            show_notification(t("rip.notify_no_disc_alert", error=str(ex)), is_error=True)
            append_rip_log(t("rip.notify_no_disc_alert", error=str(ex)))
            return

        total_tracks = len(toc)
        folder_name = f"CD_{rip_state['cd_count']:02d}_{total_tracks}tracks"
        target_album_dir = base_dir / folder_name

        rip_state["is_ripping"] = True
        btn_start_rip.disabled = True
        btn_cancel_rip.disabled = False
        btn_read_toc.disabled = True
        btn_next_cd.disabled = True
        drive_dd.disabled = True
        set_disc_status("status_ripping", ft.Colors.BLUE_800)

        track_table.rows.clear()
        for t_item in toc:
            track_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(f"{t_item['track_num']:02d}")),
                        ft.DataCell(ft.Text(format_mm_ss(t_item['duration_sec']))),
                        ft.DataCell(ft.Text(str(t_item['start_lba']))),
                        ft.DataCell(ft.Text(str(t_item['end_lba']))),
                        create_progress_cell(0.0),
                    ]
                )
            )

        append_rip_log(t("rip.log_start_rip", count=rip_state['cd_count'], total=total_tracks))
        append_rip_log(t("rip.log_target_dir", path=str(target_album_dir)))
        page.update()

        def on_track_start_cb(idx, tr_num, total, duration):
            def ui_update():
                if idx < len(track_table.rows):
                    track_table.rows[idx].cells[4] = create_progress_cell(0.01)
                current_track_progress_text.value = t("rip.track_progress_start", current=tr_num, total=total, duration=format_mm_ss(duration))
                current_track_bar.value = 0.0
                disc_progress_text.value = t("rip.disc_progress", current=idx, total=total, percent=(idx/total)*100)
                disc_progress_bar.value = idx / total
            post_ui(ui_update)

        def on_track_progress_cb(idx, tr_num, prog, done_secs, total_secs):
            def ui_update():
                current_track_progress_text.value = t("rip.track_progress_sectors", current=tr_num, total=total_tracks, percent=prog*100, done=done_secs, total_sec=total_secs)
                current_track_bar.value = prog
                overall = (idx + prog) / total_tracks
                disc_progress_text.value = t("rip.disc_progress", current=idx, total=total_tracks, percent=overall*100)
                disc_progress_bar.value = overall
                if idx < len(track_table.rows):
                    track_table.rows[idx].cells[4] = create_progress_cell(prog)
            post_ui(ui_update)

        def on_track_complete_cb(idx, tr_num, out_file):
            def ui_update():
                if idx < len(track_table.rows):
                    track_table.rows[idx].cells[4] = create_progress_cell(1.0)
            post_ui(ui_update)

        def on_all_complete_cb(out_dir, total):
            def ui_update():
                rip_state["is_ripping"] = False
                btn_start_rip.disabled = False
                btn_cancel_rip.disabled = True
                btn_read_toc.disabled = False
                btn_next_cd.disabled = False
                drive_dd.disabled = False
                current_track_bar.value = 1.0
                current_track_progress_text.value = t("rip.track_progress_done")
                disc_progress_bar.value = 1.0
                disc_progress_text.value = t("rip.disc_progress_done", total=total)
                set_disc_status("status_complete", ft.Colors.GREEN_800)

                append_rip_log(t("rip.log_all_complete", count=rip_state['cd_count'], path=str(out_dir)))
                show_notification(t("rip.notify_complete", count=rip_state['cd_count'], total=total))

                if eject_switch.value:
                    eject_cd_drive(drive)
                    append_rip_log(t("rip.log_eject_auto"))

                eject_msg = t("rip.notify_toast_ejected") if eject_switch.value else ""
                send_native_notification(
                    title=t("rip.notify_toast_title"),
                    message=t("rip.notify_toast_message", count=rip_state['cd_count'], total=total, eject_msg=eject_msg)
                )

                rip_state["cd_count"] += 1
                cd_count_text.value = f"CD #{rip_state['cd_count']:02d}"

                if on_rip_completed:
                    on_rip_completed()

            post_ui(ui_update)

        def on_error_cb(err):
            def ui_update():
                rip_state["is_ripping"] = False
                btn_start_rip.disabled = False
                btn_cancel_rip.disabled = True
                btn_read_toc.disabled = False
                btn_next_cd.disabled = False
                drive_dd.disabled = False
                set_disc_status("status_error", ft.Colors.RED_700)
                append_rip_log(t("rip.log_error", error=str(err)))
                show_notification(t("rip.log_error", error=str(err)), is_error=True)
            post_ui(ui_update)

        task = CDRipperTask(
            drive_letter=drive,
            temp_dir=str(target_album_dir),
            on_track_start=on_track_start_cb,
            on_track_progress=on_track_progress_cb,
            on_track_complete=on_track_complete_cb,
            on_all_complete=on_all_complete_cb,
            on_error=on_error_cb,
            on_log=lambda m: post_ui(lambda: append_rip_log(m)),
        )
        rip_state["current_task"] = task
        task.start()

    # Connect button events
    btn_start_rip.on_click = start_continuous_rip
    btn_cancel_rip.on_click = do_cancel_rip
    btn_eject.on_click = do_eject
    btn_next_cd.on_click = prepare_next_cd
    btn_read_toc.on_click = lambda e: do_read_toc(True)

    # Settings change callbacks
    def on_drive_change(e):
        cfg.set_value("CD", "drive_letter", drive_dd.value)
        cfg.save()
        do_read_toc(False)

    def on_eject_switch_change(e):
        cfg.set_value("CD", "eject_after_rip", str(eject_switch.value).lower())
        cfg.save()

    def on_compression_change(e):
        cfg.set_value("CD", "flac_compression_level", compression_field.value)
        cfg.save()

    drive_dd.on_change = on_drive_change
    eject_switch.on_change = on_eject_switch_change
    compression_field.on_change = on_compression_change

    browse_dir_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN_ROUNDED,
        tooltip=t("rip.browse"),
        on_click=pick_unprocessed_dir,
    )

    log_title_text = ft.Text(t("rip.log_title"), size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE_VARIANT)

    # Tab 1 View layout
    tab1_view = ft.Container(
        content=ft.Column(
            [
                # Top Control Panel Card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        drive_dd,
                                        btn_read_toc,
                                        ft.Container(width=12),
                                        cd_batch_label,
                                        cd_count_text,
                                        btn_next_cd,
                                        ft.Container(expand=True),
                                        disc_status_badge,
                                    ],
                                    alignment=ft.MainAxisAlignment.START,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Row(
                                    [
                                        target_dir_field,
                                        browse_dir_btn,
                                        compression_field,
                                        eject_switch,
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=12,
                        ),
                        padding=16,
                    ),
                ),

                # Middle Disc & Track Info Card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(icon=ft.Icons.DISC_FULL_ROUNDED, size=20, color=ft.Colors.PRIMARY),
                                        disc_info_text,
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                track_table_container,
                            ],
                            spacing=8,
                        ),
                        padding=16,
                    ),
                ),

                # Progress & Action Card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Row([current_track_progress_text]),
                                current_track_bar,
                                ft.Container(height=4),
                                ft.Row([disc_progress_text]),
                                disc_progress_bar,
                                ft.Container(height=8),
                                ft.Row(
                                    [
                                        btn_start_rip,
                                        btn_cancel_rip,
                                        btn_eject,
                                    ],
                                    spacing=12,
                                ),
                            ],
                            spacing=4,
                        ),
                        padding=16,
                    ),
                ),

                # Bottom Event Log
                log_title_text,
                log_container,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=16,
        expand=True,
    )

    def retranslate():
        """Updates all UI control texts according to current locale."""
        drive_dd.label = t("rip.drive_letter")
        target_dir_field.label = t("rip.target_dir")
        eject_switch.label = t("rip.eject_switch")
        compression_field.label = t("rip.flac_compression")
        if len(compression_field.options) >= 2:
            compression_field.options[0].text = t("rip.flac_level_5")
            compression_field.options[1].text = t("rip.flac_level_8")
        btn_start_rip_text.value = t("rip.start_rip")
        btn_cancel_rip_text.value = t("rip.cancel_rip")
        btn_eject_text.value = t("rip.eject_tray")
        btn_next_cd_text.value = t("rip.next_cd")
        btn_read_toc_text.value = t("rip.read_toc")
        browse_dir_btn.tooltip = t("rip.browse")
        cd_batch_label.value = t("rip.batch_code")
        log_title_text.value = t("rip.log_title")

        # Table columns
        if len(track_table.columns) >= 5:
            if hasattr(track_table.columns[0].label, "value"):
                track_table.columns[0].label.value = t("rip.table_track")
                track_table.columns[1].label.value = t("rip.table_duration")
                track_table.columns[2].label.value = t("rip.table_start_lba")
                track_table.columns[3].label.value = t("rip.table_end_lba")
                track_table.columns[4].label.value = t("rip.table_status")
            else:
                track_table.columns[0].label = ft.Text(t("rip.table_track"), weight=ft.FontWeight.BOLD)
                track_table.columns[1].label = ft.Text(t("rip.table_duration"), weight=ft.FontWeight.BOLD)
                track_table.columns[2].label = ft.Text(t("rip.table_start_lba"), weight=ft.FontWeight.BOLD)
                track_table.columns[3].label = ft.Text(t("rip.table_end_lba"), weight=ft.FontWeight.BOLD)
                track_table.columns[4].label = ft.Text(t("rip.table_status"), weight=ft.FontWeight.BOLD)

        # Status & Info text
        set_disc_status(rip_state.get("status_key"), rip_state.get("status_color"), rip_state.get("status_fallback"))
        if not rip_state["is_ripping"]:
            current_track_progress_text.value = t("rip.track_progress_idle")
            disc_progress_text.value = t("rip.disc_progress_idle")
            info_kind, info_kwargs = rip_state.get("disc_info_state", ("empty", {}))
            if info_kind == "prompt":
                disc_info_text.value = t("rip.disc_info_prompt")
            elif info_kind == "prep":
                disc_info_text.value = t("rip.disc_info_prep", **info_kwargs)
            elif info_kind == "detected":
                disc_info_text.value = t("rip.disc_info_detected", **info_kwargs)
            elif info_kind == "fail":
                disc_info_text.value = t("rip.disc_info_fail", **info_kwargs)
            else:
                disc_info_text.value = t("rip.disc_info_empty")

        page.update()

    subscribe(retranslate)
    tab1_view.retranslate = retranslate

    def initial_check():
        try:
            toc = read_cd_toc(drive_dd.value)
            rip_state["toc"] = toc
            rip_state["last_error"] = None
            total_duration = sum(t_tr["duration_sec"] for t_tr in toc)
            dur_str = format_mm_ss(total_duration)
            rip_state["disc_info_state"] = ("detected", {"count": len(toc), "duration": dur_str})
            disc_info_text.value = t("rip.disc_info_detected", count=len(toc), duration=dur_str)
            set_disc_status("status_ready", ft.Colors.GREEN_700)
            for t_item in toc:
                track_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(f"{t_item['track_num']:02d}")),
                            ft.DataCell(ft.Text(format_mm_ss(t_item['duration_sec']))),
                            ft.DataCell(ft.Text(str(t_item['start_lba']))),
                            ft.DataCell(ft.Text(str(t_item['end_lba']))),
                            create_progress_cell(0.0),
                        ]
                    )
                )
            append_rip_log(t("rip.log_boot_detected", drive=drive_dd.value, count=len(toc), duration=dur_str))
        except Exception as ex:
            rip_state["disc_info_state"] = ("prompt", {})
            disc_info_text.value = t("rip.disc_info_prompt")
            set_disc_status("status_waiting_no_disc", ft.Colors.ON_SURFACE_VARIANT)
            append_rip_log(t("rip.log_boot_waiting", drive=drive_dd.value, error=str(ex)))

    return tab1_view, initial_check
