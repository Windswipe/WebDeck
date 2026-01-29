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
            keyboard_controller.press(Key.media_prev)
            keyboard_controller.release(Key.media_prev)
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
        """Handle discovery requests"""
        if self.path == '/discover':
            hostname = socket.gethostname()
            response = {
                "status": "online",
                "message": "WebDeck server is online",
                "hostname": hostname,
                "port": 8000
            }
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
            print(f"[SYSTEM] Client connected.")
            send_notification("WebDeck", f"Client connected!", important=False)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
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

def run(server_class=HTTPServer, handler_class=WebDeckHandler, port=8000):
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