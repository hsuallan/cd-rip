import os
import csv
import re
import shutil
from pathlib import Path
import mutagen.flac
from mutagen.flac import Picture
from config import cfg

def sanitize_filename(name: str) -> str:
    """Sanitize string for Windows filename compatibility."""
    invalid_chars = {
        '\\': '＼',
        '/': '／',
        ':': '：',
        '*': '＊',
        '?': '？',
        '"': '＂',
        '<': '＜',
        '>': '＞',
        '|': '｜'
    }
    for char, replacement in invalid_chars.items():
        name = name.replace(char, replacement)
    return name.strip()

class TrackList(list):
    """List of track dicts preserving original CSV column headers order."""
    def __init__(self, items=(), headers=()):
        super().__init__(items)
        self.headers = list(headers)


def parse_csv_metadata(csv_file_or_text: str):
    """
    Parse CSV file or string content into a list of track metadata dicts.
    Supports dynamic CSV formats, foobar2000 remapped metadata fields,
    technical information fields, and canonical tag aliases.
    """
    raw_lines = []
    if os.path.exists(csv_file_or_text):
        with open(csv_file_or_text, mode='r', encoding='utf-8-sig') as f:
            raw_lines = f.readlines()
    else:
        raw_lines = csv_file_or_text.splitlines()

    lines = []
    for l in raw_lines:
        s = l.strip()
        # Ignore empty lines or markdown code block fences (e.g. ```csv or ```)
        if not s or s.startswith("```"):
            continue
        lines.append(s)

    if not lines:
        raise ValueError("CSV 內容為空")

    reader = csv.reader(lines)
    header = next(reader)

    # Keep original column headers as written
    raw_headers = [col.strip() for col in header]

    tracks = TrackList(headers=raw_headers)
    for row in reader:
        if not row:
            continue
        track_dict = {}
        for raw_col, val in zip(raw_headers, row):
            clean_val = val.strip()
            track_dict[raw_col] = clean_val
            norm_col = raw_col.strip('%').strip().lower()
            track_dict[norm_col] = clean_val

        # Canonical foobar2000 metadata field remapping
        # Track number (%tracknumber%, %track number%, %track%)
        track_val = (
            track_dict.get('tracknumber')
            or track_dict.get('track number')
            or track_dict.get('track')
            or ''
        )
        if track_val:
            track_dict['track'] = track_val
            track_dict['tracknumber'] = track_val
            track_dict['track number'] = track_val

        # Album artist (%album artist%, %albumartist%)
        aa_val = (
            track_dict.get('albumartist')
            or track_dict.get('album artist')
            or track_dict.get('album_artist')
            or ''
        )
        if aa_val:
            track_dict['albumartist'] = aa_val
            track_dict['album artist'] = aa_val

        # Track artist / Artist (%track artist%, %artist%)
        ta_val = track_dict.get('track artist') or track_dict.get('trackartist') or ''
        art_val = track_dict.get('artist') or ''
        if ta_val and not art_val:
            track_dict['artist'] = ta_val
        if ta_val:
            track_dict['track artist'] = ta_val
            track_dict['trackartist'] = ta_val
        if art_val:
            track_dict['artist'] = art_val

        # Album (%album%)
        alb_val = track_dict.get('album') or ''
        if alb_val:
            track_dict['album'] = alb_val

        # Title (%title%)
        tit_val = track_dict.get('title') or ''
        if tit_val:
            track_dict['title'] = tit_val

        # Disc number (%discnumber%)
        dn_val = (
            track_dict.get('discnumber')
            or track_dict.get('disc number')
            or track_dict.get('disc')
            or ''
        )
        if dn_val:
            track_dict['discnumber'] = dn_val
            track_dict['disc'] = dn_val

        # Total discs (%totaldiscs%)
        td_val = (
            track_dict.get('totaldiscs')
            or track_dict.get('total discs')
            or track_dict.get('disctotal')
            or ''
        )
        if td_val:
            track_dict['totaldiscs'] = td_val
            track_dict['disctotal'] = td_val

        # Total tracks (%totaltracks%)
        tt_val = (
            track_dict.get('totaltracks')
            or track_dict.get('total tracks')
            or track_dict.get('tracktotal')
            or ''
        )
        if tt_val:
            track_dict['totaltracks'] = tt_val
            track_dict['tracktotal'] = tt_val

        # Year / Date (%year%, %date%)
        yr_val = track_dict.get('year') or track_dict.get('date') or ''
        if yr_val:
            track_dict['year'] = yr_val
            track_dict['date'] = yr_val

        # Genre (%genre%)
        gen_val = track_dict.get('genre') or ''
        if gen_val:
            track_dict['genre'] = gen_val

        # Composer & Lyricist
        comp_val = track_dict.get('composer') or ''
        if comp_val:
            track_dict['composer'] = comp_val
        lyr_val = track_dict.get('lyricist') or ''
        if lyr_val:
            track_dict['lyricist'] = lyr_val

        tracks.append(track_dict)

    return tracks

def find_cover_image(search_dir: Path, target_names: list[str] = None):
    """Find cover image file strictly within search_dir (e.g. album folder)."""
    if target_names is None:
        target_names = cfg.cover_names

    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

    # Search search_dir (e.g. temp_unprocessed/CD_01/)
    for name in target_names:
        for candidate in search_dir.glob(f"{name}.*"):
            if candidate.suffix.lower() in valid_extensions:
                return candidate

    for candidate in search_dir.glob("*.*"):
        if candidate.suffix.lower() in valid_extensions and candidate.name.lower().startswith(('cover', 'folder', 'photo', 'front')):
            return candidate

    return None

def get_image_mime(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in ['.jpg', '.jpeg']:
        return "image/jpeg"
    elif ext == '.png':
        return "image/png"
    elif ext == '.webp':
        return "image/webp"
    elif ext == '.bmp':
        return "image/bmp"
    elif ext == '.gif':
        return "image/gif"
    return "image/jpeg"

def process_cover_to_jpg(source_image_or_path, target_dest_path: Path) -> tuple[bytes, str]:
    """
    Converts any image format (PNG, WebP, GIF, BMP, JPG) to standard high-quality cover.jpg.
    Handles transparency/RGBA cleanly by pasting onto a pure white background.
    Saves to target_dest_path and returns (jpeg_bytes, 'image/jpeg').
    """
    from PIL import Image
    import io

    if isinstance(source_image_or_path, (str, Path)):
        img = Image.open(str(source_image_or_path))
    else:
        img = source_image_or_path

    try:
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            final_img = rgb_img
        elif img.mode != "RGB":
            final_img = img.convert("RGB")
        else:
            final_img = img

        target_dest_path.parent.mkdir(parents=True, exist_ok=True)
        final_img.save(str(target_dest_path), "JPEG", quality=95, optimize=True)

        buf = io.BytesIO()
        final_img.save(buf, "JPEG", quality=95, optimize=True)
        return buf.getvalue(), "image/jpeg"
    finally:
        if isinstance(source_image_or_path, (str, Path)):
            img.close()

def process_and_tag_flacs(
    temp_dir: str = None,
    csv_file_or_text: str = None,
    output_base_dir: str = None,
    move_files: bool = None,
    custom_cover_path: str = None,
    progress_callback = None
):
    """
    Tags FLAC files in temp_dir according to CSV metadata and moves/copies them to output directory.
    Uses defaults from config.ini if parameters are omitted.
    """
    temp_path = Path(temp_dir) if temp_dir else cfg.temp_dir
    output_base_path = Path(output_base_dir) if output_base_dir else cfg.output_dir
    if move_files is None:
        move_files = cfg.move_temp_files

    if not csv_file_or_text:
        raise ValueError("csv_file_or_text is required")

    tracks = parse_csv_metadata(csv_file_or_text)
    total_tracks_count = len(tracks)
    track_total_str = f"{total_tracks_count:02d}"

    if not tracks:
        raise ValueError("No valid track metadata parsed from CSV.")

    first_track = tracks[0]
    album_artist = first_track.get('albumartist') or first_track.get('artist') or 'Unknown Artist'
    album_name = first_track.get('album') or 'Unknown Album'

    # Folder naming convention from config.ini
    folder_name_str = cfg.folder_format.format(
        albumartist=album_artist,
        album=album_name,
        artist=first_track.get('artist', album_artist),
        year=first_track.get('year', '')
    )
    folder_name = sanitize_filename(folder_name_str)
    dest_dir = output_base_path / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Find cover image (checks custom path, temp_dir and project root)
    cover_path = None
    if custom_cover_path == "NONE":
        cover_path = None
        # Truly clear cover: remove any residual cover.jpg in destination directory
        dest_cover_file = dest_dir / "cover.jpg"
        if dest_cover_file.exists():
            try:
                dest_cover_file.unlink()
            except Exception:
                pass
    elif custom_cover_path and Path(custom_cover_path).is_file():
        cover_path = Path(custom_cover_path)
    elif custom_cover_path is None:
        cover_path = find_cover_image(temp_path)

    cover_data = None
    mime_type = "image/jpeg"
    if cover_path:
        try:
            dest_cover_file = dest_dir / "cover.jpg"
            cover_data, mime_type = process_cover_to_jpg(cover_path, dest_cover_file)
        except Exception as e:
            print(f"Warning: Failed to convert cover to cover.jpg: {e}")
            try:
                with open(cover_path, 'rb') as img_f:
                    cover_data = img_f.read()
                mime_type = get_image_mime(cover_path)
                dest_cover_file = dest_dir / "cover.jpg"
                shutil.copy2(str(cover_path), str(dest_cover_file))
            except Exception:
                pass

    # Match FLAC files in temp_dir
    flac_files = sorted(list(temp_path.glob("*.flac")))

    processed_files = []

    for idx, track_info in enumerate(tracks):
        raw_num = (
            track_info.get('track')
            or track_info.get('tracknumber')
            or track_info.get('track number')
        )
        if raw_num and str(raw_num).strip():
            raw_str = str(raw_num).strip()
            if '/' in raw_str:
                raw_str = raw_str.split('/')[0].strip()
            track_num_str = raw_str.zfill(2) if raw_str.isdigit() else raw_str
        else:
            track_num_str = f"{idx + 1:02d}"

        # Find matching FLAC file in temp_dir (skip original reference files if ending in _or.flac)
        matched_file = None
        for f in flac_files:
            if f.name.endswith('_or.flac'):
                continue
            if f.name.startswith(track_num_str):
                matched_file = f
                break

        # Fallback by index if track number prefix matching failed
        if not matched_file and idx < len(flac_files):
            candidate = flac_files[idx]
            if not candidate.name.endswith('_or.flac'):
                matched_file = candidate

        if not matched_file:
            print(f"Warning: No matching FLAC file found for track {track_num_str}")
            if progress_callback:
                try:
                    progress_callback(idx, total_tracks_count, track_num_str, track_info.get('title', ''), None)
                except Exception:
                    pass
            continue

        audio = mutagen.flac.FLAC(matched_file)

        # Clear existing tags
        audio.clear()

        # Set vorbis comments matching original schema and foobar2000 fields
        title = track_info.get('title', '')
        artist = track_info.get('artist', '')
        album = track_info.get('album', '')
        genre = track_info.get('genre', '')
        year = track_info.get('year') or track_info.get('date', '')
        composer = track_info.get('composer', '')
        lyricist = track_info.get('lyricist', '')
        disc_num = track_info.get('discnumber') or track_info.get('disc', '')
        disc_total = track_info.get('totaldiscs') or track_info.get('disctotal', '')
        track_total = track_info.get('totaltracks') or track_info.get('tracktotal') or track_total_str

        if title: audio['title'] = title
        if artist: audio['artist'] = artist
        if album_artist: audio['albumartist'] = album_artist
        if album: audio['album'] = album
        if genre:
            audio['genre'] = genre
            if cfg.write_genere_tag:
                audio['genere'] = genre  # Write 'genere' key if enabled
        if composer: audio['composer'] = composer
        if lyricist: audio['lyricist'] = lyricist
        if year: audio['date'] = str(year)
        if disc_num: audio['discnumber'] = str(disc_num)
        if disc_total: audio['disctotal'] = str(disc_total)
        audio['tracknumber'] = track_num_str
        audio['tracktotal'] = str(track_total)

        # Attach cover picture if available (always clear pictures first)
        audio.clear_pictures()
        if cover_data:
            picture = Picture()
            picture.type = 3  # Cover (front)
            picture.mime = mime_type
            picture.data = cover_data
            audio.add_picture(picture)

        audio.save()

        # Target filename from config format
        new_filename_str = cfg.filename_format.format(
            track=track_num_str,
            title=title,
            artist=artist,
            album=album
        )
        new_filename = sanitize_filename(new_filename_str)
        target_file = dest_dir / new_filename

        if move_files:
            shutil.move(str(matched_file), str(target_file))
        else:
            shutil.copy2(str(matched_file), str(target_file))

        processed_files.append(target_file)
        if progress_callback:
            try:
                progress_callback(idx, total_tracks_count, track_num_str, title, str(target_file))
            except Exception:
                pass

        try:
            print(f"Processed track {track_num_str} -> {target_file}")
        except UnicodeEncodeError:
            print(f"Processed track {track_num_str} -> {target_file.name}".encode('ascii', errors='replace').decode('ascii'))

    return dest_dir, processed_files

