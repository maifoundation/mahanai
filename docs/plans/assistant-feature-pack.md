# Assistant Feature Pack

This is a ready-to-implement shortlist of useful AI features for MahanAI. Each item is mapped to the exact code paths I would change, so I can add it later without rediscovering the architecture.

## 1) /recap
Goal: Give a short, clean summary of the current chat, the open questions, and the next action.
Why it helps: It makes long sessions easier to continue.
Implementation hooks:
- mahanai/agent.py: add a new slash command branch, help text, and command palette entry.
- mahanai/chat_history.py: reuse saved session data if the current chat needs a fuller recap.
- tests/: add coverage for the command output shape.

## 2) /handoff
Goal: Export a compact handoff note with context, decisions, files touched, and next steps.
Why it helps: It makes it easy to pause and resume work later.
Implementation hooks:
- mahanai/agent.py: add the command and wire it into the slash-command dispatcher.
- mahanai/config.py: if needed, store a small handoff draft or path preference.
- tests/: verify the generated handoff format is stable and readable.

## 3) /task-list
Goal: Turn the current conversation into an action list the user can follow.
Why it helps: It keeps the assistant focused on execution instead of drifting.
Implementation hooks:
- mahanai/agent.py: add command handling and a formatted task output.
- mahanai/tools.py: if needed, reuse the existing note and prompt helpers.
- tests/: check that action items are extracted and numbered cleanly.

## 4) /project-brief
Goal: Produce a short project summary from MAHANAI.md, README.md, and the active workspace state.
Why it helps: It gives quick project context without making the user repeat themselves.
Implementation hooks:
- mahanai/agent.py: add the command branch and help text.
- mahanai/system_info.py: reuse runtime and workspace context helpers.
- MAHANAI.md: keep the generated brief aligned with the project conventions.

## Suggested order
1. /recap
2. /task-list
3. /handoff
4. /project-brief

## Files I already mapped for future work
- mahanai/agent.py
- mahanai/chat_history.py
- mahanai/config.py
- mahanai/system_info.py
- mahanai/tools.py
- tests/

## Notes
- These features fit the current slash-command architecture.
- They can be added without changing the plugin system.
- When you ask me to build one, I can wire it directly into the command dispatcher and add tests in the same pass.
