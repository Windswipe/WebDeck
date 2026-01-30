from pycaw.pycaw import AudioUtilities
import win32gui
import win32process
import psutil
from windows_toasts import Toast, ToastDuration, ToastScenario, WindowsToaster

notifHost = WindowsToaster("Stream Deck")

def throw_error(message):
    notif = Toast()
    notif.duration = ToastDuration.Short
    notif.scenario = ToastScenario.Important
    notif.text_fields = ["An error was encountered.", message]
    notifHost.show_toast(notif)

def get_foreground_process_name():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            throw_error(f"No foreground window detected.")
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return process.name()
    except (psutil.NoSuchProcess, Exception):
        throw_error(f"Could not get foreground process ID or name. {Exception}")
        return None

def main():
    target = get_foreground_process_name()

    ignored_processes = [
        "WindowsTerminal.exe", 
        "cmd.exe", 
        "powershell.exe", 
        "StreamDeck.exe", 
        "python.exe"
    ]

    if not target or target in ignored_processes:
        print(f"Ignored or invalid process: {target}")
        return

    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.name() == target:
            volume = session.SimpleAudioVolume
            current_mute = volume.GetMute()
            volume.SetMute(1 - current_mute, None)
            print(f"Toggled mute for {target}")
            notif = Toast()
            notif.duration = ToastDuration.Short
            #notif.scenario = ToastScenario.Important
            if current_mute:
                notif.text_fields = [f"Button Event", f"Unmuted {target}"]
            else:
                notif.text_fields = [f"Button Event", f"Muted {target}"]
            notifHost.show_toast(notif)

class WebDeckPlugin:
    metadata = {
        "name": "Toggle Mute",
        "author": "Windswipe",
        "version": "1.0",
        "description": "Toggles mute for the foreground application.",
    }
    def MuteForegroundApp(self):
        main()

if __name__ == "__main__":
    main()