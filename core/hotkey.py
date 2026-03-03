"""Global hotkey listener using pynput.

Maps user-friendly key names (e.g. "F10", "Ctrl+Shift+S") to pynput format
and emits a Qt signal when the hotkey is pressed.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from pynput import keyboard

# Map friendly names → pynput Key objects
_SPECIAL_KEYS: dict[str, keyboard.Key] = {
    f"F{i}": getattr(keyboard.Key, f"f{i}") for i in range(1, 21)
}
_SPECIAL_KEYS.update({
    "ESC": keyboard.Key.esc,
    "TAB": keyboard.Key.tab,
    "SPACE": keyboard.Key.space,
    "ENTER": keyboard.Key.enter,
    "BACKSPACE": keyboard.Key.backspace,
    "DELETE": keyboard.Key.delete,
    "INSERT": keyboard.Key.insert,
    "HOME": keyboard.Key.home,
    "END": keyboard.Key.end,
    "PAGEUP": keyboard.Key.page_up,
    "PAGEDOWN": keyboard.Key.page_down,
    "UP": keyboard.Key.up,
    "DOWN": keyboard.Key.down,
    "LEFT": keyboard.Key.left,
    "RIGHT": keyboard.Key.right,
    "PRINTSCREEN": keyboard.Key.print_screen,
    "PAUSE": keyboard.Key.pause,
    "SCROLLLOCK": keyboard.Key.scroll_lock,
    "NUMLOCK": keyboard.Key.num_lock,
    "CAPSLOCK": keyboard.Key.caps_lock,
    "MENU": keyboard.Key.menu,
})

_MODIFIERS: dict[str, keyboard.Key] = {
    "CTRL":  keyboard.Key.ctrl_l,
    "ALT":   keyboard.Key.alt_l,
    "SHIFT": keyboard.Key.shift,
    "SUPER": keyboard.Key.cmd,
    "WIN":   keyboard.Key.cmd,
    "META":  keyboard.Key.cmd,
}


def _parse_hotkey(hotkey_str: str) -> tuple[set, keyboard.Key | keyboard.KeyCode | None]:
    """Parse 'Ctrl+Shift+F10' → (modifier set, main key)."""
    parts = [p.strip().upper() for p in hotkey_str.split("+")]
    modifiers: set = set()
    main_key = None

    for part in parts:
        if part in _MODIFIERS:
            modifiers.add(_MODIFIERS[part])
        elif part in _SPECIAL_KEYS:
            main_key = _SPECIAL_KEYS[part]
        elif len(part) == 1:
            main_key = keyboard.KeyCode.from_char(part.lower())

    return modifiers, main_key


class HotkeyListener(QObject):
    """Listens for a global hotkey and emits `triggered` signal."""

    triggered = Signal()

    def __init__(self, hotkey_str: str = "F10", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hotkey_str = hotkey_str
        self._modifiers, self._main_key = _parse_hotkey(hotkey_str)
        self._pressed_modifiers: set = set()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def update_hotkey(self, hotkey_str: str) -> None:
        self._hotkey_str = hotkey_str
        self._modifiers, self._main_key = _parse_hotkey(hotkey_str)
        self._pressed_modifiers.clear()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return

        # Track modifiers
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._pressed_modifiers.add(keyboard.Key.ctrl_l)
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self._pressed_modifiers.add(keyboard.Key.alt_l)
        elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._pressed_modifiers.add(keyboard.Key.shift)
        elif key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            self._pressed_modifiers.add(keyboard.Key.cmd)

        # Check if hotkey matches
        if key == self._main_key and self._pressed_modifiers == self._modifiers:
            self.triggered.emit()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._pressed_modifiers.discard(keyboard.Key.ctrl_l)
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self._pressed_modifiers.discard(keyboard.Key.alt_l)
        elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._pressed_modifiers.discard(keyboard.Key.shift)
        elif key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            self._pressed_modifiers.discard(keyboard.Key.cmd)
