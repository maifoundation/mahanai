# Connect API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a connect capability that lets the agent request approved non-secret config changes, approved user-permission shell commands, and rerun handoff messages without exposing or mutating secrets.

**Architecture:** Add a dedicated `mahanai/connect.py` policy layer that owns redacted config views, config mutation validation, connect approval prompts, session grants, and rerun payload generation. Wire new connect tools through `mahanai/tools.py`, add user-facing `/connect` slash commands in `mahanai/agent.py`, and keep all secret access blocked behind an explicit deny-by-default policy.

**Tech Stack:** Python 3, `unittest`, existing MahanAI CLI/tool infrastructure, JSON config persistence in `mahanai/config.py`

---

## File Structure

- Create: `mahanai/connect.py`
  - Connect policy layer, redacted config view, config mutation application, connect command execution, rerun request generation, in-memory session grants.
- Create: `tests/test_connect.py`
  - Unit tests for secret redaction, field mutation policy, connect command grant behavior, and rerun payloads.
- Modify: `mahanai/config.py`
  - Small helpers for safe raw config snapshots and field-level non-secret updates.
- Modify: `mahanai/tools.py`
  - Register connect tools and route execution into `mahanai/connect.py`.
- Modify: `mahanai/agent.py`
  - Add `/connect`, `/connect grants`, and `/connect revoke`.
- Modify: `tests/test_server.py`
  - Only if needed to preserve assumptions around tool registration shape.

### Task 1: Build config policy helpers

**Files:**
- Create: `tests/test_connect.py`
- Modify: `mahanai/config.py`
- Create: `mahanai/connect.py`

- [ ] **Step 1: Write the failing config redaction and mutation tests**

```python
import os
import tempfile
import unittest

from mahanai.config import _write_config
from mahanai.connect import get_config_view, request_config_change


class ConnectConfigTests(unittest.TestCase):
    def test_config_view_hides_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("MAHANAI_CONFIG_DIR")
            os.environ["MAHANAI_CONFIG_DIR"] = td
            try:
                _write_config(
                    {
                        "api_key": "sk-secret",
                        "theme": "midnight",
                        "custom_endpoint": {
                            "url": "http://localhost:11434/v1",
                            "model": "local-model",
                            "api_key": "ce-secret",
                        },
                    }
                )

                view = get_config_view()

                self.assertNotIn("api_key", view["config"])
                self.assertEqual(view["config"]["theme"], "midnight")
                self.assertEqual(
                    view["config"]["custom_endpoint"],
                    {"url": "http://localhost:11434/v1", "model": "local-model"},
                )
            finally:
                if old is None:
                    os.environ.pop("MAHANAI_CONFIG_DIR", None)
                else:
                    os.environ["MAHANAI_CONFIG_DIR"] = old

    def test_secret_mutation_is_rejected_before_approval(self) -> None:
        result = request_config_change(
            {"api_key": "new-secret"},
            approve=lambda summary: "allow-once",
        )
        self.assertEqual(result["error"], "blocked_config_field")
        self.assertIn("api_key", result["blocked_fields"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_connect.py -k "config_view_hides_secret_fields or secret_mutation_is_rejected_before_approval" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mahanai.connect'` or missing symbol errors.

- [ ] **Step 3: Write minimal config helpers and connect config policy**

```python
# mahanai/config.py
def load_raw_config() -> dict[str, Any]:
    return dict(_read_config())


def save_config_value(key: str, value: Any) -> None:
    data = _read_config()
    data[key] = value
    _write_config(data)
```

```python
# mahanai/connect.py
from __future__ import annotations

from typing import Any, Callable

from mahanai.config import load_raw_config, save_config_value

SECRET_FIELDS = {"api_key", "nvidia_api_key", "codex_token", "store_token"}
SECRET_NESTED_FIELDS = {("custom_endpoint", "api_key")}
MUTABLE_FIELDS = {
    "theme",
    "default_model",
    "interact_enabled",
    "interact_always_allow",
    "custom_endpoint",
}


def _sanitize_config(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in SECRET_FIELDS:
            continue
        if key == "custom_endpoint" and isinstance(value, dict):
            out[key] = {k: v for k, v in value.items() if k != "api_key"}
            continue
        out[key] = value
    return out


def get_config_view() -> dict[str, Any]:
    return {
        "config": _sanitize_config(load_raw_config()),
        "grants": {"config_session_granted": False, "command_session_granted": False},
    }


def request_config_change(
    changes: dict[str, Any],
    *,
    approve: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    blocked = [key for key in changes if key in SECRET_FIELDS or key not in MUTABLE_FIELDS]
    if blocked:
        return {"error": "blocked_config_field", "blocked_fields": blocked}
    decision = approve({"changes": changes})
    if decision not in {"allow-once", "allow-session"}:
        return {"error": "user_denied"}
    for key, value in changes.items():
        save_config_value(key, value)
    return {"ok": True, "applied": sorted(changes)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_connect.py -k "config_view_hides_secret_fields or secret_mutation_is_rejected_before_approval" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_connect.py mahanai/config.py mahanai/connect.py
git commit -m "feat: add connect config policy"
```

### Task 2: Add connect session grants and command execution policy

**Files:**
- Modify: `tests/test_connect.py`
- Modify: `mahanai/connect.py`

- [ ] **Step 1: Write the failing connect command tests**

```python
from unittest.mock import patch

from mahanai.connect import (
    clear_session_grants,
    grant_command_session,
    run_user_command,
)


class ConnectCommandTests(unittest.TestCase):
    def test_session_grant_bypasses_reapproval_for_safe_command(self) -> None:
        clear_session_grants()
        grant_command_session()
        with patch("mahanai.connect.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "ok\n"
            run_mock.return_value.stderr = ""

            result = run_user_command(
                ".",
                {"command": "pwd"},
                approve=lambda summary: (_ for _ in ()).throw(AssertionError("approval should not run")),
            )

        self.assertEqual(result["exit_code"], 0)

    def test_high_risk_command_still_requires_per_action_approval(self) -> None:
        clear_session_grants()
        grant_command_session()
        result = run_user_command(
            ".",
            {"command": "rm -rf /tmp/example"},
            approve=lambda summary: "deny",
        )
        self.assertEqual(result["error"], "user_denied")
        self.assertTrue(result["high_risk"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_connect.py -k "session_grant_bypasses_reapproval_for_safe_command or high_risk_command_still_requires_per_action_approval" -v`
Expected: FAIL with missing `grant_command_session`, `clear_session_grants`, or `run_user_command`.

- [ ] **Step 3: Write minimal session grant and command execution code**

```python
# mahanai/connect.py
import json
import os
import subprocess
from pathlib import Path

from mahanai.tools import _is_high_risk

_SESSION_GRANTS = {
    "config_session_granted": False,
    "command_session_granted": False,
}


def clear_session_grants() -> None:
    _SESSION_GRANTS["config_session_granted"] = False
    _SESSION_GRANTS["command_session_granted"] = False


def grant_command_session() -> None:
    _SESSION_GRANTS["command_session_granted"] = True


def run_user_command(
    base: str | Path,
    args: dict[str, Any],
    *,
    approve: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    cmd = str(args.get("command", "")).strip()
    cwd = Path(base)
    high_risk = _is_high_risk(cmd)
    needs_approval = high_risk or not _SESSION_GRANTS["command_session_granted"]
    if needs_approval:
        decision = approve({"command": cmd, "cwd": str(cwd), "high_risk": high_risk})
        if decision == "allow-session" and not high_risk:
            grant_command_session()
        elif decision != "allow-once":
            return {"error": "user_denied", "high_risk": high_risk, "command": cmd}
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=max(1, int(args.get("timeout_seconds") or 120)),
        env=os.environ.copy(),
    )
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "cwd": str(cwd),
        "high_risk": high_risk,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_connect.py -k "session_grant_bypasses_reapproval_for_safe_command or high_risk_command_still_requires_per_action_approval" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_connect.py mahanai/connect.py
git commit -m "feat: add connect command grants"
```

### Task 3: Expose connect through the tool registry

**Files:**
- Modify: `tests/test_connect.py`
- Modify: `mahanai/tools.py`

- [ ] **Step 1: Write the failing tool registration tests**

```python
from pathlib import Path

from mahanai.tools import execute_tool, get_tools


class ConnectToolTests(unittest.TestCase):
    def test_connect_tools_are_registered(self) -> None:
        names = {tool["function"]["name"] for tool in get_tools()}
        self.assertTrue(
            {
                "connect_get_config_view",
                "connect_request_config_change",
                "connect_run_user_command",
                "connect_request_rerun",
            }.issubset(names)
        )

    def test_connect_get_config_view_dispatches(self) -> None:
        result = execute_tool("connect_get_config_view", "{}", Path("."))
        self.assertIn('"config"', result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_connect.py -k "connect_tools_are_registered or connect_get_config_view_dispatches" -v`
Expected: FAIL because the connect tools do not exist yet.

- [ ] **Step 3: Add connect tool definitions and dispatch**

```python
# mahanai/tools.py
from mahanai.connect import (
    get_config_view,
    request_config_change,
    request_rerun,
    run_user_command,
)


TOOLS.extend(
    [
        {
            "type": "function",
            "function": {
                "name": "connect_get_config_view",
                "description": "Return a sanitized view of MahanAI config and connect grants.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "connect_request_config_change",
                "description": "Request approved changes to non-secret MahanAI config.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "changes": {"type": "object"},
                        "reason": {"type": "string"},
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
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                        "timeout_seconds": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "connect_request_rerun",
                "description": "Generate a rerun handoff request for the user.",
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
)
```

```python
# mahanai/tools.py inside execute_tool(...)
if name == "connect_get_config_view":
    return json.dumps(get_config_view())
if name == "connect_request_config_change":
    return json.dumps(request_config_change(args.get("changes") or {}, approve=_approve_connect_config))
if name == "connect_run_user_command":
    return json.dumps(run_user_command(workspace, args, approve=_approve_connect_command))
if name == "connect_request_rerun":
    return json.dumps(request_rerun(args))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_connect.py -k "connect_tools_are_registered or connect_get_config_view_dispatches" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_connect.py mahanai/tools.py
git commit -m "feat: add connect tools"
```

### Task 4: Add CLI approvals and slash commands

**Files:**
- Modify: `tests/test_connect.py`
- Modify: `mahanai/tools.py`
- Modify: `mahanai/agent.py`

- [ ] **Step 1: Write the failing slash command and rerun tests**

```python
from mahanai.connect import request_rerun


class ConnectUiTests(unittest.TestCase):
    def test_rerun_payload_contains_reason_and_command(self) -> None:
        payload = request_rerun(
            {
                "reason": "need a new environment",
                "suggested_command": "mahanai --connect",
            }
        )
        self.assertEqual(payload["reason"], "need a new environment")
        self.assertIn("mahanai --connect", payload["message"])
```

Manual acceptance target for slash commands after implementation:

```text
/connect
/connect grants
/connect revoke
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_connect.py -k rerun_payload_contains_reason_and_command -v`
Expected: FAIL because `request_rerun` does not exist yet.

- [ ] **Step 3: Implement connect approvals, rerun payloads, and slash commands**

```python
# mahanai/connect.py
def request_rerun(args: dict[str, Any]) -> dict[str, Any]:
    reason = str(args.get("reason", "")).strip()
    suggested = str(args.get("suggested_command", "")).strip()
    notes = str(args.get("notes", "")).strip()
    message = f"Please rerun MahanAI. Reason: {reason}"
    if suggested:
        message += f"\nSuggested command: {suggested}"
    if notes:
        message += f"\nNotes: {notes}"
    return {"reason": reason, "suggested_command": suggested, "notes": notes, "message": message}
```

```python
# mahanai/tools.py
def _approve_connect_config(summary: dict[str, Any]) -> str:
    print(f"\n{C.WARN}  Connect Config Change{C.RST}")
    print(f"  {C.DIM}{json.dumps(summary, indent=2, sort_keys=True)}{C.RST}")
    print(f"  {C.OK}[A]{C.RST} Allow Once    {C.DIM}[S] Allow for Session{C.RST}    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    return {"a": "allow-once", "s": "allow-session"}.get(ans, "deny")


def _approve_connect_command(summary: dict[str, Any]) -> str:
    print(f"\n{C.WARN}  Connect Command{C.RST}")
    print(f"  {C.DIM}{summary['command']}{C.RST}")
    print(f"  {C.DIM}cwd={summary['cwd']}  high_risk={summary['high_risk']}{C.RST}")
    if summary["high_risk"]:
        print(f"  {C.OK}[A]{C.RST} Allow Once    {C.ERR}[D]{C.RST} Deny")
    else:
        print(f"  {C.OK}[A]{C.RST} Allow Once    {C.DIM}[S] Allow for Session{C.RST}    {C.ERR}[D]{C.RST} Deny")
    ans = _read_input("  > ").lower()
    if ans == "a":
        return "allow-once"
    if ans == "s" and not summary["high_risk"]:
        return "allow-session"
    return "deny"
```

```python
# mahanai/agent.py additions
_ALL_COMMANDS.extend(
    [
        ("/connect", "Show connect status and help"),
        ("/connect grants", "Show active connect session grants"),
        ("/connect revoke", "Clear active connect session grants"),
    ]
)
```

```python
# mahanai/agent.py inside slash command handling
if cmd == "/connect":
    sub = rest.strip().lower()
    status = get_connect_status()
    if sub == "grants":
        print_connect_grants(status)
    elif sub == "revoke":
        clear_session_grants()
        print(f"{C.OK}Connect session grants cleared.{C.RST}\n")
    else:
        print_connect_summary(status)
    continue
```

- [ ] **Step 4: Run verification**

Run: `python -m pytest tests/test_connect.py -v`
Expected: PASS

Run: `python -m pytest tests/test_interact_config.py tests/test_default_model_config.py tests/test_server.py -v`
Expected: PASS

Manual check:

```bash
python -m mahanai
```

Expected:
- `/connect` prints connect help and current grant status
- `/connect grants` shows inactive grants on a new session
- `/connect revoke` clears any active connect session grants

- [ ] **Step 5: Commit**

```bash
git add tests/test_connect.py mahanai/connect.py mahanai/tools.py mahanai/agent.py
git commit -m "feat: add connect approvals and slash commands"
```

## Self-Review

- Spec coverage:
  - Redacted config view: Task 1
  - Non-secret config changes with approval: Tasks 1 and 4
  - User-permission command path with session grants and high-risk override: Task 2 and Task 4
  - Rerun handoff: Task 4
  - Tool surface: Task 3
  - Slash commands and grant revocation: Task 4
- Placeholder scan:
  - No `TODO`, `TBD`, or deferred implementation markers remain.
- Type consistency:
  - Connect tool names are consistent across plan tasks.
  - Session grant keys are consistent with the approved spec.
