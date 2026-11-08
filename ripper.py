import ctypes
import threading
from pathlib import Path
import numpy as np
import soundfile as sf
import win32file
import win32con
from config import cfg

IOCTL_CDROM_READ_TOC = 0x00024000
IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x0004D014

class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
    _fields_ = [
        ('Length', ctypes.c_ushort),
        ('ScsiStatus', ctypes.c_ubyte),
        ('PathId', ctypes.c_ubyte),
        ('TargetId', ctypes.c_ubyte),
        ('Lun', ctypes.c_ubyte),
        ('CdbLength', ctypes.c_ubyte),
        ('SenseInfoLength', ctypes.c_ubyte),
        ('DataIn', ctypes.c_ubyte),
        ('DataTransferLength', ctypes.c_ulong),
        ('TimeOutValue', ctypes.c_ulong),
        ('DataBuffer', ctypes.c_void_p),
        ('SenseInfoOffset', ctypes.c_ulong),
        ('Cdb', ctypes.c_ubyte * 16)
    ]

def eject_cd_drive(drive_letter: str = None):
    """Eject CD drive tray using Windows MCI API."""
    if drive_letter is None:
        drive_letter = cfg.drive_letter
    drive_clean = drive_letter.strip().rstrip('\\').rstrip('/')
    try:
        mci = ctypes.windll.winmm.mciSendStringW
        mci(f"open {drive_clean} type cdaudio alias cd_drive", None, 0, None)
        mci("set cd_drive door open", None, 0, None)
        mci("close cd_drive", None, 0, None)
        print(f"[Ripper] Ejected CD drive tray ({drive_clean})")
        return True
    except Exception as e:
        print(f"[Ripper Warning] Failed to eject CD tray: {e}")
        return False

def get_cd_drive_handle(drive_letter: str):
    """Open Win32 handle for optical drive (e.g. 'G:' -> '\\\\.\\G:')."""
    drive_clean = drive_letter.strip().rstrip('\\').rstrip('/')
    prefix = "\\\\.\\"
    if not drive_clean.startswith(prefix):
        drive_clean = prefix + drive_clean
    
    handle = win32file.CreateFile(
        drive_clean,
        win32con.GENERIC_READ | win32con.GENERIC_WRITE,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
        None,
        win32con.OPEN_EXISTING,
        0, 0
    )
    return handle

def read_cd_toc(drive_letter: str = None) -> list[dict]:
    """
    Reads Table of Contents (TOC) from optical disc.
    Returns list of dicts with track info: track_num, start_lba, end_lba, total_sectors, duration_sec.
    """
    if drive_letter is None:
        drive_letter = cfg.drive_letter

    h = get_cd_drive_handle(drive_letter)
    try:
        buf = win32file.DeviceIoControl(h, IOCTL_CDROM_READ_TOC, None, 804, None)
        first_track = buf[2]
        last_track = buf[3]

        tracks_raw = []
        for i in range(last_track - first_track + 2):
            offset = 4 + i * 8
            tr_num = buf[offset + 2]
            # MSF format address to LBA calculation
            m, s, f = buf[offset + 5], buf[offset + 6], buf[offset + 7]
            lba = (m * 60 + s) * 75 + f - 150
            tracks_raw.append((tr_num, lba))

        tracks = []
        for idx in range(len(tracks_raw) - 1):
            tr_num, start_lba = tracks_raw[idx]
            _, end_lba = tracks_raw[idx + 1]
            total_sec = end_lba - start_lba
            tracks.append({
                "track_num": tr_num,
                "start_lba": start_lba,
                "end_lba": end_lba,
                "total_sectors": total_sec,
                "duration_sec": round(total_sec / 75.0, 2)
            })

        return tracks
    finally:
        win32file.CloseHandle(h)

def rip_single_track(handle, start_lba: int, end_lba: int, output_flac_path: str, progress_fn=None, cancel_event=None):
    """
    Rips audio sectors from start_lba to end_lba via SCSI MMC READ CD (0xBE) and encodes FLAC.
    """
    total_sectors = end_lba - start_lba
    batch_sectors = 27  # 27 sectors * 2352 bytes = 63,504 bytes (Maximum safe buffer under Windows 64KB SCSI limit)

    pcm_chunks = []
    curr_lba = start_lba

    while curr_lba < end_lba:
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("轉檔作業已被使用者取消")

        secs_to_read = min(batch_sectors, end_lba - curr_lba)
        buf_size = 2352 * secs_to_read
        buf = ctypes.create_string_buffer(buf_size)

        sptd = SCSI_PASS_THROUGH_DIRECT()
        sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
        sptd.CdbLength = 12
        sptd.DataIn = 1
        sptd.DataTransferLength = buf_size
        sptd.TimeOutValue = 10
        sptd.DataBuffer = ctypes.cast(buf, ctypes.c_void_p)

        # SCSI MMC READ CD Command (0xBE)
        sptd.Cdb[0] = 0xBE
        sptd.Cdb[1] = 0x04  # CD-DA Audio
        sptd.Cdb[2] = (curr_lba >> 24) & 0xFF
        sptd.Cdb[3] = (curr_lba >> 16) & 0xFF
        sptd.Cdb[4] = (curr_lba >> 8) & 0xFF
        sptd.Cdb[5] = curr_lba & 0xFF
        sptd.Cdb[6] = (secs_to_read >> 16) & 0xFF
        sptd.Cdb[7] = (secs_to_read >> 8) & 0xFF
        sptd.Cdb[8] = secs_to_read & 0xFF
        sptd.Cdb[9] = 0xF0  # User Data 2352 bytes/sector

        win32file.DeviceIoControl(handle, IOCTL_SCSI_PASS_THROUGH_DIRECT, bytes(sptd), ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT), None)
        pcm_chunks.append(buf.raw)
        curr_lba += secs_to_read

        if progress_fn:
            progress_fn(curr_lba - start_lba, total_sectors)

    # Encode raw 16-bit 44.1kHz Stereo PCM to FLAC
    raw_bytes = b''.join(pcm_chunks)
    audio = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)
    sf.write(output_flac_path, audio, 44100, subtype='PCM_16')

class CDRipperTask:
    """Manages asynchronous CD ripping in a background thread."""
    def __init__(
        self,
        drive_letter: str = None,
        temp_dir: str = None,
        on_track_start=None,
        on_track_progress=None,
        on_track_complete=None,
        on_all_complete=None,
        on_error=None,
        on_log=None
    ):
        self.drive_letter = drive_letter if drive_letter else cfg.drive_letter
        self.temp_dir = Path(temp_dir) if temp_dir else cfg.temp_dir
        self.tracks_info = []
        self.current_track_idx = 0
        self.current_track_progress = 0.0
        self.is_completed = False
        self.is_cancelled = False
        self.error = None
        self.thread = None
        self.cancel_event = threading.Event()

        # Callbacks
        self.on_track_start = on_track_start
        self.on_track_progress = on_track_progress
        self.on_track_complete = on_track_complete
        self.on_all_complete = on_all_complete
        self.on_error = on_error
        self.on_log = on_log

    def log(self, message: str):
        print(message)
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def cancel(self):
        """Signals task to stop ripping as soon as possible."""
        self.cancel_event.set()
        self.is_cancelled = True
        self.log("[Ripper] 收到取消請求，正在中止轉檔作業...")

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            self.tracks_info = read_cd_toc(self.drive_letter)
            total_tracks = len(self.tracks_info)
            self.log(f"[Ripper] 成功讀取目錄，共 {total_tracks} 首曲目，儲存目錄: {self.temp_dir}")
            
            h = get_cd_drive_handle(self.drive_letter)
            try:
                for idx, track in enumerate(self.tracks_info):
                    if self.cancel_event.is_set():
                        self.is_cancelled = True
                        self.log("[Ripper] 作業已取消。")
                        return

                    self.current_track_idx = idx
                    tr_str = f"{track['track_num']:02d}"
                    out_flac = self.temp_dir / f"{tr_str}. CD Track {tr_str}.flac"

                    if self.on_track_start:
                        try:
                            self.on_track_start(idx, track['track_num'], total_tracks, track['duration_sec'])
                        except Exception:
                            pass

                    def update_prog(done_secs, total_secs):
                        self.current_track_progress = done_secs / total_secs
                        if self.on_track_progress:
                            try:
                                self.on_track_progress(idx, track['track_num'], self.current_track_progress, done_secs, total_secs)
                            except Exception:
                                pass

                    self.log(f"[Ripper] 開始擷取第 {tr_str}/{total_tracks:02d} 首 ({track['duration_sec']} 秒)...")
                    rip_single_track(h, track['start_lba'], track['end_lba'], str(out_flac), update_prog, self.cancel_event)
                    self.log(f"[Ripper] 完成第 {tr_str} 首轉碼")

                    if self.on_track_complete:
                        try:
                            self.on_track_complete(idx, track['track_num'], str(out_flac))
                        except Exception:
                            pass

                self.is_completed = True
                self.log("[Ripper] 全數曲目擷取完成！")
                if self.on_all_complete:
                    try:
                        self.on_all_complete(str(self.temp_dir), total_tracks)
                    except Exception:
                        pass
            finally:
                win32file.CloseHandle(h)
        except Exception as e:
            if self.cancel_event.is_set():
                self.is_cancelled = True
                self.log("[Ripper] 轉檔作業已終止。")
            else:
                self.error = e
                self.log(f"[Ripper Error] CD 擷取失敗: {e}")
                if self.on_error:
                    try:
                        self.on_error(e)
                    except Exception:
                        pass

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print("Reading CD TOC from drive", cfg.drive_letter)
    toc = read_cd_toc()
    for t in toc:
        print(f"Track {t['track_num']:02d}: LBA {t['start_lba']} -> {t['end_lba']} ({t['duration_sec']}s)")
