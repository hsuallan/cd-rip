# -*- coding: utf-8 -*-
"""
Tab 2: Batch Archiving Mode (批次歸檔模式)
Dedicated module for multi-album FLAC tagging, cover art embedding, and folder organization.
"""

from pathlib import Path
import threading
from PIL import Image, ImageGrab
import flet as ft

from config import cfg
from i18n import t, subscribe
from tagger import parse_csv_metadata, process_and_tag_flacs, find_cover_image, process_cover_to_jpg
from player import add_to_foobar_or_open, open_album_folder_in_explorer
from ui.common import send_native_notification

CSV_TEMPLATE = """%track%,%title%,%genre%,%artist%,%year%,%album%,%albumartist%,%composer%,%lyricist%
01,Track 01,J-Pop,Artist,2026,Album Name,Album Artist,Composer,Lyricist
02,Track 02,J-Pop,Artist,2026,Album Name,Album Artist,Composer,Lyricist
"""


def build_archive_tab(page: ft.Page, file_picker: ft.FilePicker, show_notification, post_ui):
    """
    Constructs and returns the Batch Archiving tab view, its refresh trigger, and keyboard event handler.
    """
    archive_state = {
        "source_dir": str(cfg.unprocessed_dir),
        "output_dir": str(cfg.output_dir),
        "pending_albums": [],
        "selected_album": None,
        "parsed_tracks": [],
        "custom_cover": None,
        "is_archiving": False,
        "csv_status_state": ("empty", {}),
        "last_archive_result": None,
    }

    # UI Controls
    arch_source_field = ft.TextField(
        label=t("archive.source_dir"),
        value=archive_state["source_dir"],
        expand=True,
        dense=True,
    )

    arch_output_field = ft.TextField(
        label=t("archive.output_dir"),
        value=archive_state["output_dir"],
        expand=True,
        dense=True,
    )

    move_files_switch = ft.Switch(
        label=t("archive.move_files"),
        value=cfg.move_temp_files,
    )

    foobar_switch = ft.Switch(
        label=t("archive.foobar_switch"),
        value=cfg.open_in_foobar,
    )

    # Left Column: Albums ListView
    albums_listview = ft.ListView(
        spacing=8,
        padding=6,
        expand=True,
    )

    queue_title_text = ft.Text(t("archive.queue_title"), size=13, weight=ft.FontWeight.BOLD)
    album_count_badge = ft.Text(t("archive.album_count", count=0), size=12, color=ft.Colors.OUTLINE)

    # Right Column Controls
    selected_title_text = ft.Text(t("archive.no_album_selected_title"), size=18, weight=ft.FontWeight.BOLD)
    selected_sub_text = ft.Text(t("archive.no_album_selected_sub"), size=13, color=ft.Colors.OUTLINE)

    # Multiline CSV Input Field
    csv_text_field = ft.TextField(
        label=t("archive.csv_label"),
        hint_text=t("archive.csv_hint"),
        multiline=True,
        min_lines=6,
        max_lines=9,
        dense=True,
        expand=True,
    )

    csv_status_chip = ft.Container(
        content=ft.Text(t("archive.csv_status_empty"), size=12, color=ft.Colors.OUTLINE),
        padding=ft.Padding(left=8, top=2, right=8, bottom=2),
        border_radius=ft.BorderRadius.all(6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )

    preview_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text(t("archive.preview_no_data"), weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
        heading_row_height=34,
        data_row_min_height=30,
        data_row_max_height=34,
        column_spacing=20,
    )

    preview_table_container = ft.Container(
        content=ft.Column(
            [ft.Row([preview_table], scroll=ft.ScrollMode.AUTO)],
            scroll=ft.ScrollMode.AUTO,
        ),
        height=200,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=ft.BorderRadius.all(8),
        padding=ft.Padding(left=10, top=4, right=10, bottom=4),
    )

    # Cover Preview Elements
    cover_image_view = ft.Image(
        src="",
        width=80,
        height=80,
        fit=ft.BoxFit.COVER,
        border_radius=ft.BorderRadius.all(6),
        visible=False,
    )

    cover_placeholder_text = ft.Text(t("archive.cover_no_cover"), size=11, color=ft.Colors.OUTLINE)
    cover_placeholder_box = ft.Container(
        content=ft.Column(
            [
                ft.Icon(icon=ft.Icons.IMAGE_OUTLINED, size=32, color=ft.Colors.OUTLINE),
                cover_placeholder_text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        ),
        width=80,
        height=80,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=ft.BorderRadius.all(6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        visible=True,
    )

    cover_info_title = ft.Text(t("archive.cover_title"), size=13, weight=ft.FontWeight.W_600)
    cover_info_sub = ft.Text(t("archive.cover_unset"), size=11, color=ft.Colors.OUTLINE)

    # Execution Status & Action
    btn_archive_album_text = ft.Text(t("archive.btn_archive"))
    btn_archive_album = ft.FilledButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.DRIVE_FILE_MOVE_ROUNDED, size=18), btn_archive_album_text], spacing=4),
        disabled=True,
    )

    btn_batch_all_text = ft.Text(t("archive.btn_batch_all"))
    btn_batch_all = ft.OutlinedButton(
        content=ft.Row([ft.Icon(icon=ft.Icons.AUTO_AWESOME_ROUNDED, size=16), btn_batch_all_text], spacing=4),
        disabled=True,
    )

    archive_result_card = ft.Container(
        visible=False,
        padding=12,
        border_radius=ft.BorderRadius.all(8),
        bgcolor=ft.Colors.GREEN_50,
        border=ft.Border.all(1, ft.Colors.GREEN_300),
    )

    async def pick_source_dir(e):
        selected = await file_picker.get_directory_path(
            dialog_title=t("archive.dialog_source"),
            initial_directory=arch_source_field.value,
        )
        if selected:
            arch_source_field.value = selected
            archive_state["source_dir"] = selected
            refresh_pending_albums()

    async def pick_output_dir(e):
        selected = await file_picker.get_directory_path(
            dialog_title=t("archive.dialog_output"),
            initial_directory=arch_output_field.value,
        )
        if selected:
            arch_output_field.value = selected
            archive_state["output_dir"] = selected
            cfg.set_value("PATHS", "output_dir", selected)
            cfg.save()
            page.update()

    def set_album_cover(cover_path_str: str):
        """Applies cover to currently selected album."""
        selected = archive_state["selected_album"]
        if not selected:
            return

        if cover_path_str == "NONE" or not cover_path_str:
            selected["custom_cover"] = "NONE" if cover_path_str == "NONE" else None
            archive_state["custom_cover"] = selected["custom_cover"]
            cover_image_view.src = ""
            cover_image_view.visible = False
            cover_placeholder_box.visible = True
            cover_info_sub.value = t("archive.cover_cleared") if cover_path_str == "NONE" else t("archive.cover_unset")
            cover_info_sub.color = ft.Colors.OUTLINE
        elif Path(cover_path_str).is_file():
            selected["custom_cover"] = cover_path_str
            archive_state["custom_cover"] = cover_path_str
            cover_image_view.src = cover_path_str
            cover_image_view.visible = True
            cover_placeholder_box.visible = False
            cover_info_sub.value = t("archive.cover_set", name=Path(cover_path_str).name)
            cover_info_sub.color = ft.Colors.GREEN_800
        else:
            selected["custom_cover"] = None
            archive_state["custom_cover"] = None
            cover_image_view.src = ""
            cover_image_view.visible = False
            cover_placeholder_box.visible = True
            cover_info_sub.value = t("archive.cover_unset")
            cover_info_sub.color = ft.Colors.OUTLINE

        page.update()

    async def pick_custom_cover(e):
        files = await file_picker.pick_files(
            dialog_title=t("archive.dialog_cover"),
            file_type=ft.FilePickerFileType.IMAGE,
            allow_multiple=False,
        )
        if files and len(files) > 0:
            img_path = files[0].path
            set_album_cover(img_path)
            show_notification(t("archive.notify_cover_selected", name=Path(img_path).name))

    def paste_clipboard_cover(e=None):
        """Pastes image from Windows clipboard as cover."""
        selected = archive_state["selected_album"]
        if not selected:
            show_notification(t("archive.notify_select_album_first"), is_error=True)
            return

        try:
            clip = ImageGrab.grabclipboard()
            if clip is None:
                show_notification(t("archive.notify_clipboard_no_image"), is_error=True)
                return

            if isinstance(clip, list) and clip:
                candidate = Path(clip[0])
                if candidate.is_file() and candidate.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"]:
                    set_album_cover(str(candidate))
                    show_notification(t("archive.notify_clipboard_file_set", name=candidate.name))
                    return
                else:
                    show_notification(t("archive.notify_clipboard_not_supported"), is_error=True)
                    return

            if isinstance(clip, Image.Image):
                target_album_folder = selected["path"]
                saved_path = target_album_folder / "cover.jpg"
                process_cover_to_jpg(clip, saved_path)
                set_album_cover(str(saved_path))
                show_notification(t("archive.notify_clipboard_saved"))
                return

            show_notification(t("archive.notify_clipboard_invalid"), is_error=True)
        except Exception as ex:
            show_notification(t("archive.notify_clipboard_error", error=str(ex)), is_error=True)

    def clear_cover(e=None):
        selected = archive_state["selected_album"]
        if selected:
            folder = selected["path"]
            img_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
            try:
                for f in folder.glob("*.*"):
                    if f.suffix.lower() in img_exts:
                        try:
                            f.unlink()
                        except Exception:
                            pass
            except Exception:
                pass
            set_album_cover("NONE")
            show_notification(t("archive.notify_cover_cleared"))
        else:
            set_album_cover("NONE")

    def parse_and_update_preview(csv_text: str):
        selected_album = archive_state["selected_album"]
        if not csv_text.strip():
            archive_state["parsed_tracks"] = []
            archive_state["csv_status_state"] = ("empty", {})
            preview_table.columns = [ft.DataColumn(ft.Text(t("archive.preview_no_data")))]
            preview_table.rows.clear()
            csv_status_chip.content = ft.Text(t("archive.csv_status_empty"), size=12, color=ft.Colors.OUTLINE)
            csv_status_chip.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGHEST
            btn_archive_album.disabled = True
            if selected_album and selected_album.get("status") not in ["archived", "archived_kept"]:
                selected_album["status"] = "pending"
            refresh_album_list_ui()
            page.update()
            return

        try:
            tracks = parse_csv_metadata(csv_text)
            archive_state["parsed_tracks"] = tracks

            # Dynamic column generation matching the CSV format
            csv_cols = getattr(tracks, 'headers', [])
            if not csv_cols and tracks:
                csv_cols = list(tracks[0].keys())

            preview_table.columns = [
                ft.DataColumn(ft.Text(col, weight=ft.FontWeight.BOLD))
                for col in csv_cols
            ]

            preview_table.rows.clear()
            for tr in tracks:
                cells = []
                for col in csv_cols:
                    val = tr.get(col)
                    if val is None:
                        val = tr.get(col.strip('%').strip().lower(), "")
                    cells.append(
                        ft.DataCell(
                            ft.Text(str(val), size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
                        )
                    )
                preview_table.rows.append(ft.DataRow(cells=cells))

            flac_count = len(selected_album.get("flac_files", [])) if selected_album else 0

            if flac_count > 0 and len(tracks) != flac_count:
                archive_state["csv_status_state"] = ("mismatch", {"tracks": len(tracks), "flacs": flac_count})
                csv_status_chip.content = ft.Text(t("archive.csv_status_mismatch", tracks=len(tracks), flacs=flac_count), size=12, color=ft.Colors.AMBER_900)
                csv_status_chip.bgcolor = ft.Colors.AMBER_100
            else:
                archive_state["csv_status_state"] = ("success", {"tracks": len(tracks), "cols": len(csv_cols)})
                csv_status_chip.content = ft.Text(t("archive.csv_status_success", tracks=len(tracks), cols=len(csv_cols)), size=12, color=ft.Colors.GREEN_800)
                csv_status_chip.bgcolor = ft.Colors.GREEN_100

            btn_archive_album.disabled = False
            if selected_album and selected_album.get("status") not in ["archived", "archived_kept"]:
                selected_album["status"] = "ready"
                selected_album["csv_text"] = csv_text
            refresh_album_list_ui()
        except Exception as ex:
            archive_state["parsed_tracks"] = []
            archive_state["csv_status_state"] = ("error", {"error": str(ex)})
            preview_table.columns = [ft.DataColumn(ft.Text(t("archive.preview_error")))]
            preview_table.rows.clear()
            csv_status_chip.content = ft.Text(t("archive.csv_status_error", error=str(ex)), size=12, color=ft.Colors.RED_800)
            csv_status_chip.bgcolor = ft.Colors.RED_100
            btn_archive_album.disabled = True
            if selected_album and selected_album.get("status") not in ["archived", "archived_kept"]:
                selected_album["status"] = "pending"
            refresh_album_list_ui()
        page.update()

    def on_csv_text_change(e):
        selected = archive_state["selected_album"]
        if selected:
            selected["csv_text"] = csv_text_field.value
        parse_and_update_preview(csv_text_field.value)

    csv_text_field.on_change = on_csv_text_change

    def insert_template_csv(e=None):
        """Inserts clean in-memory CSV template with standard headers."""
        csv_text_field.value = CSV_TEMPLATE
        if archive_state["selected_album"]:
            archive_state["selected_album"]["csv_text"] = CSV_TEMPLATE
        parse_and_update_preview(CSV_TEMPLATE)
        show_notification(t("archive.notify_template_filled"))

    async def load_csv_file(e=None):
        files = await file_picker.pick_files(
            dialog_title=t("archive.dialog_csv"),
            allowed_extensions=["csv", "txt"],
            allow_multiple=False,
        )
        if files and len(files) > 0:
            try:
                with open(files[0].path, "r", encoding="utf-8-sig") as f:
                    content = f.read()
                csv_text_field.value = content
                if archive_state["selected_album"]:
                    archive_state["selected_album"]["csv_text"] = content
                parse_and_update_preview(content)
                show_notification(t("archive.notify_csv_loaded", name=files[0].name))
            except Exception as ex:
                show_notification(t("archive.notify_csv_load_fail", error=str(ex)), is_error=True)

    def clear_csv_text(e=None):
        csv_text_field.value = ""
        if archive_state["selected_album"]:
            archive_state["selected_album"]["csv_text"] = ""
        parse_and_update_preview("")

    def select_album(album_info: dict):
        current_selected = archive_state["selected_album"]
        if current_selected and current_selected != album_info:
            current_selected["csv_text"] = csv_text_field.value
            current_selected["custom_cover"] = archive_state.get("custom_cover")

        archive_state["selected_album"] = album_info
        archive_result_card.visible = False
        archive_state["last_archive_result"] = None

        folder = album_info["path"]
        flac_files = album_info["flac_files"]

        album_title_name = f"{folder.name}{t('archive.root_dir_suffix')}" if album_info.get("is_root") else folder.name
        selected_title_text.value = t("archive.selected_title", name=album_title_name)
        selected_sub_text.value = t("archive.selected_sub", path=str(folder), count=len(flac_files))

        csv_text = album_info.get("csv_text")
        if csv_text is None:
            csv_file = album_info.get("csv_file")
            if csv_file and csv_file.exists():
                try:
                    with open(csv_file, "r", encoding="utf-8-sig") as f:
                        csv_text = f.read()
                except Exception:
                    csv_text = ""
            else:
                csv_text = ""
            album_info["csv_text"] = csv_text

        csv_text_field.value = csv_text
        parse_and_update_preview(csv_text)

        cover_path = album_info.get("custom_cover")
        if not cover_path:
            detected_cover = find_cover_image(folder)
            if detected_cover and detected_cover.exists():
                cover_path = str(detected_cover)
                album_info["custom_cover"] = cover_path

        set_album_cover(cover_path)
        refresh_album_list_ui()
        page.update()

    def refresh_pending_albums(e=None):
        src = Path(arch_source_field.value.strip())
        old_albums_map = {str(a["path"]): a for a in archive_state["pending_albums"]}
        albums = []

        if src.exists() and src.is_dir():
            subdirs = sorted([d for d in src.iterdir() if d.is_dir()])
            for d in subdirs:
                flacs = sorted(list(d.glob("*.flac")))
                if flacs:
                    csvs = list(d.glob("*.csv"))
                    prev = old_albums_map.get(str(d))
                    csv_txt = prev["csv_text"] if prev else None
                    custom_c = prev["custom_cover"] if prev else None
                    st = prev["status"] if prev else ("ready" if csvs else "pending")

                    albums.append({
                        "path": d,
                        "name": d.name,
                        "is_root": False,
                        "flac_files": flacs,
                        "csv_file": csvs[0] if csvs else None,
                        "csv_text": csv_txt,
                        "custom_cover": custom_c,
                        "status": st,
                    })

            # Check root if source directly contains FLAC files
            root_flacs = sorted(list(src.glob("*.flac")))
            if root_flacs and not albums:
                csvs = list(src.glob("*.csv"))
                prev = old_albums_map.get(str(src))
                csv_txt = prev["csv_text"] if prev else None
                custom_c = prev["custom_cover"] if prev else None
                st = prev["status"] if prev else ("ready" if csvs else "pending")

                albums.append({
                    "path": src,
                    "name": src.name,
                    "is_root": True,
                    "flac_files": root_flacs,
                    "csv_file": csvs[0] if csvs else None,
                    "csv_text": csv_txt,
                    "custom_cover": custom_c,
                    "status": st,
                })

        archive_state["pending_albums"] = albums
        album_count_badge.value = t("archive.album_count", count=len(albums))
        btn_batch_all.disabled = len(albums) == 0

        if albums:
            if not archive_state["selected_album"] or archive_state["selected_album"]["path"] not in [a["path"] for a in albums]:
                select_album(albums[0])
        else:
            archive_state["selected_album"] = None
            selected_title_text.value = t("archive.not_found_title")
            selected_sub_text.value = t("archive.not_found_sub", dir=str(src))
            csv_text_field.value = ""
            set_album_cover(None)
            btn_archive_album.disabled = True

        refresh_album_list_ui()
        page.update()

    def refresh_album_list_ui():
        albums_listview.controls.clear()
        for alb in archive_state["pending_albums"]:
            is_selected = archive_state["selected_album"] and archive_state["selected_album"]["path"] == alb["path"]
            status = alb.get("status", "pending")

            if status == "archived":
                badge_color = ft.Colors.PURPLE_100
                text_color = ft.Colors.PURPLE_800
                status_lbl = t("archive.status_archived")
            elif status == "archived_kept":
                badge_color = ft.Colors.PURPLE_100
                text_color = ft.Colors.PURPLE_800
                status_lbl = t("archive.status_archived_kept")
            elif alb.get("csv_text") or alb.get("csv_file"):
                badge_color = ft.Colors.GREEN_100
                text_color = ft.Colors.GREEN_800
                status_lbl = t("archive.status_ready")
            else:
                badge_color = ft.Colors.AMBER_100
                text_color = ft.Colors.AMBER_800
                status_lbl = t("archive.status_pending")

            alb_closure = alb
            display_name = f"{alb['name']}{t('archive.root_dir_suffix')}" if alb.get("is_root") else alb["name"]
            card = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            icon=ft.Icons.FOLDER_ROUNDED,
                            color=ft.Colors.PRIMARY if is_selected else ft.Colors.OUTLINE,
                            size=22,
                        ),
                        ft.Column(
                            [
                                ft.Text(display_name, size=12, weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(t("archive.track_count_sub", count=len(alb['flac_files'])), size=10, color=ft.Colors.OUTLINE),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Container(
                            content=ft.Text(status_lbl, size=9, color=text_color, weight=ft.FontWeight.BOLD),
                            bgcolor=badge_color,
                            padding=ft.Padding(left=5, top=2, right=5, bottom=2),
                            border_radius=ft.BorderRadius.all(4),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                bgcolor=ft.Colors.SECONDARY_CONTAINER if is_selected else ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=ft.BorderRadius.all(8),
                padding=8,
                on_click=lambda e, a=alb_closure: select_album(a),
            )
            albums_listview.controls.append(card)

    def render_archive_result(dest_dir: Path, files_count: int):
        archive_result_card.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(icon=ft.Icons.CHECK_CIRCLE_ROUNDED, color=ft.Colors.GREEN_700, size=24),
                        ft.Text(t("archive.result_success", count=files_count), weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_900),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(t("archive.result_save_to", dir=str(dest_dir)), size=12, color=ft.Colors.GREEN_800),
                ft.Row(
                    [
                        ft.FilledTonalButton(
                            content=ft.Row([ft.Icon(icon=ft.Icons.FOLDER_OPEN_ROUNDED, size=16), ft.Text(t("archive.btn_open_folder"))], spacing=4),
                            on_click=lambda e: open_album_folder_in_explorer(dest_dir),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row([ft.Icon(icon=ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, size=16), ft.Text(t("archive.btn_play_foobar"))], spacing=4),
                            on_click=lambda e: add_to_foobar_or_open(dest_dir),
                        ),
                    ],
                    spacing=8,
                ),
            ],
            spacing=6,
        )
        archive_result_card.visible = True

    def do_archive_selected(e=None):
        selected = archive_state["selected_album"]
        csv_text = csv_text_field.value.strip()

        if not selected:
            show_notification(t("archive.notify_select_album_archive"), is_error=True)
            return
        if not csv_text:
            show_notification(t("archive.notify_enter_csv_first"), is_error=True)
            return

        btn_archive_album.disabled = True
        btn_batch_all.disabled = True
        archive_state["is_archiving"] = True

        album_folder = selected["path"]
        out_base = Path(arch_output_field.value.strip())
        move_flg = move_files_switch.value
        cover_path = archive_state["custom_cover"]

        def run_archive_thread():
            try:
                dest_dir, files = process_and_tag_flacs(
                    temp_dir=str(album_folder),
                    csv_file_or_text=csv_text,
                    output_base_dir=str(out_base),
                    move_files=move_flg,
                    custom_cover_path=cover_path,
                )

                if foobar_switch.value:
                    add_to_foobar_or_open(dest_dir)

                def on_success():
                    archive_state["is_archiving"] = False
                    btn_archive_album.disabled = False
                    btn_batch_all.disabled = False

                    if not move_flg:
                        selected["status"] = "archived_kept"
                    else:
                        selected["status"] = "archived"

                    archive_state["last_archive_result"] = (dest_dir, len(files))
                    render_archive_result(dest_dir, len(files))

                    mode_msg = t("archive.mode_kept") if not move_flg else t("archive.mode_moved")
                    show_notification(t("archive.notify_archive_done", name=dest_dir.name, mode=mode_msg))
                    send_native_notification(
                        title=t("archive.toast_title"),
                        message=t("archive.toast_message", name=dest_dir.name, count=len(files), mode=mode_msg),
                    )
                    refresh_pending_albums()

                post_ui(on_success)

            except Exception as ex:
                def on_fail():
                    archive_state["is_archiving"] = False
                    btn_archive_album.disabled = False
                    btn_batch_all.disabled = False
                    show_notification(t("archive.notify_archive_fail", error=str(ex)), is_error=True)
                post_ui(on_fail)

        threading.Thread(target=run_archive_thread, daemon=True).start()

    def do_batch_archive_all(e=None):
        current_selected = archive_state["selected_album"]
        if current_selected:
            current_selected["csv_text"] = csv_text_field.value
            current_selected["custom_cover"] = archive_state.get("custom_cover")

        ready_albums = []
        for alb in archive_state["pending_albums"]:
            if alb.get("status") in ["archived", "archived_kept"]:
                continue
            c_text = alb.get("csv_text")
            if not c_text and alb.get("csv_file"):
                try:
                    with open(alb["csv_file"], "r", encoding="utf-8-sig") as f:
                        c_text = f.read()
                    alb["csv_text"] = c_text
                except Exception:
                    pass
            if c_text and c_text.strip():
                ready_albums.append(alb)

        if not ready_albums:
            show_notification(t("archive.notify_batch_fill_first"), is_error=True)
            return

        show_notification(t("archive.notify_batch_starting", count=len(ready_albums)))
        btn_batch_all.disabled = True
        btn_archive_album.disabled = True

        out_base = Path(arch_output_field.value.strip())
        move_flg = move_files_switch.value

        def run_batch_thread():
            success_count = 0
            for alb in ready_albums:
                c_text = alb.get("csv_text", "").strip()
                if not c_text:
                    continue
                try:
                    dest_dir, _ = process_and_tag_flacs(
                        temp_dir=str(alb["path"]),
                        csv_file_or_text=c_text,
                        output_base_dir=str(out_base),
                        move_files=move_flg,
                        custom_cover_path=alb.get("custom_cover"),
                    )
                    alb["status"] = "archived_kept" if not move_flg else "archived"
                    success_count += 1
                    if foobar_switch.value:
                        add_to_foobar_or_open(dest_dir)
                except Exception as err:
                    print(f"Batch archive error on {alb['name']}: {err}")

            def on_batch_done():
                btn_batch_all.disabled = False
                btn_archive_album.disabled = False
                mode_msg = t("archive.mode_kept") if not move_flg else t("archive.mode_moved")
                show_notification(t("archive.notify_batch_done", count=success_count, total=len(ready_albums), mode=mode_msg))
                send_native_notification(
                    title=t("archive.toast_batch_title"),
                    message=t("archive.toast_batch_message", count=success_count, total=len(ready_albums), mode=mode_msg),
                )
                refresh_pending_albums()

            post_ui(on_batch_done)

        threading.Thread(target=run_batch_thread, daemon=True).start()

    btn_archive_album.on_click = do_archive_selected
    btn_batch_all.on_click = do_batch_archive_all

    # Settings change callbacks
    def on_move_files_change(e):
        cfg.set_value("BEHAVIOR", "move_temp_files", str(move_files_switch.value).lower())
        cfg.save()

    def on_foobar_switch_change(e):
        cfg.set_value("BEHAVIOR", "open_in_foobar", str(foobar_switch.value).lower())
        cfg.save()

    move_files_switch.on_change = on_move_files_change
    foobar_switch.on_change = on_foobar_switch_change

    def on_keyboard_event(e: ft.KeyboardEvent):
        if getattr(e, "ctrl", False) and str(getattr(e, "key", "") or "").upper() == "V":
            try:
                clip = ImageGrab.grabclipboard()
                if clip is not None:
                    if isinstance(clip, Image.Image) or (isinstance(clip, list) and clip):
                        paste_clipboard_cover()
            except Exception:
                pass

    browse_source_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN_ROUNDED,
        tooltip=t("archive.browse_source"),
        on_click=pick_source_dir,
    )
    rescan_btn = ft.IconButton(
        icon=ft.Icons.REFRESH_ROUNDED,
        tooltip=t("archive.rescan"),
        on_click=refresh_pending_albums,
    )
    browse_output_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN_ROUNDED,
        tooltip=t("archive.browse_output"),
        on_click=pick_output_dir,
    )

    csv_title_text = ft.Text(t("archive.csv_title"), size=14, weight=ft.FontWeight.BOLD)
    btn_load_csv_text = ft.Text(t("archive.btn_load_csv"))
    btn_template_csv_text = ft.Text(t("archive.btn_template_csv"))
    btn_clear_csv_text = ft.Text(t("archive.btn_clear_csv"))

    btn_pick_cover_text = ft.Text(t("archive.btn_pick_cover"))
    btn_paste_cover_text = ft.Text(t("archive.btn_paste_cover"))
    btn_clear_cover_text = ft.Text(t("archive.btn_clear_cover"), size=12)

    preview_title_text = ft.Text(t("archive.preview_title"), size=12, color=ft.Colors.OUTLINE)

    # Tab 2 Layout assembly
    tab2_view = ft.Container(
        content=ft.Column(
            [
                # Top Settings Card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        arch_source_field,
                                        browse_source_btn,
                                        rescan_btn,
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Row(
                                    [
                                        arch_output_field,
                                        browse_output_btn,
                                        move_files_switch,
                                        foobar_switch,
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=8,
                        ),
                        padding=14,
                    ),
                ),

                # Split Main Area: Left (Queue) + Right (Editor)
                ft.Row(
                    [
                        # Left Panel: Albums Queue
                        ft.Card(
                            content=ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Row(
                                            [
                                                queue_title_text,
                                                album_count_badge,
                                            ],
                                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        ),
                                        albums_listview,
                                        btn_batch_all,
                                    ],
                                    spacing=8,
                                    expand=True,
                                ),
                                padding=10,
                                width=260,
                            ),
                        ),

                        # Right Panel: Active Album Workbench
                        ft.Card(
                            content=ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Row(
                                            [
                                                ft.Column(
                                                    [
                                                        selected_title_text,
                                                        selected_sub_text,
                                                    ],
                                                    spacing=2,
                                                    expand=True,
                                                ),
                                                btn_archive_album,
                                            ],
                                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        ft.Divider(height=1),

                                        # CSV Section
                                        ft.Row(
                                            [
                                                csv_title_text,
                                                csv_status_chip,
                                                ft.Container(expand=True),
                                                ft.TextButton(
                                                    content=ft.Row([ft.Icon(icon=ft.Icons.FILE_OPEN_ROUNDED, size=15), btn_load_csv_text], spacing=4),
                                                    on_click=load_csv_file,
                                                ),
                                                ft.TextButton(
                                                    content=ft.Row([ft.Icon(icon=ft.Icons.DATA_OBJECT_ROUNDED, size=15), btn_template_csv_text], spacing=4),
                                                    on_click=insert_template_csv,
                                                ),
                                                ft.TextButton(
                                                    content=ft.Row([ft.Icon(icon=ft.Icons.CLEAR_ALL_ROUNDED, size=15), btn_clear_csv_text], spacing=4),
                                                    on_click=clear_csv_text,
                                                ),
                                            ],
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        csv_text_field,

                                        # Cover Art Section
                                        ft.Container(
                                            content=ft.Row(
                                                [
                                                    ft.Stack([
                                                        cover_placeholder_box,
                                                        cover_image_view,
                                                    ]),
                                                    ft.Column(
                                                        [
                                                            cover_info_title,
                                                            cover_info_sub,
                                                            ft.Row(
                                                                [
                                                                    ft.OutlinedButton(
                                                                        content=ft.Row([ft.Icon(icon=ft.Icons.IMAGE_ROUNDED, size=15), btn_pick_cover_text], spacing=4),
                                                                        on_click=pick_custom_cover,
                                                                    ),
                                                                    ft.FilledTonalButton(
                                                                        content=ft.Row([ft.Icon(icon=ft.Icons.CONTENT_PASTE_ROUNDED, size=15), btn_paste_cover_text], spacing=4),
                                                                        on_click=paste_clipboard_cover,
                                                                    ),
                                                                    ft.TextButton(
                                                                        content=btn_clear_cover_text,
                                                                        on_click=clear_cover,
                                                                    ),
                                                                ],
                                                                spacing=8,
                                                            ),
                                                        ],
                                                        spacing=3,
                                                        expand=True,
                                                    ),
                                                ],
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            padding=12,
                                            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                                            border_radius=ft.BorderRadius.all(8),
                                            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                                        ),

                                        # Real-time parsed preview
                                        preview_title_text,
                                        preview_table_container,

                                        # Result Notification Card
                                        archive_result_card,
                                    ],
                                    spacing=8,
                                    scroll=ft.ScrollMode.AUTO,
                                ),
                                padding=16,
                            ),
                            expand=True,
                        ),
                    ],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ],
            spacing=10,
            expand=True,
        ),
        padding=16,
        expand=True,
    )

    def retranslate():
        """Updates all UI labels according to current active locale."""
        arch_source_field.label = t("archive.source_dir")
        arch_output_field.label = t("archive.output_dir")
        move_files_switch.label = t("archive.move_files")
        foobar_switch.label = t("archive.foobar_switch")
        browse_source_btn.tooltip = t("archive.browse_source")
        rescan_btn.tooltip = t("archive.rescan")
        browse_output_btn.tooltip = t("archive.browse_output")

        queue_title_text.value = t("archive.queue_title")
        album_count_badge.value = t("archive.album_count", count=len(archive_state["pending_albums"]))
        btn_batch_all_text.value = t("archive.btn_batch_all")
        btn_archive_album_text.value = t("archive.btn_archive")

        csv_title_text.value = t("archive.csv_title")
        btn_load_csv_text.value = t("archive.btn_load_csv")
        btn_template_csv_text.value = t("archive.btn_template_csv")
        btn_clear_csv_text.value = t("archive.btn_clear_csv")
        csv_text_field.label = t("archive.csv_label")
        csv_text_field.hint_text = t("archive.csv_hint")

        cover_placeholder_text.value = t("archive.cover_no_cover")
        cover_info_title.value = t("archive.cover_title")
        btn_pick_cover_text.value = t("archive.btn_pick_cover")
        btn_paste_cover_text.value = t("archive.btn_paste_cover")
        btn_clear_cover_text.value = t("archive.btn_clear_cover")

        preview_title_text.value = t("archive.preview_title")
        if not archive_state["parsed_tracks"]:
            status_kind, _ = archive_state.get("csv_status_state", ("empty", {}))
            if status_kind == "error":
                preview_table.columns = [ft.DataColumn(ft.Text(t("archive.preview_error"), weight=ft.FontWeight.BOLD))]
            else:
                preview_table.columns = [ft.DataColumn(ft.Text(t("archive.preview_no_data"), weight=ft.FontWeight.BOLD))]

        # Update selected album text
        selected = archive_state["selected_album"]
        if selected:
            folder = selected["path"]
            flac_files = selected["flac_files"]
            album_title_name = f"{folder.name}{t('archive.root_dir_suffix')}" if selected.get("is_root") else folder.name
            selected_title_text.value = t("archive.selected_title", name=album_title_name)
            selected_sub_text.value = t("archive.selected_sub", path=str(folder), count=len(flac_files))
            cover_path = archive_state.get("custom_cover")
            if cover_path == "NONE":
                cover_info_sub.value = t("archive.cover_cleared")
            elif cover_path and Path(cover_path).is_file():
                cover_info_sub.value = t("archive.cover_set", name=Path(cover_path).name)
            else:
                cover_info_sub.value = t("archive.cover_unset")
        elif not archive_state["pending_albums"]:
            selected_title_text.value = t("archive.not_found_title")
            selected_sub_text.value = t("archive.not_found_sub", dir=str(Path(arch_source_field.value.strip())))
            cover_info_sub.value = t("archive.cover_unset")
        else:
            selected_title_text.value = t("archive.no_album_selected_title")
            selected_sub_text.value = t("archive.no_album_selected_sub")
            cover_info_sub.value = t("archive.cover_unset")

        # Update CSV status chip text
        status_kind, status_kwargs = archive_state.get("csv_status_state", ("empty", {}))
        if status_kind == "empty":
            csv_status_chip.content = ft.Text(t("archive.csv_status_empty"), size=12, color=ft.Colors.OUTLINE)
        elif status_kind == "mismatch":
            csv_status_chip.content = ft.Text(t("archive.csv_status_mismatch", **status_kwargs), size=12, color=ft.Colors.AMBER_900)
        elif status_kind == "success":
            csv_status_chip.content = ft.Text(t("archive.csv_status_success", **status_kwargs), size=12, color=ft.Colors.GREEN_800)
        elif status_kind == "error":
            csv_status_chip.content = ft.Text(t("archive.csv_status_error", **status_kwargs), size=12, color=ft.Colors.RED_800)

        # Update archive result card if visible
        if archive_result_card.visible and archive_state.get("last_archive_result"):
            res_dest, res_count = archive_state["last_archive_result"]
            render_archive_result(res_dest, res_count)

        refresh_album_list_ui()
        page.update()

    subscribe(retranslate)
    tab2_view.retranslate = retranslate

    return tab2_view, refresh_pending_albums, on_keyboard_event
