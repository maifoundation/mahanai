from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mahanai import chat_history


def _write_chat(path: Path, *, session_id: str, name: str, model: str, messages: list[dict], mtime: float) -> None:
    path.write_text(
        json.dumps(
            {
                "id": session_id,
                "name": name,
                "model": model,
                "messages": messages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    path.touch()
    path.chmod(0o644)
    os.utime(path, (mtime, mtime))


def test_search_chats_finds_matching_sessions_and_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()

    monkeypatch.setattr(chat_history, "get_chats_dir", lambda project_name=None: chats_dir)

    chat_a = chats_dir / "deploy-plan.json"
    chat_b = chats_dir / "random-notes.json"
    chat_c = chats_dir / "deploy-bugfix.json"

    _write_chat(
        chat_a,
        session_id="aaa",
        name="deploy-plan",
        model="gpt-5.4",
        messages=[
            {"role": "user", "content": "Plan the deploy to staging"},
            {"role": "assistant", "content": "Sure"},
        ],
        mtime=1000.0,
    )
    _write_chat(
        chat_b,
        session_id="bbb",
        name="random-notes",
        model="gpt-5.4",
        messages=[
            {"role": "user", "content": "Lunch ideas"},
            {"role": "assistant", "content": "Pizza"},
        ],
        mtime=2000.0,
    )
    _write_chat(
        chat_c,
        session_id="ccc",
        name="deploy-bugfix",
        model="claude-sonnet-4-6",
        messages=[
            {"role": "user", "content": "Fix the deploy crash"},
            {"role": "assistant", "content": "Investigating"},
        ],
        mtime=3000.0,
    )

    results = chat_history.search_chats("deploy")

    assert [r["id"] for r in results] == ["ccc", "aaa"]
    assert results[0]["_preview"].lower().startswith("fix the deploy crash")
    assert results[1]["_preview"].lower().startswith("plan the deploy to staging")


def test_search_chats_empty_query_returns_recent_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    monkeypatch.setattr(chat_history, "get_chats_dir", lambda project_name=None: chats_dir)

    _write_chat(
        chats_dir / "one.json",
        session_id="1",
        name="one",
        model="gpt-5.4",
        messages=[{"role": "user", "content": "Hello"}],
        mtime=1000.0,
    )
    _write_chat(
        chats_dir / "two.json",
        session_id="2",
        name="two",
        model="gpt-5.4",
        messages=[{"role": "user", "content": "World"}],
        mtime=2000.0,
    )

    results = chat_history.search_chats("")

    assert [r["id"] for r in results] == ["2", "1"]
