# Web UI Embedding And GitHub OAuth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed the web UI into the Python server response path, add recommended GitHub OAuth onboarding for the marketplace, and rename indirect Codex gateway model IDs with an `-indirect` suffix.

**Architecture:** Keep the existing repo layout and entry points. Add focused helpers in `mahanai.server`, `mahanai.agent`, and `mahanai.store`, then verify behavior with targeted `unittest` coverage for server UI/model behavior and onboarding/store token persistence.

**Tech Stack:** Python, `http.server`, `httpx`, `unittest`

---

### Task 1: Cover server-facing behavior

**Files:**
- Create: `tests/test_server.py`
- Modify: `mahanai/server.py`
- Test: `tests/test_server.py`

- [ ] Add failing tests for embedded UI response behavior and `-indirect` model IDs.
- [ ] Run `python -m unittest tests.test_server -v` and confirm failures reflect missing behavior.
- [ ] Implement minimal server changes to satisfy those tests.
- [ ] Re-run `python -m unittest tests.test_server -v` and confirm passing results.

### Task 2: Cover onboarding and store auth behavior

**Files:**
- Create: `tests/test_store_auth.py`
- Modify: `mahanai/agent.py`
- Modify: `mahanai/store.py`
- Test: `tests/test_store_auth.py`

- [ ] Add failing tests for GitHub device-flow config handling, token persistence, and onboarding prompt behavior.
- [ ] Run `python -m unittest tests.test_store_auth -v` and confirm failures reflect missing behavior.
- [ ] Implement minimal auth helpers and wire them into onboarding and `/store login`.
- [ ] Re-run `python -m unittest tests.test_store_auth -v` and confirm passing results.

### Task 3: Verify the integrated change set

**Files:**
- Modify: `mahanai/server.py`
- Modify: `mahanai/agent.py`
- Modify: `mahanai/store.py`
- Test: `tests/test_server.py`
- Test: `tests/test_store_auth.py`

- [ ] Run `python -m unittest tests.test_server tests.test_store_auth -v`.
- [ ] Run one broader regression command for nearby config behavior.
- [ ] Inspect the diff for scope and ensure the exposed CLI/help text matches the new auth flow.
