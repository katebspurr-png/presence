"""USB HID keyboard report encoder for /dev/hidg0.

Translates text strings into USB HID 8-byte keyboard reports. Handles full
printable ASCII (characters 32–126), backspace, enter, and tab. Supports
persona-driven typo injection using QWERTY-adjacent keys with backspace
correction, and mid-burst thinking pauses at word boundaries.

Report format (8 bytes per event):
  key-down: [modifier, 0x00, keycode, 0x00, 0x00, 0x00, 0x00, 0x00]
  key-up:   [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

Modifier bytes: 0x00 = none, 0x02 = left shift.
"""

import logging
import random
import time

logger = logging.getLogger(__name__)

_MOD_NONE: int = 0x00
_MOD_SHIFT: int = 0x02
_KEY_UP: bytes = bytes(8)


# ---------------------------------------------------------------------------
# Scan code table: char -> (modifier_byte, keycode_byte)
# Covers all printable ASCII (32–126) plus \n, \t, \x08.
# ---------------------------------------------------------------------------

SCAN_CODES: dict[str, tuple[int, int]] = {
    # Lowercase letters (keycodes 0x04–0x1D)
    "a": (_MOD_NONE, 0x04), "b": (_MOD_NONE, 0x05), "c": (_MOD_NONE, 0x06),
    "d": (_MOD_NONE, 0x07), "e": (_MOD_NONE, 0x08), "f": (_MOD_NONE, 0x09),
    "g": (_MOD_NONE, 0x0A), "h": (_MOD_NONE, 0x0B), "i": (_MOD_NONE, 0x0C),
    "j": (_MOD_NONE, 0x0D), "k": (_MOD_NONE, 0x0E), "l": (_MOD_NONE, 0x0F),
    "m": (_MOD_NONE, 0x10), "n": (_MOD_NONE, 0x11), "o": (_MOD_NONE, 0x12),
    "p": (_MOD_NONE, 0x13), "q": (_MOD_NONE, 0x14), "r": (_MOD_NONE, 0x15),
    "s": (_MOD_NONE, 0x16), "t": (_MOD_NONE, 0x17), "u": (_MOD_NONE, 0x18),
    "v": (_MOD_NONE, 0x19), "w": (_MOD_NONE, 0x1A), "x": (_MOD_NONE, 0x1B),
    "y": (_MOD_NONE, 0x1C), "z": (_MOD_NONE, 0x1D),
    # Uppercase letters (same keycodes, left-shift modifier)
    "A": (_MOD_SHIFT, 0x04), "B": (_MOD_SHIFT, 0x05), "C": (_MOD_SHIFT, 0x06),
    "D": (_MOD_SHIFT, 0x07), "E": (_MOD_SHIFT, 0x08), "F": (_MOD_SHIFT, 0x09),
    "G": (_MOD_SHIFT, 0x0A), "H": (_MOD_SHIFT, 0x0B), "I": (_MOD_SHIFT, 0x0C),
    "J": (_MOD_SHIFT, 0x0D), "K": (_MOD_SHIFT, 0x0E), "L": (_MOD_SHIFT, 0x0F),
    "M": (_MOD_SHIFT, 0x10), "N": (_MOD_SHIFT, 0x11), "O": (_MOD_SHIFT, 0x12),
    "P": (_MOD_SHIFT, 0x13), "Q": (_MOD_SHIFT, 0x14), "R": (_MOD_SHIFT, 0x15),
    "S": (_MOD_SHIFT, 0x16), "T": (_MOD_SHIFT, 0x17), "U": (_MOD_SHIFT, 0x18),
    "V": (_MOD_SHIFT, 0x19), "W": (_MOD_SHIFT, 0x1A), "X": (_MOD_SHIFT, 0x1B),
    "Y": (_MOD_SHIFT, 0x1C), "Z": (_MOD_SHIFT, 0x1D),
    # Digits
    "1": (_MOD_NONE, 0x1E), "2": (_MOD_NONE, 0x1F), "3": (_MOD_NONE, 0x20),
    "4": (_MOD_NONE, 0x21), "5": (_MOD_NONE, 0x22), "6": (_MOD_NONE, 0x23),
    "7": (_MOD_NONE, 0x24), "8": (_MOD_NONE, 0x25), "9": (_MOD_NONE, 0x26),
    "0": (_MOD_NONE, 0x27),
    # Shifted-digit symbols
    "!": (_MOD_SHIFT, 0x1E), "@": (_MOD_SHIFT, 0x1F), "#": (_MOD_SHIFT, 0x20),
    "$": (_MOD_SHIFT, 0x21), "%": (_MOD_SHIFT, 0x22), "^": (_MOD_SHIFT, 0x23),
    "&": (_MOD_SHIFT, 0x24), "*": (_MOD_SHIFT, 0x25), "(": (_MOD_SHIFT, 0x26),
    ")": (_MOD_SHIFT, 0x27),
    # Special keys
    "\n":   (_MOD_NONE,  0x28),  # Enter
    "\x08": (_MOD_NONE,  0x2A),  # Backspace
    "\t":   (_MOD_NONE,  0x2B),  # Tab
    " ":    (_MOD_NONE,  0x2C),  # Space
    # Unshifted punctuation
    "-":  (_MOD_NONE,  0x2D), "=":  (_MOD_NONE,  0x2E),
    "[":  (_MOD_NONE,  0x2F), "]":  (_MOD_NONE,  0x30),
    "\\": (_MOD_NONE,  0x31), ";":  (_MOD_NONE,  0x33),
    "'":  (_MOD_NONE,  0x34), "`":  (_MOD_NONE,  0x35),
    ",":  (_MOD_NONE,  0x36), ".":  (_MOD_NONE,  0x37),
    "/":  (_MOD_NONE,  0x38),
    # Shifted punctuation
    "_":  (_MOD_SHIFT, 0x2D), "+":  (_MOD_SHIFT, 0x2E),
    "{":  (_MOD_SHIFT, 0x2F), "}":  (_MOD_SHIFT, 0x30),
    "|":  (_MOD_SHIFT, 0x31), ":":  (_MOD_SHIFT, 0x33),
    '"':  (_MOD_SHIFT, 0x34), "~":  (_MOD_SHIFT, 0x35),
    "<":  (_MOD_SHIFT, 0x36), ">":  (_MOD_SHIFT, 0x37),
    "?":  (_MOD_SHIFT, 0x38),
}


# ---------------------------------------------------------------------------
# QWERTY adjacency map: char -> list of physically adjacent key characters.
# All values are chars present in SCAN_CODES — safe to look up without guards.
# Used for realistic typo injection: every key in SCAN_CODES has an entry.
# ---------------------------------------------------------------------------

ADJACENT_KEYS: dict[str, list[str]] = {
    # Lowercase letters
    "q": ["w", "a", "1", "2"],
    "w": ["q", "e", "a", "s", "2", "3"],
    "e": ["w", "r", "s", "d", "3", "4"],
    "r": ["e", "t", "d", "f", "4", "5"],
    "t": ["r", "y", "f", "g", "5", "6"],
    "y": ["t", "u", "g", "h", "6", "7"],
    "u": ["y", "i", "h", "j", "7", "8"],
    "i": ["u", "o", "j", "k", "8", "9"],
    "o": ["i", "p", "k", "l", "9", "0"],
    "p": ["o", "[", "l", ";", "0", "-"],
    "a": ["q", "w", "s", "z"],
    "s": ["a", "w", "e", "d", "z", "x"],
    "d": ["s", "e", "r", "f", "x", "c"],
    "f": ["d", "r", "t", "g", "c", "v"],
    "g": ["f", "t", "y", "h", "v", "b"],
    "h": ["g", "y", "u", "j", "b", "n"],
    "j": ["h", "u", "i", "k", "n", "m"],
    "k": ["j", "i", "o", "l", "m", ","],
    "l": ["k", "o", "p", ";", ",", "."],
    "z": ["a", "s", "x"],
    "x": ["z", "s", "d", "c"],
    "c": ["x", "d", "f", "v"],
    "v": ["c", "f", "g", "b"],
    "b": ["v", "g", "h", "n", " "],
    "n": ["b", "h", "j", "m", " "],
    "m": ["n", "j", "k", ",", " "],
    # Uppercase letters (same physical positions, uppercase adjacents)
    "Q": ["W", "A", "1", "2"],
    "W": ["Q", "E", "A", "S", "2", "3"],
    "E": ["W", "R", "S", "D", "3", "4"],
    "R": ["E", "T", "D", "F", "4", "5"],
    "T": ["R", "Y", "F", "G", "5", "6"],
    "Y": ["T", "U", "G", "H", "6", "7"],
    "U": ["Y", "I", "H", "J", "7", "8"],
    "I": ["U", "O", "J", "K", "8", "9"],
    "O": ["I", "P", "K", "L", "9", "0"],
    "P": ["O", "{", "L", ":", "0", "_"],
    "A": ["Q", "W", "S", "Z"],
    "S": ["A", "W", "E", "D", "Z", "X"],
    "D": ["S", "E", "R", "F", "X", "C"],
    "F": ["D", "R", "T", "G", "C", "V"],
    "G": ["F", "T", "Y", "H", "V", "B"],
    "H": ["G", "Y", "U", "J", "B", "N"],
    "J": ["H", "U", "I", "K", "N", "M"],
    "K": ["J", "I", "O", "L", "M", "<"],
    "L": ["K", "O", "P", ":", "<", ">"],
    "Z": ["A", "S", "X"],
    "X": ["Z", "S", "D", "C"],
    "C": ["X", "D", "F", "V"],
    "V": ["C", "F", "G", "B"],
    "B": ["V", "G", "H", "N", " "],
    "N": ["B", "H", "J", "M", " "],
    "M": ["N", "J", "K", "<", " "],
    # Digits
    "1": ["2", "q", "`"],
    "2": ["1", "3", "q", "w"],
    "3": ["2", "4", "w", "e"],
    "4": ["3", "5", "e", "r"],
    "5": ["4", "6", "r", "t"],
    "6": ["5", "7", "t", "y"],
    "7": ["6", "8", "y", "u"],
    "8": ["7", "9", "u", "i"],
    "9": ["8", "0", "i", "o"],
    "0": ["9", "-", "o", "p"],
    # Shifted digit symbols
    "!": ["@", "Q", "W", "~"],
    "@": ["!", "#", "Q", "W", "E"],
    "#": ["@", "$", "W", "E", "R"],
    "$": ["#", "%", "E", "R", "T"],
    "%": ["$", "^", "R", "T", "Y"],
    "^": ["%", "&", "T", "Y", "U"],
    "&": ["^", "*", "Y", "U", "I"],
    "*": ["&", "(", "U", "I", "O"],
    "(": ["*", ")", "I", "O", "P"],
    ")": ["(", "O", "P", "{"],
    # Special keys
    "\n":   ["'", "]", "\\"],
    "\x08": ["=", "]"],
    "\t":   ["`", "q", "1"],
    " ":    ["b", "v", "n", "m", "c"],
    # Unshifted punctuation
    "-":  ["0", "=", "p", "["],
    "=":  ["-", "]", "[", "\x08"],
    "[":  ["p", "]", "-", ";", "o"],
    "]":  ["[", "\\", "l", ";", "\n"],
    "\\": ["]", "'", "\n"],
    ";":  ["l", "'", "p", "[", ",", "."],
    "'":  [";", "[", "\\", "\n"],
    "`":  ["1", "\t"],
    ",":  ["m", "k", "l", ".", " "],
    ".":  [",", "l", ";", "/"],
    "/":  [".", ";", "'"],
    # Shifted punctuation
    "_":  [")", "P", "{", "+"],
    "+":  ["_", "}", "{", "\x08"],
    "{":  ["P", "}", "_", ":"],
    "}":  ["{", "|", "L", ":"],
    "|":  ["}", '"', "\n"],
    ":":  ["L", '"', "P", "{", "<"],
    '"':  [":", "|", "\n"],
    "~":  ["!", "\t"],
    "<":  ["M", "K", "L", ">", " "],
    ">":  ["<", "L", ":", "?"],
    "?":  [">", ":", '"'],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_key(hid_file, char: str) -> None:
    """Write one key-down + key-up report pair. No-op if hid_file is None."""
    if hid_file is None or char not in SCAN_CODES:
        return
    modifier, keycode = SCAN_CODES[char]
    try:
        hid_file.write(bytes([modifier, 0x00, keycode, 0x00, 0x00, 0x00, 0x00, 0x00]))
        hid_file.flush()
        hid_file.write(_KEY_UP)
        hid_file.flush()
    except OSError as e:
        logger.warning(f"hid_key_write_error={e!r}")


def _jittered_delay(base_s: float) -> float:
    """Inter-key delay with ±15% Gaussian jitter, clamped to [0.5x, 2.0x] of base."""
    return base_s * max(0.5, min(2.0, random.gauss(1.0, 0.15)))


def _interruptible_pause(duration_s: float, control) -> None:
    """Sleep for duration_s, waking early if control.stopped or control.paused fires."""
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        if control.stopped.is_set() or control.paused.is_set():
            break
        time.sleep(min(0.1, end - time.monotonic()))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_string(
    text: str,
    wpm: int,
    typo_rate: float,
    thinking_pause_p: float,
    thinking_pause_mean_s: float,
    control,
    hid_path: str | None = None,
) -> None:
    """Type text as USB HID keyboard reports to hid_path.

    Args:
        text: The string to type. Characters not in SCAN_CODES are silently skipped.
        wpm: Typing speed in words per minute (1 word = 5 characters).
        typo_rate: Per-character probability of injecting a QWERTY-adjacent typo
            followed by a backspace before the correct key.
        thinking_pause_p: Probability of a pause after each word boundary
            (space or newline character).
        thinking_pause_mean_s: Mean duration of thinking pauses in seconds.
        control: EngineControl instance — checked between every keystroke.
            Exits cleanly on stop or pause without raising.
        hid_path: Path to the HID keyboard gadget device (e.g. /dev/hidg0), or
            None for a dry run where timing runs but nothing is written.
            OSError on open is logged and silently skipped.
    """
    hid_file = None
    if hid_path is not None:
        try:
            hid_file = open(hid_path, "wb")
        except OSError as e:
            logger.warning(f"hid_keyboard_unavailable path={hid_path} error={e!r}")

    try:
        # Base delay: 60s / (wpm * 5 chars/word)
        base_delay_s = 60.0 / (max(1, wpm) * 5)

        for char in text:
            if control.stopped.is_set() or control.paused.is_set():
                break

            if char not in SCAN_CODES:
                continue

            # Typo injection: write adjacent key + backspace before correct key
            if typo_rate > 0 and random.random() < typo_rate:
                candidates = [c for c in ADJACENT_KEYS.get(char, []) if c in SCAN_CODES]
                if candidates:
                    _write_key(hid_file, random.choice(candidates))
                    time.sleep(_jittered_delay(base_delay_s))
                    _write_key(hid_file, "\x08")
                    time.sleep(_jittered_delay(base_delay_s))

            _write_key(hid_file, char)

            # Thinking pause after word boundaries
            if char in (" ", "\n") and thinking_pause_p > 0 and random.random() < thinking_pause_p:
                pause_s = max(0.3, random.gauss(thinking_pause_mean_s, thinking_pause_mean_s * 0.3))
                _interruptible_pause(pause_s, control)
            else:
                time.sleep(_jittered_delay(base_delay_s))

    finally:
        if hid_file is not None:
            hid_file.close()
