import os
import shutil
import subprocess
from pathlib import Path
from config import cfg

def locate_foobar_executable(configured_path: str = None) -> str | None:
    """Locate foobar2000 executable from config or standard Windows install paths."""
    path_to_check = configured_path if configured_path is not None else cfg.foobar_path

    # Check specified path directly
    if path_to_check:
        p = Path(path_to_check)
        if p.is_file():
            return str(p)
        # Check if command is in system PATH (e.g. 'foobar2000')
        found_in_path = shutil.which(path_to_check)
        if found_in_path:
            return found_in_path

    # Common default Windows installation locations for foobar2000
    default_locations = [
        r"C:\Program Files\foobar2000\foobar2000.exe",
        r"C:\Program Files (x86)\foobar2000\foobar2000.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\foobar2000\foobar2000.exe")
    ]
    for loc in default_locations:
        if Path(loc).is_file():
            return loc

    return None

def open_album_folder_in_explorer(folder_path: Path):
    """Open album folder in Windows Explorer."""
    try:
        os.startfile(str(folder_path))
        print(f"Opened in Windows Explorer: {folder_path}")
        return True
    except Exception as e:
        print(f"Failed to open folder in Explorer: {e}")
        return False

def add_to_foobar_or_open(folder_path: Path) -> dict:
    """
    Adds target folder to foobar2000 playlist if foobar2000 is enabled and found.
    Falls back to opening folder in Windows Explorer if configured.
    """
    folder_path = Path(folder_path)
    result = {"foobar_opened": False, "explorer_opened": False}

    if not folder_path.exists():
        print(f"Error: Target directory does not exist: {folder_path}")
        return result

    if cfg.open_in_foobar:
        foobar_exe = locate_foobar_executable()
        if foobar_exe:
            try:
                # Command line: foobar2000.exe /add "folder_path"
                cmd = [foobar_exe, "/add", str(folder_path)]
                subprocess.Popen(cmd)
                print(f"Added to foobar2000 playlist: {folder_path}")
                result["foobar_opened"] = True
                return result
            except Exception as e:
                print(f"Warning: Failed to launch foobar2000: {e}")
        else:
            print("Notice: foobar2000 executable not found.")

    # Fallback to Windows Explorer
    if cfg.fallback_open_explorer:
        result["explorer_opened"] = open_album_folder_in_explorer(folder_path)

    return result

if __name__ == '__main__':
    # Quick standalone test
    test_folder = cfg.output_dir
    if test_folder.exists():
        print(f"Testing player launcher on: {test_folder}")
        res = add_to_foobar_or_open(test_folder)
        print("Result:", res)
