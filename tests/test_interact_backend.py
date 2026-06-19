from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class InteractBackendTests(unittest.TestCase):
    def test_prefers_wayland_when_helpers_exist(self) -> None:
        tools = importlib.import_module("mahanai.tools")
        with patch.dict(
            tools.os.environ,
            {"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland"},
            clear=False,
        ), patch.object(tools, "_command_exists", side_effect=lambda name: name in {"grim", "ydotool"}), patch.object(
            tools, "_can_import_pyautogui", return_value=True
        ):
            backend = tools._select_interact_backend()

        self.assertEqual(backend.kind, "wayland")

    def test_wayland_session_without_helpers_fails_cleanly(self) -> None:
        tools = importlib.import_module("mahanai.tools")
        with patch.dict(
            tools.os.environ,
            {"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "XAUTHORITY": ""},
            clear=False,
        ), patch.object(tools, "_command_exists", return_value=False), patch.object(
            tools, "_can_import_pyautogui", return_value=True
        ):
            with self.assertRaisesRegex(RuntimeError, "ydotool"):
                tools._select_interact_backend()

    def test_wayland_backend_builds_expected_commands(self) -> None:
        tools = importlib.import_module("mahanai.tools")
        with tempfile.TemporaryDirectory() as td:
            backend = tools._WaylandInteractBackend(Path(td))

            commands: list[list[str]] = []

            def fake_run(*args, **kwargs):
                commands.append(args[0])

                class _Result:
                    returncode = 0

                return _Result()

            with patch.object(tools.subprocess, "run", side_effect=fake_run):
                backend.click({"x": 10, "y": 20, "button": "left", "clicks": 2})

            self.assertTrue(any(cmd and cmd[0] == "ydotool" for cmd in commands))

    def test_interact_dependency_check_accepts_wayland_helpers(self) -> None:
        agent = importlib.import_module("mahanai.agent")
        with patch.object(agent, "_can_import_pyautogui", return_value=False), patch.object(
            agent, "_wayland_helpers_available", return_value=True
        ):
            ok, msg = agent._ensure_interact_dependencies()

        self.assertTrue(ok)
        self.assertIn("Wayland", msg)

    def test_wayland_session_without_ydotool_and_xauthority_fails_cleanly(self) -> None:
        tools = importlib.import_module("mahanai.tools")
        agent = importlib.import_module("mahanai.agent")
        with patch.dict(
            tools.os.environ,
            {
                "WAYLAND_DISPLAY": "wayland-1",
                "XDG_SESSION_TYPE": "wayland",
                "DISPLAY": ":0",
                "XAUTHORITY": "",
            },
            clear=False,
        ), patch.object(tools, "_command_exists", side_effect=lambda name: name == "grim"), patch.object(
            tools, "_can_import_pyautogui", return_value=True
        ):
            with self.assertRaisesRegex(RuntimeError, "ydotool"):
                tools._select_interact_backend()

            ok, msg = agent._ensure_interact_dependencies()

        self.assertFalse(ok)
        self.assertIn("X11 fallback is unavailable", msg)


if __name__ == "__main__":
    unittest.main()
