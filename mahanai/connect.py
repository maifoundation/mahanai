"""Connect API policy layer for approved config and command actions."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from mahanai.config import load_raw_config, save_config_value

ApprovalCallback = Callable[[dict[str, Any]], str]

SECRET_FIELDS = {"api_key", "nvidia_api_key", "codex_token", "store_token"}

MUTABLE_FIELDS = {
    "active_project",
    "aliases",
    "always_allowed",
    "chat_history",
    "context_limit_tokens",
    "custom_endpoint",
    "custom_theme",
    "custom_theme_path",
    "default_model",
    "index_docs",
    "interact_always_allow",
    "interact_enabled",
    "macros",
    "memories",
    "ollama_providers",
    "onboarding_complete",
    "plugins",
    "projects",
    "prompts",
    "roles",
    "show_cost",
    "show_tokens",
    "theme",
}

_SESSION_GRANTS = {
    "config_session_granted": False,
    "command_session_granted": False,
}

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


def _is_high_risk(command: str) -> bool:
    low = command.strip().lower()
    return any(pattern.search(low) for pattern in _HIGH_RISK_PATTERNS)


def clear_session_grants() -> None:
    _SESSION_GRANTS["config_session_granted"] = False
    _SESSION_GRANTS["command_session_granted"] = False


def grant_config_session() -> None:
    _SESSION_GRANTS["config_session_granted"] = True


def grant_command_session() -> None:
    _SESSION_GRANTS["command_session_granted"] = True


def get_connect_status() -> dict[str, bool]:
    return dict(_SESSION_GRANTS)


def _sanitize_custom_endpoint(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {k: v for k, v in value.items() if k != "api_key"}


def _sanitize_ollama_providers(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    sanitized: dict[str, Any] = {}
    for name, provider in value.items():
        if isinstance(provider, dict):
            sanitized[name] = {k: v for k, v in provider.items() if k != "api_key"}
        else:
            sanitized[name] = provider
    return sanitized


def _sanitize_config(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if key in SECRET_FIELDS:
            continue
        if key == "custom_endpoint":
            sanitized[key] = _sanitize_custom_endpoint(value)
        elif key == "ollama_providers":
            sanitized[key] = _sanitize_ollama_providers(value)
        else:
            sanitized[key] = value
    return sanitized


def get_config_view() -> dict[str, Any]:
    return {
        "config": _sanitize_config(load_raw_config()),
        "grants": get_connect_status(),
    }


def _nested_api_key_fields(prefix: str, value: Any) -> list[str]:
    blocked: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}"
            if key == "api_key":
                blocked.append(path)
            else:
                blocked.extend(_nested_api_key_fields(path, nested))
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            blocked.extend(_nested_api_key_fields(f"{prefix}.{idx}", nested))
    return blocked


def _blocked_config_fields(changes: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    for key, value in changes.items():
        if key in SECRET_FIELDS or key not in MUTABLE_FIELDS:
            blocked.append(key)
            continue
        if key == "custom_endpoint" and isinstance(value, dict) and "api_key" in value:
            blocked.append("custom_endpoint.api_key")
        if key == "ollama_providers":
            blocked.extend(_nested_api_key_fields("ollama_providers", value))
    return blocked


def _safe_after_value(key: str, value: Any) -> Any:
    if key == "custom_endpoint":
        return _sanitize_custom_endpoint(value)
    if key == "ollama_providers":
        return _sanitize_ollama_providers(value)
    return value


def _merged_config_value(key: str, current: dict[str, Any], requested: Any) -> Any:
    if key == "custom_endpoint" and isinstance(current.get(key), dict) and isinstance(requested, dict):
        merged = dict(current[key])
        merged.update(requested)
        return merged

    if key == "ollama_providers" and isinstance(current.get(key), dict) and isinstance(requested, dict):
        providers = dict(current[key])
        for name, provider in requested.items():
            if isinstance(providers.get(name), dict) and isinstance(provider, dict):
                merged_provider = dict(providers[name])
                merged_provider.update(provider)
                providers[name] = merged_provider
            else:
                providers[name] = provider
        return providers

    return requested


def request_config_change(
    changes: dict[str, Any],
    *,
    approve: ApprovalCallback,
    reason: str = "",
) -> dict[str, Any]:
    if not isinstance(changes, dict) or not changes:
        return {"error": "invalid_payload", "message": "changes must be a non-empty object"}

    blocked = _blocked_config_fields(changes)
    if blocked:
        return {
            "error": "blocked_config_field",
            "blocked_fields": blocked,
            "message": "Connect cannot read or write secret or unknown config fields.",
        }

    current = load_raw_config()
    summary = {
        "reason": reason,
        "changes": [
            {
                "key": key,
                "before": _safe_after_value(key, current.get(key)),
                "after": _safe_after_value(key, value),
            }
            for key, value in changes.items()
        ],
    }

    session_granted = False
    if not _SESSION_GRANTS["config_session_granted"]:
        decision = approve(summary)
        if decision == "allow-session":
            grant_config_session()
            session_granted = True
        elif decision != "allow-once":
            return {"error": "user_denied", "message": "Connect config change denied by user."}

    for key, value in changes.items():
        save_config_value(key, _merged_config_value(key, current, value))

    return {"ok": True, "applied": sorted(changes), "session_granted": session_granted}


def _resolve_cwd(base: str | Path, raw: Any) -> Path:
    cwd = Path(base).expanduser()
    if isinstance(raw, str) and raw.strip():
        candidate = Path(raw).expanduser()
        cwd = candidate if candidate.is_absolute() else cwd / candidate
    return cwd.resolve()


def run_user_command(
    base: str | Path,
    args: dict[str, Any],
    *,
    approve: ApprovalCallback,
) -> dict[str, Any]:
    command = str(args.get("command", "")).strip()
    if not command:
        return {"error": "empty_command"}

    cwd = _resolve_cwd(base, args.get("cwd"))
    timeout = max(1, int(args.get("timeout_seconds") or 120))
    high_risk = _is_high_risk(command)

    if command.lower() == "pwd":
        return {
            "exit_code": 0,
            "stdout": f"{cwd}\n",
            "stderr": "",
            "output": f"{cwd}\n",
            "command": command,
            "cwd": str(cwd),
            "high_risk": False,
        }

    if high_risk or not _SESSION_GRANTS["command_session_granted"]:
        decision = approve(
            {
                "command": command,
                "cwd": str(cwd),
                "high_risk": high_risk,
                "reason": str(args.get("reason", "")).strip(),
            }
        )
        if decision == "allow-session" and not high_risk:
            grant_command_session()
        elif decision != "allow-once":
            return {
                "error": "user_denied",
                "command": command,
                "cwd": str(cwd),
                "high_risk": high_risk,
                "message": "Connect command denied by user.",
            }

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout}s", "command": command, "cwd": str(cwd)}
    except OSError as exc:
        return {"error": str(exc), "command": command, "cwd": str(cwd)}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if len(stdout) > 100_000:
        stdout = stdout[:100_000] + "\n... [truncated]"
    if len(stderr) > 100_000:
        stderr = stderr[:100_000] + "\n... [truncated]"

    return {
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "output": stdout + stderr,
        "command": command,
        "cwd": str(cwd),
        "high_risk": high_risk,
    }


def request_rerun(args: dict[str, Any]) -> dict[str, Any]:
    reason = str(args.get("reason", "")).strip()
    suggested_command = str(args.get("suggested_command", "")).strip()
    notes = str(args.get("notes", "")).strip()
    message = f"Please rerun MahanAI. Reason: {reason or 'permission context required'}"
    if suggested_command:
        message += f"\nSuggested command: {suggested_command}"
    if notes:
        message += f"\nNotes: {notes}"
    return {
        "reason": reason,
        "suggested_command": suggested_command,
        "notes": notes,
        "message": message,
    }
