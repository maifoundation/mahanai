"""Tool definitions and execution for the MahanAI agent."""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from mahanai import colors as C

_JSON_BAD_BACKSLASH = re.compile(r'\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})')

# ── Autonomous mode ───────────────────────────────────────────────────────────
_AUTONOMOUS_MODE: bool = False


def set_autonomous_mode(enabled: bool) -> None:
    global _AUTONOMOUS_MODE
    _AUTONOMOUS_MODE = enabled


def is_autonomous_mode() -> bool:
    return _AUTONOMOUS_MODE


def repair_invalid_json_escapes(raw: str) -> str:
    s = raw
    for _ in range(128):
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError:
            nxt = _JSON_BAD_BACKSLASH.sub(r"\\\\", s)
            if nxt == s:
                return s
            s = nxt
    return s


def normalize_tool_arguments_json(arguments: str) -> str:
    """Parse model tool arguments and re-serialize as valid JSON for the API and executor."""
    raw = (arguments or "").strip() or "{}"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        try:
            obj = json.loads(repair_invalid_json_escapes(raw))
        except json.JSONDecodeError:
            return "{}"
    if not isinstance(obj, dict):
        return "{}"
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _can_import_pyautogui() -> bool:
    try:
        import pyautogui  # noqa: F401
        return True
    except Exception:
        return False


def _wayland_helpers_available() -> bool:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if not (os.environ.get("WAYLAND_DISPLAY") or session_type == "wayland"):
        return False
    return _command_exists("grim") and _command_exists("ydotool")


def _wayland_screenshot_available() -> bool:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if not (os.environ.get("WAYLAND_DISPLAY") or session_type == "wayland"):
        return False
    return _command_exists("grim")


def _wayland_input_available() -> bool:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if not (os.environ.get("WAYLAND_DISPLAY") or session_type == "wayland"):
        return False
    return _command_exists("ydotool")


def _x11_fallback_available() -> bool:
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        return False
    xauthority = os.environ.get("XAUTHORITY", "").strip()
    if xauthority:
        return Path(xauthority).expanduser().is_file()
    return (Path.home() / ".Xauthority").is_file()


_WAYLAND_BUTTON_CODES = {
    "left": "0xC0",
    "middle": "0xC2",
    "right": "0xC1",
}

_WAYLAND_KEY_CODES = {
    "esc": 1,
    "escape": 1,
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
    "backspace": 14,
    "tab": 15,
    "q": 16,
    "w": 17,
    "e": 18,
    "r": 19,
    "t": 20,
    "y": 21,
    "u": 22,
    "i": 23,
    "o": 24,
    "p": 25,
    "enter": 28,
    "return": 28,
    "ctrl": 29,
    "control": 29,
    "a": 30,
    "s": 31,
    "d": 32,
    "f": 33,
    "g": 34,
    "h": 35,
    "j": 36,
    "k": 37,
    "l": 38,
    "shift": 42,
    "z": 44,
    "x": 45,
    "c": 46,
    "v": 47,
    "b": 48,
    "n": 49,
    "m": 50,
    "alt": 56,
    "space": 57,
    "capslock": 58,
    "f1": 59,
    "f2": 60,
    "f3": 61,
    "f4": 62,
    "f5": 63,
    "f6": 64,
    "f7": 65,
    "f8": 66,
    "f9": 67,
    "f10": 68,
    "numlock": 69,
    "scrolllock": 70,
    "f11": 87,
    "f12": 88,
    "home": 102,
    "up": 103,
    "pageup": 104,
    "left": 105,
    "right": 106,
    "end": 107,
    "down": 108,
    "pagedown": 109,
    "insert": 110,
    "delete": 111,
    "super": 125,
    "meta": 125,
}


def _wayland_key_code(key: str) -> int | None:
    cleaned = key.strip().lower().replace(" ", "_").replace("-", "_")
    if len(cleaned) == 1 and cleaned in _WAYLAND_KEY_CODES:
        return _WAYLAND_KEY_CODES[cleaned]
    return _WAYLAND_KEY_CODES.get(cleaned)


def _wayland_key_sequence(keys: list[str], *, press_and_release: bool = True) -> list[str]:
    codes: list[int] = []
    for key in keys:
        code = _wayland_key_code(str(key))
        if code is None:
            raise ValueError(f"unsupported Wayland key: {key}")
        codes.append(code)

    seq: list[str] = []
    if press_and_release:
        for code in codes:
            seq.append(f"{code}:1")
        for code in reversed(codes):
            seq.append(f"{code}:0")
    else:
        for code in codes:
            seq.append(f"{code}:1")
    return seq


def _run_wayland_command(args: list[str], *, timeout: int = 15) -> None:
    subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)


class _InteractBackend:
    kind = "base"

    def __init__(self, base: Path):
        self.base = base

    def _screenshot_path(self) -> Path:
        ts = time.strftime("%Y%m%d-%H%M%S")
        return self.base / f".mahanai-interact-{ts}.png"

    def screenshot(self) -> dict[str, Any]:
        raise NotImplementedError

    def move_mouse(self, x: int, y: int) -> dict[str, Any]:
        raise NotImplementedError

    def click(self, args: dict[str, object]) -> dict[str, Any]:
        raise NotImplementedError

    def double_click(self, args: dict[str, object]) -> dict[str, Any]:
        raise NotImplementedError

    def right_click(self, args: dict[str, object]) -> dict[str, Any]:
        raise NotImplementedError

    def drag(self, args: dict[str, object]) -> dict[str, Any]:
        raise NotImplementedError

    def scroll(self, dy: int) -> dict[str, Any]:
        raise NotImplementedError

    def type_text(self, text: str) -> dict[str, Any]:
        raise NotImplementedError

    def press_key(self, key: str) -> dict[str, Any]:
        raise NotImplementedError

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        raise NotImplementedError

    def sleep(self, seconds: float) -> dict[str, Any]:
        time.sleep(max(0.0, float(seconds)))
        return {"ok": True, "action": "sleep"}


class _X11InteractBackend(_InteractBackend):
    kind = "x11"

    def __init__(self, base: Path):
        super().__init__(base)
        self._pyautogui = None

    def _pyautogui_module(self):
        if self._pyautogui is None:
            import pyautogui

            self._pyautogui = pyautogui
            try:
                self._pyautogui.FAILSAFE = True
                self._pyautogui.PAUSE = 0.05
            except Exception:
                pass
        return self._pyautogui

    def screenshot(self) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        img = pyautogui.screenshot()
        path = self._screenshot_path()
        img.save(path)
        return {"ok": True, "path": str(path), "size": [img.size[0], img.size[1]]}

    def move_mouse(self, x: int, y: int) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.moveTo(int(x), int(y), duration=0.15)
        return {"ok": True, "action": "move_mouse"}

    def click(self, args: dict[str, object]) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.click(
            x=args.get("x"),
            y=args.get("y"),
            clicks=int(args.get("clicks") or 1),
            button=str(args.get("button") or "left"),
        )
        return {"ok": True, "action": "click"}

    def double_click(self, args: dict[str, object]) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.doubleClick(x=args.get("x"), y=args.get("y"), button=str(args.get("button") or "left"))
        return {"ok": True, "action": "double_click"}

    def right_click(self, args: dict[str, object]) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.rightClick(x=args.get("x"), y=args.get("y"))
        return {"ok": True, "action": "right_click"}

    def drag(self, args: dict[str, object]) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.dragTo(int(args.get("x", 0)), int(args.get("y", 0)), duration=0.3, button=str(args.get("button") or "left"))
        return {"ok": True, "action": "drag"}

    def scroll(self, dy: int) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.scroll(int(dy))
        return {"ok": True, "action": "scroll"}

    def type_text(self, text: str) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.write(str(text), interval=0.01)
        return {"ok": True, "action": "type_text"}

    def press_key(self, key: str) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.press(str(key))
        return {"ok": True, "action": "press_key"}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        pyautogui = self._pyautogui_module()
        pyautogui.hotkey(*[str(k) for k in keys])
        return {"ok": True, "action": "hotkey", "keys": [str(k) for k in keys]}


class _WaylandInteractBackend(_InteractBackend):
    kind = "wayland"

    def screenshot(self) -> dict[str, Any]:
        path = self._screenshot_path()
        _run_wayland_command(["grim", str(path)])
        return {"ok": True, "path": str(path), "size": None}

    def move_mouse(self, x: int, y: int) -> dict[str, Any]:
        _run_wayland_command(["ydotool", "mousemove", "--absolute", "-x", str(int(x)), "-y", str(int(y))])
        return {"ok": True, "action": "move_mouse"}

    def click(self, args: dict[str, object]) -> dict[str, Any]:
        button = str(args.get("button") or "left").strip().lower()
        clicks = max(1, int(args.get("clicks") or 1))
        code = _WAYLAND_BUTTON_CODES.get(button, _WAYLAND_BUTTON_CODES["left"])
        if clicks > 1:
            _run_wayland_command(["ydotool", "click", "--repeat", str(clicks), "--next-delay", "25", code])
        else:
            _run_wayland_command(["ydotool", "click", code])
        return {"ok": True, "action": "click", "button": button, "clicks": clicks}

    def double_click(self, args: dict[str, object]) -> dict[str, Any]:
        payload = dict(args)
        payload["clicks"] = 2
        return self.click(payload)

    def right_click(self, args: dict[str, object]) -> dict[str, Any]:
        payload = dict(args)
        payload["button"] = "right"
        return self.click(payload)

    def drag(self, args: dict[str, object]) -> dict[str, Any]:
        # ydotool can move and click reliably; drag support is best-effort and
        # falls back to X11 if available for the current session.
        if _can_import_pyautogui():
            return _X11InteractBackend(self.base).drag(args)
        return {"error": "drag is not supported by the available Wayland helpers"}

    def scroll(self, dy: int) -> dict[str, Any]:
        if _can_import_pyautogui():
            return _X11InteractBackend(self.base).scroll(dy)
        return {"error": "scroll is not supported by the available Wayland helpers"}

    def type_text(self, text: str) -> dict[str, Any]:
        _run_wayland_command(["ydotool", "type", str(text)])
        return {"ok": True, "action": "type_text"}

    def press_key(self, key: str) -> dict[str, Any]:
        seq = _wayland_key_sequence([key])
        _run_wayland_command(["ydotool", "key", *seq])
        return {"ok": True, "action": "press_key", "key": key}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        seq = _wayland_key_sequence(keys)
        _run_wayland_command(["ydotool", "key", *seq])
        return {"ok": True, "action": "hotkey", "keys": [str(k) for k in keys]}


def _select_interact_backend(base: Path | None = None) -> _InteractBackend:
    base_path = base or Path.cwd()
    if _wayland_helpers_available():
        return _WaylandInteractBackend(base_path)
    if _x11_fallback_available() and _can_import_pyautogui():
        return _X11InteractBackend(base_path)
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").strip().lower() == "wayland":
        if not _wayland_input_available():
            raise RuntimeError(
                "Wayland session detected but ydotool is missing. "
                "Install ydotool (and keep grim for screenshots) or switch to an X11 session with a valid Xauthority file."
            )
    raise RuntimeError("No supported Interact backend is available")


def _interact_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "interact",
            "description": (
                "Use the local computer by taking screenshots and controlling mouse and keyboard. "
                "Prefer Wayland helpers when available, and fall back to X11 pyautogui when not. "
                "Supported actions: screenshot, move_mouse, click, double_click, right_click, drag, "
                "scroll, type_text, press_key, hotkey, sleep."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to perform.",
                    },
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string"},
                    "text": {"type": "string"},
                    "key": {"type": "string"},
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "dx": {"type": "integer"},
                    "dy": {"type": "integer"},
                    "clicks": {"type": "integer"},
                    "seconds": {"type": "number"},
                },
                "required": ["action"],
            },
        },
    }


def get_tools() -> list[dict[str, Any]]:
    from mahanai.config import load_interact_enabled

    tools = list(TOOLS) + list(CONNECT_TOOLS)
    if load_interact_enabled():
        tools.append(_interact_tool())
    return tools


CONNECT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "connect_get_config_view",
            "description": "Return a sanitized view of MahanAI config and active connect grants. Secrets are omitted.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "connect_request_config_change",
            "description": "Request approved changes to non-secret MahanAI config fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "changes": {
                        "type": "object",
                        "description": "Non-secret config key/value changes to request.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this config change is needed.",
                    },
                },
                "required": ["changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "connect_run_user_command",
            "description": "Request approved shell command execution through the connect permission path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Full shell command to execute."},
                    "cwd": {"type": "string", "description": "Optional working directory."},
                    "timeout_seconds": {"type": "integer", "description": "Max seconds to wait."},
                    "reason": {"type": "string", "description": "Why this command is needed."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "connect_request_rerun",
            "description": "Generate a rerun handoff request for the user without changing config or running commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "suggested_command": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Execute a shell command now (the user sees ⚡Running: in the terminal). "
                "Do not only show commands in chat—this tool must be called to run them. "
                "On Windows the default shell is usually cmd.exe (COMSPEC), not PowerShell; "
                "use cmd syntax or call powershell -NoProfile -Command \"...\" explicitly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full command line to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory (absolute or relative to cwd).",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 120).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full text of a file (UTF-8).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with UTF-8 text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file contents.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a path (non-recursive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: current working directory).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append UTF-8 text to a file (creates the file if missing).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch the text content of a URL (HTML is stripped to plain text).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python_repl",
            "description": "Execute Python code in an isolated subprocess and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 30).",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Apply a targeted string replacement to an existing file. "
                "Reads the file, finds old_string (must appear exactly once), replaces it with new_string, "
                "shows a diff, then saves. Fails if old_string is not found or appears more than once. "
                "Prefer this over write_file for surgical, line-level edits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to find and replace (must be unique in the file).",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Text to replace old_string with.",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns titles, URLs, and snippets for top results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# ── Approval helpers ───────────────────────────────────────────────────────────

_HIGH_RISK_PATTERNS = [
    re.compile(r"\brm\s+.*(-\s*rf\b|-\s*fr\b|--no-preserve-root)"),
    re.compile(r"\brmdir(\.exe)?\b.*\s/s\b"),
    re.compile(r"\brd(\.exe)?\b.*\s/s\b"),
    re.compile(r"\bdel(\.exe)?\b.*\s/s\b"),
    re.compile(r"\berase(\.exe)?\b.*\s/s\b"),
    re.compile(r"\bformat\s+"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\blogoff\b"),
    re.compile(r"\bhalt\b"),
    re.compile(r"\bpoweroff\b"),
    re.compile(r"\binit\s+0\b"),
    re.compile(r"\bdiskpart\b"),
    re.compile(r"\bmkfs"),
    re.compile(r"\bdd\s+if="),
    re.compile(r":\(\)\s*\{\s*:"),
    re.compile(r"remove-item.*-recurse.*-force"),
]


def _is_high_risk(cmd: str) -> bool:
    low = cmd.strip().lower()
    return any(p.search(low) for p in _HIGH_RISK_PATTERNS)


def _command_category(cmd: str) -> str:
    first = cmd.strip().split()[0].lower().rstrip(".exe") if cmd.strip() else ""
    if first == "git":
        return "git"
    if first == "gh":
        return "github"
    return "normal"


def _command_prefix(cmd: str) -> str:
    return cmd.strip().split()[0].lower() if cmd.strip() else ""


def _read_input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _approve_connect_config(summary: dict[str, Any]) -> str:
    print(f"\n{C.WARN}  Connect Config Change{C.RST}")
    reason = str(summary.get("reason") or "").strip()
    if reason:
        print(f"  {C.DIM}Reason: {reason}{C.RST}")
    for change in summary.get("changes", []):
        key = change.get("key", "")
        before = json.dumps(change.get("before"), sort_keys=True)
        after = json.dumps(change.get("after"), sort_keys=True)
        print(f"  {C.DIM}{key}: {before} -> {after}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow Once    {C.DIM}[S] Allow for Session{C.RST}    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans in ("a", "allow", "allow once", "once"):
        return "allow-once"
    if ans in ("s", "session", "allow session", "allow for session"):
        return "allow-session"
    return "deny"


def _approve_connect_command(summary: dict[str, Any]) -> str:
    high_risk = bool(summary.get("high_risk"))
    print(f"\n{C.WARN}  Connect Command{C.RST}{'  ' + C.ERR + '[DESTRUCTIVE]' + C.RST if high_risk else ''}")
    reason = str(summary.get("reason") or "").strip()
    if reason:
        print(f"  {C.DIM}Reason: {reason}{C.RST}")
    print(f"  {C.DIM}{summary.get('command', '')}{C.RST}")
    print(f"  {C.DIM}cwd: {summary.get('cwd', '')}{C.RST}")
    if high_risk:
        print(f"  {C.OK}[A]{C.RST} Allow Once    {C.ERR}[D]{C.RST} Deny")
    else:
        print(f"  {C.OK}[A]{C.RST} Allow Once    {C.DIM}[S] Allow for Session{C.RST}    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans in ("a", "allow", "allow once", "once"):
        return "allow-once"
    if not high_risk and ans in ("s", "session", "allow session", "allow for session"):
        return "allow-session"
    return "deny"


def _approve_command(cmd: str) -> tuple[bool, str]:
    """
    Show an approval prompt for a shell command.
    Returns (approved, denial_message_for_ai).
    """
    from mahanai.config import load_always_allowed, add_always_allowed_command, load_interact_enabled

    if load_interact_enabled():
        lowered = cmd.lower()
        browser_like = any(
            token in lowered
            for token in (
                "chrome.exe",
                "chrome ",
                "msedge",
                "firefox",
                "start \"\"",
                "start chrome",
                "start msedge",
                "start firefox",
                "https://",
                "http://",
                "www.",
                "where chrome",
                "which chrome",
            )
        )
        if browser_like:
            return False, "Interact is enabled. Use the interact tool for browser/app opening and GUI actions."

    category = _command_category(cmd)
    prefix = _command_prefix(cmd)
    high_risk = _is_high_risk(cmd)

    # Autonomous mode: auto-approve non-destructive commands
    if _AUTONOMOUS_MODE and not high_risk:
        print(f"\n{C.DIM}  [AUTO] {cmd}{C.RST}", flush=True)
        return True, ""

    # Always-Allow only applies to normal (non-git, non-gh) commands
    if category == "normal" and not high_risk:
        always = load_always_allowed()
        if prefix in always.get("command_prefixes", []):
            return True, ""

    # ── Build prompt ──────────────────────────────────────────────────────────
    cat_label = {
        "git":    "Git Command",
        "github": "GitHub Command",
        "normal": "Shell Command",
    }[category]

    risk_tag = f"  {C.ERR}[DESTRUCTIVE]{C.RST}" if high_risk else ""
    print(f"\n{C.WARN}  {cat_label}{C.RST}{risk_tag}")
    print(f"  {C.DIM}{cmd}{C.RST}")

    if category in ("git", "github"):
        print(f"  {C.OK}[A]{C.RST} Allow    {C.ERR}[D]{C.RST} Deny")
        ans = _read_input("  > ")
        approved = ans.lower() in ("a", "allow")
    else:
        # Normal: Allow / Always Allow / Deny
        always_label = f"Always Allow ({prefix})" if not high_risk else "Always Allow (disabled for destructive)"
        if high_risk:
            print(f"  {C.OK}[A]{C.RST} Allow    {C.ERR}[D]{C.RST} Deny")
            ans = _read_input("  > ")
            approved = ans.lower() in ("a", "allow")
        else:
            print(f"  {C.OK}[A]{C.RST} Allow    {C.DIM}[W] {always_label}{C.RST}    {C.ERR}[D]{C.RST} Deny")
            ans = _read_input("  > ").lower()
            if ans in ("w", "always allow", "always"):
                add_always_allowed_command(prefix)
                print(f"  {C.OK}'{prefix}' commands will always be allowed.{C.RST}")
                return True, ""
            approved = ans in ("a", "allow")

    if approved:
        return True, ""

    # Denied — let user send a message to the AI
    msg = _read_input(f"  {C.DIM}Instruction for AI (Enter to skip):{C.RST} ")
    return False, msg or "Command was denied by the user."


def _approve_file_op(op: str, display_path: str) -> tuple[bool, str]:
    """
    Show an approval prompt for a file operation.
    Returns (approved, denial_message_for_ai).
    """
    from mahanai.config import load_always_allowed, add_always_allowed_file_op

    if _AUTONOMOUS_MODE:
        print(f"\n{C.DIM}  [AUTO] {op}: {display_path}{C.RST}", flush=True)
        return True, ""

    always = load_always_allowed()
    if op in always.get("file_ops", []):
        return True, ""

    op_labels = {
        "read_file":      "Read File",
        "write_file":     "Write / Create File",
        "append_file":    "Append to File",
        "list_directory": "List Directory",
    }
    label = op_labels.get(op, op)

    print(f"\n{C.WARN}  {label}{C.RST}")
    print(f"  {C.DIM}{display_path}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow    {C.DIM}[W] Always Allow ({label}){C.RST}    {C.ERR}[D]{C.RST} Deny")

    ans = _read_input("  > ").lower()

    if ans in ("w", "always allow", "always"):
        add_always_allowed_file_op(op)
        print(f"  {C.OK}'{label}' will always be allowed.{C.RST}")
        return True, ""

    if ans in ("a", "allow"):
        return True, ""

    msg = _read_input(f"  {C.DIM}Instruction for AI (Enter to skip):{C.RST} ")
    return False, msg or "File operation was denied by the user."


def _approve_interact(action: str) -> tuple[bool, str]:
    from mahanai.config import load_interact_always_allow, save_interact_always_allow

    if load_interact_always_allow():
        return True, ""

    print(f"\n{C.WARN}  Interact Action{C.RST}")
    print(f"  {C.DIM}{action}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow    {C.DIM}[W] Always Allow Interact{C.RST}    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans in ("w", "always allow", "always"):
        save_interact_always_allow(True)
        print(f"  {C.OK}Interact will always be allowed.{C.RST}")
        return True, ""
    if ans in ("a", "allow"):
        return True, ""
    msg = _read_input(f"  {C.DIM}Instruction for AI (Enter to skip):{C.RST} ")
    return False, msg or "Interact was denied by the user."


# ── Tool implementations ───────────────────────────────────────────────────────

def _resolve_path(base: Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p


def run_command(base: Path, args: dict[str, object]) -> str:
    cmd = str(args.get("command", "")).strip()
    if not cmd:
        return json.dumps({"error": "empty command"})
    cwd_raw = args.get("cwd")
    timeout = int(args.get("timeout_seconds") or 120)
    cwd = base
    if isinstance(cwd_raw, str) and cwd_raw.strip():
        cwd = _resolve_path(base, cwd_raw)

    approved, denial_msg = _approve_command(cmd)
    if not approved:
        return json.dumps({
            "exit_code": -1,
            "error": "user_denied",
            "message": denial_msg,
            "command": cmd,
            "output": denial_msg,
            "cwd": str(cwd),
        })

    print(f"\n{C.OK}⚡Running:{C.RST} {cmd}", flush=True)
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            env=os.environ.copy(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > 100_000:
            out = out[:100_000] + "\n… [truncated]"
        return json.dumps({"exit_code": proc.returncode, "output": out, "cwd": str(cwd)})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"timed out after {timeout}s", "command": cmd})
    except OSError as e:
        return json.dumps({"error": str(e), "command": cmd})


def read_file(base: Path, args: dict[str, object]) -> str:
    raw_path = str(args.get("path", ""))
    path = _resolve_path(base, raw_path)

    approved, denial_msg = _approve_file_op("read_file", str(path))
    if not approved:
        return json.dumps({"error": "user_denied", "message": denial_msg, "path": str(path)})

    if not path.is_file():
        return json.dumps({"error": "not a file", "path": str(path)})
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > 200_000:
            text = text[:200_000] + "\n… [truncated]"
        return json.dumps({"path": str(path), "content": text})
    except OSError as e:
        return json.dumps({"error": str(e), "path": str(path)})


def _show_write_diff(path: Path, new_content: str) -> None:
    """Print a colored unified diff when overwriting an existing file."""
    if not path.is_file():
        return
    try:
        old_content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if old_content == new_content:
        print(f"  {C.DIM}(no changes){C.RST}")
        return
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{path.name}", tofile=f"b/{path.name}", n=3,
    ))
    if not diff:
        return
    print(f"\n{C.DIM}  Diff ({path.name}):{C.RST}")
    shown = 0
    for line in diff:
        stripped = line.rstrip("\n")
        if stripped.startswith("+++") or stripped.startswith("---"):
            print(f"  {C.DIM}{stripped}{C.RST}")
        elif stripped.startswith("+"):
            print(f"  \033[32m{stripped}\033[0m")
        elif stripped.startswith("-"):
            print(f"  \033[31m{stripped}\033[0m")
        elif stripped.startswith("@@"):
            print(f"  {C.WARN}{stripped}{C.RST}")
        else:
            print(f"  {C.DIM}{stripped}{C.RST}")
        shown += 1
        if shown >= 60:
            remaining = len(diff) - shown
            if remaining > 0:
                print(f"  {C.DIM}… {remaining} more lines not shown{C.RST}")
            break
    print()


def write_file(base: Path, args: dict[str, object]) -> str:
    raw_path = str(args.get("path", ""))
    path = _resolve_path(base, raw_path)
    content = str(args.get("content", ""))

    _show_write_diff(path, content)
    approved, denial_msg = _approve_file_op("write_file", str(path))
    if not approved:
        return json.dumps({"error": "user_denied", "message": denial_msg, "path": str(path)})

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True, "path": str(path), "bytes": len(content.encode("utf-8"))})
    except OSError as e:
        return json.dumps({"error": str(e), "path": str(path)})


def append_file(base: Path, args: dict[str, object]) -> str:
    raw_path = str(args.get("path", ""))
    path = _resolve_path(base, raw_path)
    content = str(args.get("content", ""))

    approved, denial_msg = _approve_file_op("append_file", str(path))
    if not approved:
        return json.dumps({"error": "user_denied", "message": denial_msg, "path": str(path)})

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"ok": True, "path": str(path), "appended_bytes": len(content.encode("utf-8"))})
    except OSError as e:
        return json.dumps({"error": str(e), "path": str(path)})


def list_directory(base: Path, args: dict[str, object]) -> str:
    raw = args.get("path")
    path = base if not isinstance(raw, str) or not raw.strip() else _resolve_path(base, raw)

    approved, denial_msg = _approve_file_op("list_directory", str(path))
    if not approved:
        return json.dumps({"error": "user_denied", "message": denial_msg, "path": str(path)})

    if not path.is_dir():
        return json.dumps({"error": "not a directory", "path": str(path)})
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        truncated = len(entries) > 500
        rows = [
            {"name": p.name, "type": "dir" if p.is_dir() else "file"}
            for p in entries[:500]
        ]
        return json.dumps({"path": str(path), "entries": rows, "truncated": truncated})
    except OSError as e:
        return json.dumps({"error": str(e), "path": str(path)})


def fetch_url(base: Path, args: dict[str, object]) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        return json.dumps({"error": "empty url"})

    print(f"\n{C.WARN}  Fetch URL{C.RST}")
    print(f"  {C.DIM}{url}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans not in ("a", "allow"):
        return json.dumps({"error": "user_denied", "url": url})

    try:
        import httpx as _httpx
        from html.parser import HTMLParser as _HP

        resp = _httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "html" in ct.lower():
            class _Stripper(_HP):
                def __init__(self) -> None:
                    super().__init__()
                    self.parts: list[str] = []
                    self._skip = False
                def handle_starttag(self, tag: str, attrs: object) -> None:
                    if tag in ("script", "style"):
                        self._skip = True
                def handle_endtag(self, tag: str) -> None:
                    if tag in ("script", "style"):
                        self._skip = False
                def handle_data(self, d: str) -> None:
                    if not self._skip:
                        self.parts.append(d)
            s = _Stripper()
            s.feed(resp.text)
            text = re.sub(r"\s+", " ", " ".join(s.parts)).strip()
        else:
            text = resp.text
        if len(text) > 50_000:
            text = text[:50_000] + "\n… [truncated]"
        return json.dumps({"url": url, "content": text, "status": resp.status_code})
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


def python_repl(base: Path, args: dict[str, object]) -> str:
    code = str(args.get("code", "")).strip()
    if not code:
        return json.dumps({"error": "empty code"})
    timeout = int(args.get("timeout_seconds") or 30)

    print(f"\n{C.WARN}  Python REPL{C.RST}")
    lines = code.split("\n")
    preview = "\n  ".join(lines[:5])
    if len(lines) > 5:
        preview += f"\n  … ({len(lines)} lines total)"
    print(f"  {C.DIM}{preview}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans not in ("a", "allow"):
        return json.dumps({"error": "user_denied"})

    print(f"\n{C.OK}🐍 Running Python...{C.RST}", flush=True)
    fname: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            fname = f.name
        proc = subprocess.run(
            [sys.executable, fname],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            env=os.environ.copy(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > 50_000:
            out = out[:50_000] + "\n… [truncated]"
        return json.dumps({"exit_code": proc.returncode, "output": out})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if fname:
            try:
                Path(fname).unlink(missing_ok=True)
            except Exception:
                pass


def web_search(base: Path, args: dict[str, object]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return json.dumps({"error": "empty query"})
    max_results = int(args.get("max_results") or 5)

    print(f"\n{C.WARN}  Web Search{C.RST}")
    print(f"  {C.DIM}{query}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans not in ("a", "allow"):
        return json.dumps({"error": "user_denied", "query": query})

    try:
        import urllib.parse
        import httpx as _httpx
        from html.parser import HTMLParser as _HP

        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = _httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()

        class _DDGParser(_HP):
            def __init__(self) -> None:
                super().__init__()
                self._in_title = False
                self._in_snippet = False
                self._cur_url: str | None = None
                self._cur_title: list[str] = []
                self._cur_snippet: list[str] = []
                self.results: list[dict] = []

            def handle_starttag(self, tag: str, attrs: list) -> None:
                d = dict(attrs)
                cls = d.get("class", "")
                if tag == "a" and "result__a" in cls:
                    self._in_title = True
                    self._cur_title = []
                    href = d.get("href", "")
                    if "uddg=" in href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        self._cur_url = parsed.get("uddg", [href])[0]
                    else:
                        self._cur_url = href
                if "result__snippet" in cls:
                    self._in_snippet = True
                    self._cur_snippet = []

            def handle_endtag(self, tag: str) -> None:
                if self._in_title and tag == "a":
                    self._in_title = False
                    if self._cur_url and self._cur_title:
                        if not any(r["url"] == self._cur_url for r in self.results):
                            self.results.append({
                                "title": "".join(self._cur_title).strip(),
                                "url": self._cur_url,
                                "snippet": "",
                            })
                if self._in_snippet and tag in ("a", "div", "span"):
                    self._in_snippet = False
                    if self.results:
                        self.results[-1]["snippet"] = "".join(self._cur_snippet).strip()
                    self._cur_snippet = []

            def handle_data(self, d: str) -> None:
                if self._in_title:
                    self._cur_title.append(d)
                elif self._in_snippet:
                    self._cur_snippet.append(d)

        parser = _DDGParser()
        parser.feed(resp.text)
        results = parser.results[:max_results]
        return json.dumps({"query": query, "results": results})
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


def interact(base: Path, args: dict[str, object]) -> str:
    action = str(args.get("action", "")).strip().lower()
    if not action:
        return json.dumps({"error": "empty action"})
    try:
        backend = _select_interact_backend(base)
    except Exception as e:
        return json.dumps({"error": str(e), "action": action})

    approved, denial_msg = _approve_interact(action)
    if not approved:
        return json.dumps({"error": "user_denied", "message": denial_msg, "action": action})

    try:
        if action == "screenshot":
            return json.dumps(backend.screenshot())
        if action == "move_mouse":
            return json.dumps(backend.move_mouse(int(args.get("x", 0)), int(args.get("y", 0))))
        if action == "click":
            return json.dumps(backend.click(args))
        if action == "double_click":
            return json.dumps(backend.double_click(args))
        if action == "right_click":
            return json.dumps(backend.right_click(args))
        if action == "drag":
            return json.dumps(backend.drag(args))
        if action == "scroll":
            return json.dumps(backend.scroll(int(args.get("dy") or 0)))
        if action == "type_text":
            return json.dumps(backend.type_text(str(args.get("text", ""))))
        if action == "press_key":
            return json.dumps(backend.press_key(str(args.get("key", ""))))
        if action == "hotkey":
            keys = args.get("keys") or []
            if not isinstance(keys, list) or not keys:
                return json.dumps({"error": "keys must be a non-empty array"})
            return json.dumps(backend.hotkey([str(k) for k in keys]))
        if action == "sleep":
            return json.dumps(backend.sleep(float(args.get("seconds") or 0.0)))
        return json.dumps({"error": f"unknown interact action: {action}"})
    except Exception as e:
        return json.dumps({"error": str(e), "action": action})


def edit_file(base: Path, args: dict[str, object]) -> str:
    raw_path = str(args.get("path", ""))
    path = _resolve_path(base, raw_path)
    old_string = str(args.get("old_string", ""))
    new_string = str(args.get("new_string", ""))

    if not old_string:
        return json.dumps({"error": "old_string must not be empty"})
    if not path.is_file():
        return json.dumps({"error": "not a file", "path": str(path)})

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return json.dumps({"error": str(e), "path": str(path)})

    count = original.count(old_string)
    if count == 0:
        return json.dumps({"error": "old_string not found in file", "path": str(path)})
    if count > 1:
        return json.dumps({
            "error": f"old_string appears {count} times — add more surrounding context to make it unique",
            "path": str(path),
        })

    new_content = original.replace(old_string, new_string, 1)
    _show_write_diff(path, new_content)

    approved, denial_msg = _approve_file_op("write_file", str(path))
    if not approved:
        return json.dumps({"error": "user_denied", "message": denial_msg, "path": str(path)})

    try:
        path.write_text(new_content, encoding="utf-8")
        return json.dumps({"ok": True, "path": str(path)})
    except OSError as e:
        return json.dumps({"error": str(e), "path": str(path)})


def batch_approve_and_execute(
    calls: list[tuple[str, str, str]],  # [(call_id, name, arguments_json), ...]
    workspace: Path,
) -> dict[str, str]:
    """
    Batch-approve and (where safe) execute tools in parallel.
    Shows all pending tools, asks for batch approval, then runs them.
    Returns {call_id: result_json}.
    """
    import concurrent.futures

    if not calls:
        return {}

    if len(calls) == 1:
        cid, name, args_json = calls[0]
        return {cid: execute_tool(name, args_json, workspace)}

    # Show all pending tools
    print(f"\n{C.WARN}  {len(calls)} tools requested:{C.RST}")
    for i, (cid, name, args_json) in enumerate(calls, 1):
        try:
            args = json.loads(normalize_tool_arguments_json(args_json))
        except Exception:
            args = {}
        # Build a short display of the args
        if name == "run_command":
            detail = args.get("command", "")[:80]
        elif name in ("read_file", "write_file", "append_file", "edit_file"):
            detail = args.get("path", "")
        elif name == "web_search":
            detail = args.get("query", "")[:60]
        elif name == "fetch_url":
            detail = args.get("url", "")[:60]
        elif name == "interact":
            detail = args.get("action", "")
        else:
            detail = str(args)[:60]
        print(f"  {C.DIM}{i}. {name}{C.RST}  {C.DIM}{detail}{C.RST}")

    print(f"  {C.OK}[A]{C.RST} Approve all  {C.DIM}[R]{C.RST} Review each  {C.ERR}[D]{C.RST} Deny all")
    ans = _read_input("  > ").strip().lower()

    results: dict[str, str] = {}

    if ans in ("d", "deny"):
        for cid, name, _ in calls:
            results[cid] = json.dumps({"error": "user_denied", "message": "Denied by user."})
        return results

    from mahanai.config import load_interact_always_allow
    if all(name == "interact" for _, name, _ in calls) and load_interact_always_allow():
        ans = "a"

    if ans in ("r", "review"):
        for cid, name, args_json in calls:
            results[cid] = execute_tool(name, args_json, workspace)
        return results

    # Approve all — execute in parallel
    print(f"  {C.OK}Running {len(calls)} tools in parallel...{C.RST}")

    def _run_one(call: tuple[str, str, str]) -> tuple[str, str]:
        cid, name, args_json = call
        canon = normalize_tool_arguments_json(args_json)
        try:
            args = json.loads(canon)
        except json.JSONDecodeError:
            return cid, json.dumps({"error": "invalid JSON arguments"})
        # Execute without interactive approval (already batch-approved above)
        if name == "run_command":
            cmd = str(args.get("command", "")).strip()
            cwd_raw = args.get("cwd")
            timeout = int(args.get("timeout_seconds") or 120)
            cwd = workspace
            if isinstance(cwd_raw, str) and cwd_raw.strip():
                cwd = _resolve_path(workspace, cwd_raw)
            print(f"\n{C.OK}⚡Running:{C.RST} {cmd}", flush=True)
            try:
                proc = subprocess.run(
                    cmd, shell=True, cwd=str(cwd),
                    capture_output=True, text=True,
                    timeout=max(1, timeout), env=os.environ.copy(),
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                if len(out) > 100_000:
                    out = out[:100_000] + "\n… [truncated]"
                return cid, json.dumps({"exit_code": proc.returncode, "output": out, "cwd": str(cwd)})
            except subprocess.TimeoutExpired:
                return cid, json.dumps({"error": f"timed out after {timeout}s", "command": cmd})
            except OSError as e:
                return cid, json.dumps({"error": str(e), "command": cmd})
        elif name == "read_file":
            path = _resolve_path(workspace, str(args.get("path", "")))
            if not path.is_file():
                return cid, json.dumps({"error": "not a file", "path": str(path)})
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if len(text) > 200_000:
                    text = text[:200_000] + "\n… [truncated]"
                return cid, json.dumps({"path": str(path), "content": text})
            except OSError as e:
                return cid, json.dumps({"error": str(e)})
        elif name == "list_directory":
            raw = args.get("path")
            path = workspace if not isinstance(raw, str) or not raw.strip() else _resolve_path(workspace, raw)
            if not path.is_dir():
                return cid, json.dumps({"error": "not a directory", "path": str(path)})
            try:
                entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                rows = [{"name": p.name, "type": "dir" if p.is_dir() else "file"} for p in entries[:500]]
                return cid, json.dumps({"path": str(path), "entries": rows})
            except OSError as e:
                return cid, json.dumps({"error": str(e)})
        else:
            # Fallback: sequential with standard approval
            return cid, execute_tool(name, args_json, workspace)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(calls), 8)) as executor:
        futures = [executor.submit(_run_one, call) for call in calls]
        for f in concurrent.futures.as_completed(futures):
            cid, result = f.result()
            results[cid] = result

    return results


def execute_tool(name: str, arguments_json: str, workspace: Path) -> str:
    canon = normalize_tool_arguments_json(arguments_json)
    if canon == "{}" and (arguments_json or "").strip() not in ("", "{}"):
        return json.dumps(
            {
                "error": "could not parse tool arguments as JSON",
                "raw": (arguments_json or "")[:500],
            }
        )
    try:
        args = json.loads(canon)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid JSON arguments: {e}"})

    if name == "run_command":
        result = run_command(workspace, args)
    elif name == "read_file":
        result = read_file(workspace, args)
    elif name == "write_file":
        result = write_file(workspace, args)
    elif name == "append_file":
        result = append_file(workspace, args)
    elif name == "list_directory":
        result = list_directory(workspace, args)
    elif name == "fetch_url":
        result = fetch_url(workspace, args)
    elif name == "python_repl":
        result = python_repl(workspace, args)
    elif name == "edit_file":
        result = edit_file(workspace, args)
    elif name == "web_search":
        result = web_search(workspace, args)
    elif name == "interact":
        result = interact(workspace, args)
    elif name == "connect_get_config_view":
        from mahanai.connect import get_config_view

        result = json.dumps(get_config_view())
    elif name == "connect_request_config_change":
        from mahanai.connect import request_config_change

        changes = args.get("changes")
        result = json.dumps(
            request_config_change(
                changes if isinstance(changes, dict) else {},
                approve=_approve_connect_config,
                reason=str(args.get("reason", "")).strip(),
            )
        )
    elif name == "connect_run_user_command":
        from mahanai.connect import run_user_command

        result = json.dumps(run_user_command(workspace, args, approve=_approve_connect_command))
    elif name == "connect_request_rerun":
        from mahanai.connect import request_rerun

        result = json.dumps(request_rerun(args))
    else:
        return json.dumps({"error": f"unknown tool: {name}"})

    try:
        from mahanai.config import audit_log_path
        import datetime as _dt
        _log = audit_log_path()
        _log.parent.mkdir(parents=True, exist_ok=True)
        _ts = _dt.datetime.now().isoformat(timespec="seconds")
        _ap = (arguments_json or "")[:120].replace("\n", " ")
        _rp = (result or "")[:120].replace("\n", " ")
        with _log.open("a", encoding="utf-8") as _f:
            _f.write(f"{_ts} | {name} | {_ap} | {_rp}\n")
    except Exception:
        pass

    return result
