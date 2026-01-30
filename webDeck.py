'''
A simple web server that runs Stream Deck-like actions based on HTTP POST requests.
Supports automatic discovery and connection handling.
'''

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from tkinter import messagebox
import socket
import logging
import os
import threading
import sys
import subprocess
import importlib.util
import inspect
import traceback
import re
from pathlib import Path

try:
    from pynput.keyboard import Controller, Key
    MEDIA_CONTROL_AVAILABLE = True
except ImportError:
    MEDIA_CONTROL_AVAILABLE = False
    print("pynput not found. Media control will be disabled.")

try:
    from windows_toasts import Toast, ToastDuration, ToastScenario, WindowsToaster
except ImportError:
    WindowsToaster = None

try:
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtGui import QIcon
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("PyQt6 not found. Tray applet will be disabled.")

# Initialize the keyboard controller
keyboard_controller = Controller() if MEDIA_CONTROL_AVAILABLE else None

# Suppress HTTP server logging
logging.getLogger().setLevel(logging.CRITICAL)

notifHost = WindowsToaster("WebDeck") if WindowsToaster else None

# Global registry for plugin action -> callable
PLUGIN_ACTIONS = {}


def _camel_to_snake(name: str) -> str:
    # Convert CamelCase or mixedCase to snake_case
    s1 = re.sub('(.)([A-Z][a-z]+)', r"\1_\2", name)
    s2 = re.sub('([a-z0-9])([A-Z])', r"\1_\2", s1)
    return s2.replace('-', '_').lower()


def load_plugins(plugins_dir: str = None):
    """Load .py plugin modules from plugins_dir and register callable actions.

    Rules:
    - Module filename (without .py) converted to snake_case becomes an action mapped
      to the module `main()` function if present.
    - Public functions in the module will be registered by their snake_case name.
    - If the module defines a `WebDeckPlugin` class, its public instance methods
      (excluding `metadata`) will be registered by snake_case method name.
    """
    global PLUGIN_ACTIONS
    if plugins_dir is None:
        plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')

    plugins_path = Path(plugins_dir)
    if not plugins_path.exists() or not plugins_path.is_dir():
        print(f"[PLUGINS] No plugins directory found at {plugins_path}")
        return

    for p in plugins_path.iterdir():
        if p.suffix != '.py' or p.name.startswith('_'):
            continue
        mod_name = p.stem
        try:
            spec = importlib.util.spec_from_file_location(f"webdeck_plugin_{mod_name}", str(p))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Only register methods on a WebDeckPlugin class (ignore module-level functions)
            if hasattr(module, 'WebDeckPlugin'):
                try:
                    cls = getattr(module, 'WebDeckPlugin')
                    plugin_instance = cls()
                    for attr_name, attr in inspect.getmembers(plugin_instance, inspect.ismethod):
                        # Skip private methods and metadata attribute
                        if attr_name.startswith('_') or attr_name == 'metadata':
                            continue
                        action_name = _camel_to_snake(attr_name)
                        PLUGIN_ACTIONS.setdefault(action_name, attr)
                        print(f"[PLUGINS] Registered action '{action_name}' -> {p.name}.WebDeckPlugin.{attr_name}()")
                except Exception:
                    print(f"[PLUGINS] Failed to instantiate WebDeckPlugin in {p.name}:\n{traceback.format_exc()}")
            else:
                # No WebDeckPlugin class found — ignore this module for actions
                print(f"[PLUGINS] Skipping {p.name}: no WebDeckPlugin class found")

        except Exception:
            print(f"[PLUGINS] Failed to load plugin {p.name}:\n{traceback.format_exc()}")

    # Summary
    if PLUGIN_ACTIONS:
        print(f"[PLUGINS] Loaded {len(PLUGIN_ACTIONS)} plugin actions: {', '.join(sorted(PLUGIN_ACTIONS.keys()))}")
    else:
        print("[PLUGINS] No plugin actions registered.")


# Attempt to load plugins on import
load_plugins()

def get_button_configuration():
    """Load button configuration from the config file"""
    config_path = os.path.join(os.path.dirname(__file__), 'webdeckCfg.json')
    
    # Default button configuration
    default_buttons = [
        {"label": "Example action", "icon": "🎬", "action": "example"},
        {"label": "Open Notepad", "icon": "🎵", "action": "open_app", "path": "C:\\Windows\\System32\\notepad.exe"},
        {"label": "Mute/Unmute Sound", "icon": "🎙️", "action": "toggle_mute"},
        {"label": "Play/Pause Media", "icon": "📹", "action": "pause_media"},
        {"label": "Next/Skip Track", "icon": "🔴", "action": "skip_track"},
        {"label": "Previous Track", "icon": "⏹️", "action": "previous_track"},
        {"label": "Open ChatGPT", "icon": "▶️", "action": "open_url", "path": "https://chat.openai.com/"},
        {"label": "Lock Screen", "icon": "⏸️", "action": "lock_screen"},
        {"label": "Button 9", "icon": "🔊", "action": "action_9"},
        {"label": "Button 10", "icon": "🔇", "action": "action_10"},
        {"label": "Button 11", "icon": "⬆️", "action": "action_11"},
        {"label": "Button 12", "icon": "⬇️", "action": "action_12"},
        {"label": "Button 13", "icon": "▶️", "action": "action_7"},
        {"label": "Button 14", "icon": "⏸️", "action": "action_8"},
        {"label": "Button 15", "icon": "🔊", "action": "action_9"},
        {"label": "Button 16", "icon": "🔇", "action": "action_10"},
        {"label": "Button 17", "icon": "⬆️", "action": "action_11"},
        {"label": "Button 18", "icon": "⬇️", "action": "action_12"}
    ]
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if 'buttons' in config:
                return config['buttons']
            else:
                raise KeyError("'buttons' key not found in config file")
    except FileNotFoundError:
        # Create config file with defaults
        default_config = {
            "notifications": {
                "enabled": True,
                "important_only": False
            },
            "password": {
                "required": False,
                "value": "your_password_here"
            },
            "buttons": default_buttons
        }
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            print(f"[CONFIG] Created default config file at {config_path}")
        except Exception as e:
            print(f"[ERROR] Failed to create config file: {e}")
        raise FileNotFoundError(f"Config file not found at {config_path}. Default config file created. Please restart the server.")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in config file: {e}", e.doc, e.pos)

def send_notification(title, message, important=False):
    if notifHost:
        notif = Toast()
        notif.duration = ToastDuration.Short
        if important:
            notif.scenario = ToastScenario.Important
        notif.text_fields = [title, message]
        notifHost.show_toast(notif)
    else:
        print(f"WebDeck tried to send a Windows system notification, but WindowsToaster is missing.")

def handle_media_control(action):
    """Handle media control actions using Windows media keys"""
    if not MEDIA_CONTROL_AVAILABLE or not keyboard_controller:
        return {"status": "error", "message": "Media control not available."}
    
    try:
        if action == "pause_media":
            keyboard_controller.press(Key.media_play_pause)
            keyboard_controller.release(Key.media_play_pause)
            return {"status": "success", "message": "Toggled play/pause."}
        elif action == "toggle_mute":
            keyboard_controller.press(Key.media_volume_mute)
            keyboard_controller.release(Key.media_volume_mute)
            return {"status": "success", "message": "Toggled mute."}
        elif action == "skip_track":
            keyboard_controller.press(Key.media_next)
            keyboard_controller.release(Key.media_next)
            return {"status": "success", "message": "Skipped to next track."}
        elif action == "previous_track":
            keyboard_controller.press(Key.media_previous)
            keyboard_controller.release(Key.media_previous)
            return {"status": "success", "message": "Skipped to previous track."}
        else:
            return {"status": "error", "message": "Unknown media action."}
    except AttributeError as e:
        return {"status": "error", "message": f"Media key not supported on this system: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to execute media control: {e}"}

class WebDeckHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Suppress default server logging"""
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Handle discovery and button configuration requests"""
        if self.path == '/discover':
            hostname = socket.gethostname()
            response = {
                "status": "online",
                "message": "WebDeck server is online",
                "hostname": hostname,
                "port": 8001
            }
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
            print(f"[SYSTEM] Client connected.")
            send_notification("WebDeck", f"Client connected from {self.client_address[0]}", important=False)
        elif self.path == '/status':
            # Lightweight status check used by GUIs - do not trigger user notifications
            hostname = socket.gethostname()
            response = {
                "status": "online",
                "hostname": hostname,
                "port": 8001
            }
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        elif self.path == '/buttons':
            buttons = get_button_configuration()
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(buttons).encode('utf-8'))
            print(f"[SYSTEM] Sent button configuration to client.")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # Special endpoint to trigger a reload (no action body required)
        if self.path == '/reload':
            # Simply verify config file can be read and respond accordingly
            try:
                _ = get_button_configuration()
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Reloaded button configuration."}).encode('utf-8'))
                print(f"[SYSTEM] Reloaded button configuration.")
            except Exception as e:
                self.send_response(500)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            data = json.loads(post_data)
            action = data.get("action")
            if action == "example":
                messagebox.showinfo("Test Action", "This is a test action from WebDeck.")
                response = {"status": "success", "message": "Opened example message box."}
                print(f"[SYSTEM] Example action executed")
            elif action == "open_app":
                path_to_app = data.get("path")
                try:
                    os.startfile(path_to_app)
                    response = {"status": "success", "message": f"Opened application: {path_to_app}"}
                    print(f"[SYSTEM] Opened application: {path_to_app}")
                    send_notification("WebDeck", f"Opened application: {os.path.basename(path_to_app)}", important=False)
                except Exception as e:
                    response = {"status": "error", "message": f"Failed to open application: {e}"}
                    print(f"[SYSTEM] Failed to open application: {e}")
                    send_notification("WebDeck", f"Failed to open application: {os.path.basename(path_to_app)}", important=True)
            elif action in ["toggle_mute", "pause_media", "skip_track", "previous_track"]:
                response = handle_media_control(action)
                if response["status"] == "success":
                    print(f"[MEDIA] {response['message']}")
                    send_notification("WebDeck", response['message'], important=False)
                else:
                    print(f"[MEDIA] {response['message']}")
                    send_notification("WebDeck", response['message'], important=True)
            elif action == "open_url":
                url = data.get("path")
                try:
                    os.startfile(url)
                    response = {"status": "success", "message": f"Opened URL: {url}"}
                    print(f"[SYSTEM] Opened URL: {url}")
                    send_notification("WebDeck", f"Opened URL: {url}", important=False)
                except Exception as e:
                    response = {"status": "error", "message": f"Failed to open URL: {e}"}
                    print(f"[SYSTEM] Failed to open URL: {e}")
                    send_notification("WebDeck", f"Failed to open URL: {url}", important=True)
            elif action == "lock_screen":
                try:
                    os.system("rundll32.exe user32.dll,LockWorkStation")
                    response = {"status": "success", "message": "Screen locked."}
                    print(f"[SYSTEM] Screen locked.")
                    send_notification("WebDeck", "Screen locked.", important=False)
                except Exception as e:
                    response = {"status": "error", "message": f"Failed to lock screen: {e}"}
                    print(f"[SYSTEM] Failed to lock screen: {e}")
                    send_notification("WebDeck", "Failed to lock screen.", important=True)
            else:
                # If action not handled by builtin handlers, try plugin registry
                plugin_callable = PLUGIN_ACTIONS.get(action)
                if plugin_callable:
                    try:
                        sig = inspect.signature(plugin_callable)
                        # Call plugin with `data` if it accepts parameters, otherwise without
                        if len(sig.parameters) == 0:
                            result = plugin_callable()
                        else:
                            result = plugin_callable(data)

                        if isinstance(result, dict) and 'status' in result:
                            response = result
                        else:
                            response = {"status": "success", "message": f"Plugin '{action}' executed."}
                        # Notify user of plugin outcome
                        if response.get("status") == "success":
                            send_notification("WebDeck", response.get("message", f"Plugin {action} ran."), important=False)
                        else:
                            send_notification("WebDeck", response.get("message", f"Plugin {action} failed."), important=True)
                        print(f"[PLUGINS] Executed plugin action '{action}'")
                    except Exception as e:
                        tb = traceback.format_exc()
                        print(f"[PLUGINS] Error executing plugin '{action}': {e}\n{tb}")
                        response = {"status": "error", "message": f"Plugin error: {e}"}
                        send_notification("WebDeck", f"Plugin error: {e}", important=True)
                else:
                    response = {"status": "error", "message": "Unknown action."}
                    send_notification("WebDeck", "Received unknown action.", important=True)
        except json.JSONDecodeError:
            response = {"status": "error", "message": "Invalid JSON."}
            send_notification("WebDeck", "Received invalid JSON.", important=True)
        
        status_code = 200 if response["status"] == "success" else 400
        self.send_response(status_code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

def run(server_class=HTTPServer, handler_class=WebDeckHandler, port=8001):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'\n=== WebDeck Server v1.0 ===')
    print("By Windswipe\n")
    print("Debug/System Info:")
    print(f'Hostname: {socket.gethostname()}')
    print(f'IP Address: {socket.gethostbyname(socket.gethostname())}\n')
    print("=============================\n")
    print(f'Starting web server on port {port}...')
    print(f'Waiting for clients to connect...\n')
    send_notification("WebDeck", "Server started!", important=False)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
        print('\nStopping web server.')
        exit(0)

def start_server_thread():
    """Run the HTTP server in a background thread"""
    server_thread = threading.Thread(target=run, daemon=True)
    server_thread.start()

def create_qt_app():
    """Create a PyQt6 tray applet with an exit button."""
    if not PYQT_AVAILABLE:
        print("PyQt6 not available. Running server without tray applet.")
        run()
        return

    app = QApplication(sys.argv)
    
    # Create tray icon
    tray = QSystemTrayIcon()
    
    # Create a simple colored icon (blue)
    icon = QIcon()
    pixmap = app.style().standardIcon(app.style().StandardPixmap.SP_MediaPlay).pixmap(64, 64)
    icon.addPixmap(pixmap)
    tray.setIcon(icon)
    
    # Create context menu
    menu = QMenu()

    launch_gui_action = menu.addAction("Open Setttings GUI")
    def _launch_gui_process():
        try:
            gui_path = os.path.join(os.path.dirname(__file__), "webDeck_GUI.py")
            if not os.path.exists(gui_path):
                print(f"[TRAY] GUI script not found: {gui_path}")
                return
            # Use same Python interpreter
            args = [sys.executable, gui_path]
            creationflags = 0
            # Windows: use detached process flags
            if os.name == 'nt':
                creationflags = 0
                if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                    creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
                if hasattr(subprocess, 'DETACHED_PROCESS'):
                    creationflags |= subprocess.DETACHED_PROCESS
                subprocess.Popen(args, cwd=os.path.dirname(gui_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
            else:
                # POSIX: start new session
                subprocess.Popen(args, cwd=os.path.dirname(gui_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            print("[TRAY] Launched GUI process.")
        except Exception as e:
            print(f"[TRAY] Failed to launch GUI process: {e}")

    launch_gui_action.triggered.connect(_launch_gui_process)

    open_web_gui_action = menu.addAction("Open Web GUI")
    def _open_web_gui():
        try:
            import webbrowser
            webbrowser.open("https://windswipe.github.io/WebDeck/webDeckClient/?ip=127.0.0.1")
            print("[TRAY] Opened Web GUI in default browser.")
        except Exception as e:
            print(f"[TRAY] Failed to open Web GUI: {e}")
    
    exit_action = menu.addAction("Exit WebDeck")
    exit_action.triggered.connect(lambda: sys.exit(0))
    
    tray.setContextMenu(menu)
    tray.show()
    
    # Start the server in a separate thread
    start_server_thread()
    
    # Run the Qt event loop
    sys.exit(app.exec())
    

if __name__ == "__main__":
    create_qt_app()
    run()