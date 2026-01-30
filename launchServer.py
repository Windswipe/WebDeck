#!/usr/bin/env python
"""
launchServer.py

Performs startup checks and launches the WebDeck server in a detached process.

Behavior:
1. Ensure required Python packages are installed (attempts `pip install` for missing ones).
2. Create a default `webdeckCfg.json` if it does not exist.
3. If this repository is a git clone, check remote for updates and `git pull` if needed.
4. Create a startup entry (batch file) in the current user's Startup folder if none exists.
5. Start `webDeck.py` in a detached process and exit.

This script is conservative — it only auto-updates when a `.git` directory exists and `git` is available.
"""

from pathlib import Path
import os
import sys
import subprocess
import json
import shutil
import time
import urllib.request
import urllib.error
import tempfile
import zipfile
import datetime


REPO_ROOT = Path(__file__).parent
CONFIG_PATH = REPO_ROOT / 'webdeckCfg.json'
WEBDECK_SCRIPT = REPO_ROOT / 'webDeck.py'

# Modules to check and candidate pip packages (module_name -> pip_name)
REQUIRED_MODULES = {
    'pynput': 'pynput',
    'windows_toasts': 'windows-toasts',
    'PyQt6': 'PyQt6',
    'pycaw': 'pycaw',
    'win32gui': 'pywin32',
    'psutil': 'psutil'
}

# Names (top-level file/dir names) to preserve during ZIP updates
PRESERVE_NAMES = {CONFIG_PATH.name, 'plugins'}


def ensure_dependencies():
    missing = []
    for mod, pkg in REQUIRED_MODULES.items():
        try:
            __import__(mod)
        except Exception:
            missing.append((mod, pkg))

    if not missing:
        print('[DEPS] All required modules are available')
        return True

    print(f"[DEPS] Missing modules: {', '.join(m for m, _ in missing)}")
    for mod, pkg in missing:
        try:
            print(f"[DEPS] Installing {pkg}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])
            time.sleep(0.2)
        except Exception as e:
            print(f"[DEPS] Failed to install {pkg}: {e}")
            return False

    # Verify again
    for mod, _ in missing:
        try:
            __import__(mod)
        except Exception as e:
            print(f"[DEPS] Still cannot import {mod}: {e}")
            return False

    print('[DEPS] Dependencies installed successfully')
    return True


def create_default_config():
    if CONFIG_PATH.exists():
        print(f"[CONFIG] Config exists at {CONFIG_PATH}")
        return True

    default_buttons = [
        {"label": "Example action", "icon": "🎬", "action": "example"},
        {"label": "Open Notepad", "icon": "🎵", "action": "open_app", "path": "C:\\Windows\\System32\\notepad.exe"},
        {"label": "Mute/Unmute Sound", "icon": "🎙️", "action": "toggle_mute"},
        {"label": "Play/Pause Media", "icon": "📹", "action": "pause_media"},
        {"label": "Next/Skip Track", "icon": "🔴", "action": "skip_track"},
        {"label": "Previous Track", "icon": "⏹️", "action": "previous_track"},
        {"label": "Open ChatGPT", "icon": "▶️", "action": "open_url", "path": "https://chat.openai.com/"},
        {"label": "Lock Screen", "icon": "⏸️", "action": "lock_screen"}
    ]

    default_config = {
        "notifications": {"enabled": True, "important_only": False},
        "password": {"required": False, "value": "your_password_here"},
        "buttons": default_buttons
    }

    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"[CONFIG] Created default config at {CONFIG_PATH}")
        return True
    except Exception as e:
        print(f"[CONFIG] Failed to create config: {e}")
        return False


def git_check_and_update():
    git_dir = REPO_ROOT / '.git'
    if not git_dir.exists():
        print('[UPDATE] No .git directory found — skipping update check')
        return False

    # Ensure git is available
    try:
        subprocess.check_call(['git', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print('[UPDATE] git not available on PATH — skipping update check')
        return False

    try:
        # Fetch remote
        print('[UPDATE] Fetching remote...')
        subprocess.check_call(['git', 'fetch'], cwd=str(REPO_ROOT))

        # Local and remote refs
        local = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=str(REPO_ROOT)).strip()
        try:
            upstream = subprocess.check_output(['git', 'rev-parse', '@{u}'], cwd=str(REPO_ROOT)).strip()
        except subprocess.CalledProcessError:
            # No upstream configured
            print('[UPDATE] No upstream configured for current branch — skipping auto-update')
            return False

        if local != upstream:
            print('[UPDATE] Remote has new commits — pulling...')
            subprocess.check_call(['git', 'pull'], cwd=str(REPO_ROOT))
            print('[UPDATE] Repository updated')
            return True
        else:
            print('[UPDATE] Repository up-to-date')
            return False
    except Exception as e:
        print(f'[UPDATE] Update check failed: {e}')
        return False


def github_zip_update(repo_owner='Windswipe', repo_name='WebDeck'):
    """If this installation is not a git clone, check GitHub for changes and
    download/apply a ZIP update when the remote HEAD differs from the last
    applied SHA. Preserves `webdeckCfg.json` and creates backups.
    """
    api_repo = f'https://api.github.com/repos/{repo_owner}/{repo_name}'
    try:
        req = urllib.request.Request(api_repo, headers={'User-Agent': 'WebDeck-Updater'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            repo_info = json.load(resp)
            default_branch = repo_info.get('default_branch', 'main')
    except Exception as e:
        print(f"[UPDATE] Could not query GitHub repo info: {e}")
        return False

    # Get latest commit SHA for default branch
    commit_api = f'{api_repo}/commits/{default_branch}'
    try:
        req = urllib.request.Request(commit_api, headers={'User-Agent': 'WebDeck-Updater'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            commit_info = json.load(resp)
            latest_sha = commit_info.get('sha')
    except Exception as e:
        print(f"[UPDATE] Could not query latest commit: {e}")
        return False

    if not latest_sha:
        print('[UPDATE] No commit SHA found from GitHub')
        return False

    sha_file = REPO_ROOT / '.webdeck_remote_sha'
    try:
        if sha_file.exists():
            local_sha = sha_file.read_text(encoding='utf-8').strip()
        else:
            local_sha = None
    except Exception:
        local_sha = None

    if local_sha == latest_sha:
        print('[UPDATE] Remote ZIP up-to-date')
        return False

    # Download zipball
    zip_url = f'https://github.com/{repo_owner}/{repo_name}/archive/refs/heads/{default_branch}.zip'
    print(f"[UPDATE] Downloading {zip_url}...")
    try:
        with urllib.request.urlopen(urllib.request.Request(zip_url, headers={'User-Agent': 'WebDeck-Updater'}), timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        print(f"[UPDATE] Failed to download ZIP: {e}")
        return False

    # Extract to temp dir
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix='webdeck_update_'))
        zip_path = tmpdir / 'update.zip'
        zip_path.write_bytes(data)
        with zipfile.ZipFile(str(zip_path), 'r') as z:
            z.extractall(str(tmpdir))
        # Find extracted root dir
        children = [p for p in tmpdir.iterdir() if p.is_dir()]
        if not children:
            print('[UPDATE] Extracted ZIP contains no files')
            shutil.rmtree(str(tmpdir), ignore_errors=True)
            return False
        extracted_root = children[0]
    except Exception as e:
        print(f"[UPDATE] Failed to extract ZIP: {e}")
        try:
            shutil.rmtree(str(tmpdir), ignore_errors=True)
        except Exception:
            pass
        return False

    # Prepare backup dir
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    backup_root = REPO_ROOT / 'backups' / timestamp
    backup_root.mkdir(parents=True, exist_ok=True)

    # Copy files from extracted_root into REPO_ROOT, backing up overwritten files
    preserved_names = PRESERVE_NAMES
    try:
        for src in extracted_root.rglob('*'):
            rel = src.relative_to(extracted_root)
            # Skip .git artifacts
            if '.git' in rel.parts:
                continue

            # If the top-level path is in preserved_names, skip applying changes
            top = rel.parts[0] if len(rel.parts) > 0 else None
            if top in preserved_names:
                # If it's a directory preserve, log and skip
                dest = REPO_ROOT / rel
                if dest.exists():
                    print(f"[UPDATE] Preserving user file/dir: {dest}")
                continue

            dest = REPO_ROOT / rel
            if src.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue

            # Backup dest if exists
            if dest.exists():
                dest_parent = backup_root / rel.parent
                dest_parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(dest), str(dest_parent / dest.name))
                except Exception:
                    pass

            # Ensure parent exists and copy
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))

        # Write latest sha
        try:
            sha_file.write_text(latest_sha, encoding='utf-8')
        except Exception:
            pass

        print(f'[UPDATE] Applied ZIP update from GitHub to {REPO_ROOT} (backup at {backup_root})')
        # Clean up tmp
        try:
            shutil.rmtree(str(tmpdir), ignore_errors=True)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[UPDATE] Failed while applying update: {e}")
        try:
            shutil.rmtree(str(tmpdir), ignore_errors=True)
        except Exception:
            pass
        return False


def ensure_startup_entry():
    # Windows Startup folder
    if os.name != 'nt':
        print('[STARTUP] Non-Windows OS dectected — WebDeck only works on Windows.')
        exit(0)

    try:
        appdata = os.environ.get('APPDATA')
        if not appdata:
            print('[STARTUP] APPDATA not found — cannot create startup entry')
            return False
        startup_dir = Path(appdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
        startup_dir.mkdir(parents=True, exist_ok=True)

        bat_path = startup_dir / 'WebDeck_start.bat'
        python_exe = sys.executable
        webdeck_path = str(WEBDECK_SCRIPT)

        content = f'start "" "{python_exe}" "{webdeck_path}"\r\n'

        if bat_path.exists():
            # Check content; if it already points to the same python and script, do nothing
            try:
                existing = bat_path.read_text(encoding='utf-8')
                if python_exe in existing and webdeck_path in existing:
                    print(f'[STARTUP] Startup entry already exists at {bat_path}')
                    return True
            except Exception:
                pass

        bat_path.write_text(content, encoding='utf-8')
        print(f'[STARTUP] Wrote startup batch to {bat_path}')
        return True
    except Exception as e:
        print(f'[STARTUP] Failed to create startup entry: {e}')
        return False


def launch_server_detached():
    if not WEBDECK_SCRIPT.exists():
        print(f'[LAUNCH] Server script not found: {WEBDECK_SCRIPT}')
        return False

    args = [sys.executable, str(WEBDECK_SCRIPT)]
    try:
        if os.name == 'nt':
            creationflags = 0
            if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, 'DETACHED_PROCESS'):
                creationflags |= subprocess.DETACHED_PROCESS
            subprocess.Popen(args, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        else:
            subprocess.Popen(args, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

        print('[LAUNCH] Server started in a detached process')
        return True
    except Exception as e:
        print(f'[LAUNCH] Failed to start server: {e}')
        return False


def main():
    print('=== WebDeck Launcher ===')

    ok = ensure_dependencies()
    if not ok:
        print('[MAIN] Dependency installation failed; you may need to run this script as an administrator or install packages manually.')

    create_default_config()

    try:
        updated = git_check_and_update()
        if not updated:
            # attempt non-git update flow
            try:
                zip_updated = github_zip_update()
                if zip_updated:
                    time.sleep(0.5)
            except Exception:
                pass
        else:
            # small pause to allow files to settle after git pull
            time.sleep(0.5)
    except Exception:
        pass

    ensure_startup_entry()

    launched = launch_server_detached()
    if launched:
        print('[MAIN] Exiting launcher.')
        sys.exit(0)
    else:
        print('[MAIN] Could not launch server; staying alive for troubleshooting')


if __name__ == '__main__':
    main()
