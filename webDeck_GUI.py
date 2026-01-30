"""
WebDeck GUI - Configure buttons and actions
"""

import sys
import json
import os
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QPushButton, QLabel, QLineEdit, QComboBox,
                             QMessageBox, QInputDialog, QDialog, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor
import urllib.request
import urllib.error
import subprocess
import threading
import time
import sys
try:
    import webDeck
    PLUGIN_ACTIONS = getattr(webDeck, 'PLUGIN_ACTIONS', {})
except Exception:
    PLUGIN_ACTIONS = {}

class EmojiPickerDialog(QDialog):
    """Simple emoji picker dialog"""
    def __init__(self, parent=None, current_emoji=""):
        super().__init__(parent)
        self.setWindowTitle("Pick an Emoji")
        self.setGeometry(100, 100, 600, 400)
        self.selected_emoji = current_emoji
        
        layout = QVBoxLayout()
        
        # Create scrollable emoji grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(5)
        
        # Common emojis for buttons
        common_emojis = [
            "🎬", "🎵", "🎙️", "📹", "🔴", "⏹️", "▶️", "⏸️", 
            "🔊", "🔇", "⬆️", "⬇️", "⬅️", "➡️", "🔒", "🔓",
            "⌨️", "🖱️", "💾", "📁", "📂", "🗑️", "🔄", "⚙️",
            "🌐", "📡", "🔗", "📞", "📧", "📮", "🔔", "🔕",
            "⭐", "🌟", "✨", "💫", "🎯", "🎲", "🎰", "🎪",
            "🏠", "🏢", "🏭", "🏗️", "🏛️", "🏰", "🎡", "🎢",
            "⚡", "🔥", "💧", "❄️", "☀️", "🌙", "⭐", "☃️",
            "🎁", "🎀", "🎊", "🎉", "🎈", "🎃", "🎄", "🎆"
        ]
        
        for i, emoji_char in enumerate(common_emojis):
            btn = QPushButton(emoji_char)
            btn.setFixedSize(50, 50)
            btn.setFont(QFont("Arial", 24))
            btn.clicked.connect(lambda checked, e=emoji_char: self.select_emoji(e))
            grid.addWidget(btn, i // 8, i % 8)
        
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addWidget(ok_btn)
        layout.addLayout(bottom_layout)
        
        self.setLayout(layout)
    
    def select_emoji(self, emoji_char):
        self.selected_emoji = emoji_char
        self.accept()
    
    def get_emoji(self):
        return self.selected_emoji


class ButtonConfigWidget(QFrame):
    """Widget representing a single button in the grid"""
    def __init__(self, button_num, button_data=None, on_click=None):
        super().__init__()
        self.button_num = button_num
        self.button_data = button_data or {"label": f"Button {button_num}", "icon": "❓", "action": "example"}
        self.on_click = on_click
        self.is_selected = False
        
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Emoji display
        self.emoji_label = QLabel(self.button_data.get("icon", "❓"))
        self.emoji_label.setFont(QFont("Arial", 24))
        self.emoji_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Label display
        self.label_widget = QLabel(self.button_data.get("label", f"Button {button_num}"))
        self.label_widget.setFont(QFont("Arial", 9))
        self.label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_widget.setWordWrap(True)
        
        layout.addWidget(self.emoji_label)
        layout.addWidget(self.label_widget)
        layout.addStretch()
        
        self.setLayout(layout)
        self.setMinimumHeight(100)
        self.set_selected(False)
    
    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            self.setStyleSheet("""
                ButtonConfigWidget {
                    background-color: #00d9ff;
                    border: 3px solid #0099cc;
                    border-radius: 8px;
                    color: #ffffff;
                }
            """)
            # selected - use dark text for contrast on cyan background
            self.label_widget.setStyleSheet("color: #002a33;")
            self.emoji_label.setStyleSheet("color: #002a33;")
        else:
            self.setStyleSheet("""
                ButtonConfigWidget {
                    background-color: #0f3460;
                    border: 2px solid #3700ff;
                    border-radius: 8px;
                    color: #ffffff;
                }
            """)
            # unselected - ensure text/emoji are white
            self.label_widget.setStyleSheet("color: #ffffff;")
            self.emoji_label.setStyleSheet("color: #ffffff;")
    
    def update_button_data(self, button_data):
        self.button_data = button_data
        self.emoji_label.setText(button_data.get("icon", "❓"))
        self.label_widget.setText(button_data.get("label", f"Button {self.button_num}"))
    
    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click(self.button_num)
        super().mousePressEvent(event)


class WebDeckGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WebDeck Setup")
        self.setGeometry(100, 100, 1200, 700)
        
        # Load config
        self.config_path = Path(__file__).parent / 'webdeckCfg.json'
        self.config = self.load_config()
        
        # Current selection
        self.selected_button = 0
        self.buttons = self.config.get('buttons', [])
        
        # Create UI
        self.init_ui()
        
        # Select first button by default
        self.select_button(0)
    
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", f"Config file not found: {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", f"Invalid JSON in {self.config_path}")
            sys.exit(1)
    
    def save_config(self):
        """Save configuration to JSON file"""
        # Enforce at least one button exists before saving
        if not self.config.get('buttons') or len(self.config.get('buttons', [])) < 1:
            QMessageBox.critical(self, "Error", "You must have at least one button to save the configuration.")
            return

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "Success", "Configuration saved successfully!")
            # If server is running, request reload; otherwise offer to start
            running = self.is_server_running()
            if running:
                ok, msg = self.request_server_reload()
                if ok:
                    QMessageBox.information(self, 'Server Reload', 'Server reloaded button configuration.')
                else:
                    QMessageBox.warning(self, 'Server Reload', f'Failed to reload server: {msg}')
            else:
                reply = QMessageBox.question(self, 'Server Not Running', 'Server is not running. Start it now?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    self.start_server_process()
                    # after start, attempt reload
                    time.sleep(1.0)
                    ok, msg = self.request_server_reload()
                    if ok:
                        QMessageBox.information(self, 'Server Reload', 'Server started and reloaded button configuration.')
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")
    
    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Left side - Server status + Button grid
        self.left_layout = QVBoxLayout()

        # Server status row
        status_row = QHBoxLayout()
        self.server_status_label = QLabel("Server: Unknown")
        self.server_status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        status_row.addWidget(self.server_status_label)
        status_row.addStretch()
        self.server_action_btn = QPushButton("Start Server")
        self.server_action_btn.setMinimumHeight(28)
        self.server_action_btn.clicked.connect(self.on_server_action_clicked)
        status_row.addWidget(self.server_action_btn)
        self.left_layout.addLayout(status_row)

        left_label = QLabel("Select Button")
        left_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.left_layout.addWidget(left_label)

        # Grid for buttons
        self.button_grid = QGridLayout()
        self.button_grid.setSpacing(10)
        self.button_widgets = []

        self.left_layout.addLayout(self.button_grid)
        self.left_layout.addStretch()
        
        # Right side - Button configuration
        right_layout = QVBoxLayout()
        
        # Button number display
        self.button_num_label = QLabel(f"Button #{self.selected_button}")
        self.button_num_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        right_layout.addWidget(self.button_num_label)
        
        # Title section
        right_layout.addWidget(QLabel("Title"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Button title")
        self.title_input.textChanged.connect(self.on_title_changed)
        right_layout.addWidget(self.title_input)
        
        # Action section
        right_layout.addWidget(QLabel("Action"))
        self.action_combo = QComboBox()
        builtins = [
            "example",
            "open_app",
            "toggle_mute",
            "pause_media",
            "skip_track",
            "previous_track",
            "open_url",
            "lock_screen"
        ]
        # Add built-in actions first
        for b in builtins:
            self.action_combo.addItem(b)

        # Add plugin actions with marker
        try:
            for pa in sorted(PLUGIN_ACTIONS.keys()):
                display = f"[PLUGIN] {pa}"
                self.action_combo.addItem(display)
        except Exception:
            pass

        self.action_combo.currentTextChanged.connect(self.on_action_changed)
        right_layout.addWidget(self.action_combo)
        
        # Path section (for open_app and open_url)
        right_layout.addWidget(QLabel("Path/URL"))
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Application path or URL")
        self.path_input.textChanged.connect(self.on_path_changed)
        right_layout.addWidget(self.path_input)
        
        # Emoji section
        right_layout.addWidget(QLabel("Emoji"))
        emoji_layout = QHBoxLayout()
        self.emoji_display = QLabel()
        self.emoji_display.setFont(QFont("Arial", 32))
        self.emoji_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emoji_display.setMinimumHeight(50)
        emoji_btn = QPushButton("Pick Emoji")
        emoji_btn.clicked.connect(self.pick_emoji)
        emoji_layout.addWidget(self.emoji_display)
        emoji_layout.addWidget(emoji_btn)
        right_layout.addLayout(emoji_layout)
        
        right_layout.addStretch()
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        add_btn = QPushButton("Add Button")
        add_btn.setMinimumHeight(40)
        add_btn.clicked.connect(self.add_button)

        remove_btn = QPushButton("Remove Button")
        remove_btn.setMinimumHeight(40)
        remove_btn.clicked.connect(self.remove_button)
        self.remove_btn = remove_btn

        reset_btn = QPushButton("Reset")
        reset_btn.setMinimumHeight(40)
        reset_btn.clicked.connect(self.reset_button_config)

        save_btn = QPushButton("Save Configuration")
        save_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.save_config)

        bottom_layout.addWidget(add_btn)
        bottom_layout.addWidget(remove_btn)
        bottom_layout.addWidget(reset_btn)
        bottom_layout.addWidget(save_btn)
        right_layout.addLayout(bottom_layout)
        
        # Add sections to main layout
        main_layout.addLayout(self.left_layout, 1)
        main_layout.addLayout(right_layout, 1)
        
        central_widget.setLayout(main_layout)
        
            # Render initial grid
        self.render_button_grid()
        self.update_remove_button_state()

            # Update server status in background
        threading.Thread(target=self.async_update_server_status, daemon=True).start()
        # Immediate status probe so UI updates quickly
        try:
            self.update_server_status_ui(self.is_server_running())
        except Exception:
            pass

        # -- Server integration helpers run as methods defined on the class below --
    
    def select_button(self, button_num):
        """Select a button and update the UI"""
        # Deselect previous
        if hasattr(self, 'button_widgets') and self.selected_button < len(self.button_widgets):
            self.button_widgets[self.selected_button].set_selected(False)
        
        # Select new
        self.selected_button = button_num
        self.button_widgets[button_num].set_selected(True)
        
        # Update UI
        button_data = self.buttons[button_num]
        self.button_num_label.setText(f"Button #{button_num}")
        self.title_input.blockSignals(True)
        self.title_input.setText(button_data.get("label", f"Button {button_num}"))
        self.title_input.blockSignals(False)
        
        self.action_combo.blockSignals(True)
        stored_action = button_data.get("action", "example")
        # If stored action is provided by a plugin, display with marker
        display_action = stored_action
        try:
            if stored_action in PLUGIN_ACTIONS:
                display_action = f"[PLUGIN] {stored_action}"
        except Exception:
            pass
        self.action_combo.setCurrentText(display_action)
        self.action_combo.blockSignals(False)
        
        self.path_input.blockSignals(True)
        self.path_input.setText(button_data.get("path", ""))
        self.path_input.blockSignals(False)
        
        self.emoji_display.setText(button_data.get("icon", "❓"))

    def render_button_grid(self):
        """Render (or re-render) the button grid from self.buttons"""
        # Clear existing widgets from grid
        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)

        clear_layout(self.button_grid)
        self.button_widgets = []

        for i in range(len(self.buttons)):
            btn_widget = ButtonConfigWidget(i, self.buttons[i], self.select_button)
            self.button_widgets.append(btn_widget)
            self.button_grid.addWidget(btn_widget, i // 4, i % 4)

        # If selected index out of range, clamp
        if self.selected_button >= len(self.button_widgets):
            self.selected_button = max(0, len(self.button_widgets) - 1)

        # Update selection visuals
        for idx, w in enumerate(self.button_widgets):
            w.set_selected(idx == self.selected_button)

    # -- Server integration helpers --
    def is_server_running(self, host='http://localhost:8001'):
        paths = ['/status', '/discover']
        hosts = [host, host.replace('localhost', '127.0.0.1')]
        for h in hosts:
            for p in paths:
                try:
                    req = urllib.request.Request(h + p)
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        if 200 <= resp.status < 300:
                            return True
                except Exception:
                    continue
        return False

    def async_update_server_status(self):
        # Periodically check server status and update UI
        while True:
            running = self.is_server_running()
            self.update_server_status_ui(running)
            time.sleep(3)

    def update_server_status_ui(self, running: bool):
        # Called from background thread; post to main thread via Qt
        def apply_status():
            if running:
                self.server_status_label.setText('Server: Running')
                self.server_action_btn.setText('Restart Server')
            else:
                self.server_status_label.setText('Server: Stopped')
                self.server_action_btn.setText('Start Server')
        try:
            # Use Qt single-shot to ensure runs on GUI thread
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, apply_status)
        except Exception:
            pass

    def on_server_action_clicked(self):
        running = self.is_server_running()
        if running:
            # Restart: ask user
            reply = QMessageBox.question(self, 'Restart Server', 'Restart the server?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Attempt to start a new process (best-effort)
            self.start_server_process()
        else:
            reply = QMessageBox.question(self, 'Start Server', 'Start the WebDeck server now?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.start_server_process()

    def start_server_process(self):
        """Start the server process (best-effort, detached)"""
        server_path = Path(__file__).parent / 'webDeck.py'
        if not server_path.exists():
            QMessageBox.critical(self, 'Error', f'Server script not found: {server_path}')
            return

        try:
            # Launch a detached process
            creationflags = 0
            if os.name == 'nt':
                creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            subprocess.Popen([sys.executable, str(server_path)], cwd=str(server_path.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
            # Give server a moment to start
            time.sleep(1.0)
            self.update_server_status_ui(self.is_server_running())
            QMessageBox.information(self, 'Server', 'Server start requested (check tray/console).')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to start server: {e}')

    def request_server_reload(self):
        """Ask the server to reload its button configuration"""
        try:
            req = urllib.request.Request('http://localhost:8001/reload', data=b'{}', method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return True, resp.read().decode('utf-8')
                return False, resp.read().decode('utf-8')
        except urllib.error.URLError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def add_button(self):
        """Add a new default button and re-render grid"""
        new_button = {
            "label": f"Button {len(self.buttons)}",
            "icon": "❓",
            "action": "example"
        }
        self.buttons.append(new_button)
        self.config['buttons'] = self.buttons
        self.render_button_grid()
        # Select the new button
        self.select_button(len(self.buttons) - 1)
        self.update_remove_button_state()

    def remove_button(self):
        """Remove the currently selected button after confirmation"""
        if not self.buttons:
            return

        reply = QMessageBox.question(self, "Confirm Remove",
                                     f"Remove {self.buttons[self.selected_button].get('label', 'this button')}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Remove
        self.buttons.pop(self.selected_button)
        self.config['buttons'] = self.buttons

        # Clamp selection
        if self.selected_button >= len(self.buttons):
            self.selected_button = max(0, len(self.buttons) - 1)

        self.render_button_grid()
        if self.buttons:
            self.select_button(self.selected_button)
        else:
            # Clear fields when no buttons
            self.button_num_label.setText("Button #")
            self.title_input.setText("")
            self.action_combo.setCurrentText("example")
            self.path_input.setText("")
            self.emoji_display.setText("")

        self.update_remove_button_state()

    def update_remove_button_state(self):
        """Disable remove button if only one or zero buttons remain"""
        if hasattr(self, 'remove_btn'):
            self.remove_btn.setEnabled(len(self.buttons) > 1)
    
    def on_title_changed(self, text):
        """Update button title"""
        self.buttons[self.selected_button]["label"] = text
        self.button_widgets[self.selected_button].update_button_data(self.buttons[self.selected_button])
        self.config['buttons'] = self.buttons
    
    def on_action_changed(self, text):
        """Update button action"""
        # Strip plugin marker when storing
        if isinstance(text, str) and text.startswith('[PLUGIN] '):
            action_value = text[len('[PLUGIN] '):]
        else:
            action_value = text
        self.buttons[self.selected_button]["action"] = action_value
        self.config['buttons'] = self.buttons
    
    def on_path_changed(self, text):
        """Update button path/URL"""
        if text:
            self.buttons[self.selected_button]["path"] = text
        else:
            self.buttons[self.selected_button].pop("path", None)
        self.config['buttons'] = self.buttons
    
    def pick_emoji(self):
        """Open emoji picker dialog"""
        current_emoji = self.buttons[self.selected_button].get("icon", "❓")
        dialog = EmojiPickerDialog(self, current_emoji)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_emoji = dialog.get_emoji()
            self.buttons[self.selected_button]["icon"] = selected_emoji
            self.emoji_display.setText(selected_emoji)
            self.button_widgets[self.selected_button].update_button_data(self.buttons[self.selected_button])
            self.config['buttons'] = self.buttons
    
    def reset_button_config(self):
        """Reset button configuration"""
        reply = QMessageBox.question(self, "Confirm Reset", 
                                     "Are you sure you want to reset this button to defaults?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.buttons[self.selected_button] = {
                "label": f"Button {self.selected_button}",
                "icon": "❓",
                "action": "example"
            }
            self.config['buttons'] = self.buttons
            self.select_button(self.selected_button)


def main():
    app = QApplication(sys.argv)
    window = WebDeckGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
