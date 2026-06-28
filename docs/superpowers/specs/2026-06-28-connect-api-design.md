# Connect API Design

Date: 2026-06-28
Status: Draft approved in chat, pending final spec review

## Goal

Add a `connect` capability that lets the MahanAI agent:

- request approved changes to MahanAI's own non-secret config
- request approved execution of shell commands through a dedicated connect path using the user's permissions
- ask the user to rerun MahanAI with a clearer permission mode when direct execution is not appropriate

This must not let the agent read API keys, tokens, or other secret config values, and it must not let the agent modify any config without approval.

## Scope

This design covers:

- internal connect module and policy checks
- agent-facing connect tool surface
- user-facing slash commands for connect status and grant management
- approval flow and session grants
- tests for config redaction, config mutation policy, and connect command execution policy

This design does not cover:

- HTTP server or gateway API endpoints
- direct secret management through connect
- persistent privileged background daemons or OS service installation

## Requirements

### Functional

1. The agent can inspect a sanitized config view.
2. The agent can request changes to most non-secret app settings.
3. Every config change requires user approval unless there is an active connect session grant for non-secret config changes.
4. The agent can request command execution through a dedicated connect command path.
5. Every connect command requires user approval unless there is an active connect session grant, except that high-risk commands always require per-action approval.
6. The agent can request a rerun handoff that tells the user how to restart MahanAI with the needed permission context.
7. The user can inspect and revoke connect session grants through slash commands.

### Security

1. The agent cannot read secret config values.
2. The agent cannot write secret config values.
3. The agent cannot access the raw config file through connect.
4. Connect approvals must be separate from existing file-op and shell approval storage.
5. High-risk commands remain per-action even if a session grant exists.
6. Connect policy must default-deny unknown config fields.

## Architecture

### New module

Add `mahanai/connect.py` as the single policy and execution layer for connect.

Responsibilities:

- build a redacted config view for the agent
- classify config keys as readable, mutable, secret, or blocked
- validate and apply approved config changes
- manage connect session grants
- approve and execute connect commands
- generate rerun handoff payloads

This module should be the only place that knows the connect allowlist and connect approval behavior.

### Existing module integration

- `mahanai/config.py`
  - remains the source of truth for config persistence
  - gains helper functions for safe config snapshots and field-level updates if needed
- `mahanai/tools.py`
  - registers and dispatches new connect tools
  - delegates all connect logic to `mahanai/connect.py`
- `mahanai/agent.py`
  - exposes slash commands for connect status and grant management
  - adds connect tool descriptions to the agent tool list

## Connect tool surface

The model should get narrow tools instead of raw config or raw privileged access.

### `connect_get_config_view`

Returns a sanitized config snapshot for agent use.

Properties:

- includes only non-secret readable values
- excludes or redacts secrets
- includes connect grant status

### `connect_request_config_change`

Requests a single config mutation or a small batch of related non-secret mutations.

Input:

- `changes`: object or list of key/value updates
- optional `reason`

Behavior:

- validate requested keys against the mutable allowlist
- reject secret or blocked keys before approval
- show a structured before/after summary
- apply only after approval or active session grant

### `connect_run_user_command`

Requests execution of a shell command through connect.

Input:

- `command`
- optional `cwd`
- optional `timeout_seconds`
- optional `reason`

Behavior:

- evaluate risk using a connect-specific approval path
- require per-action approval for high-risk commands
- allow session grants only for non-high-risk connect commands
- execute and return stdout, stderr, exit code, and cwd

### `connect_request_rerun`

Generates a rerun handoff request for the user.

Input:

- `reason`
- optional `suggested_command`
- optional `notes`

Behavior:

- returns structured text the CLI can render clearly
- does not itself modify config or execute commands

## Config policy

### Secret fields

The following must be treated as unreadable and unwritable through connect:

- `api_key`
- `nvidia_api_key`
- `codex_token`
- `store_token`
- `custom_endpoint.api_key`
- any future config field explicitly marked secret

### Allowed mutable fields in v1

Connect should allow changes to most non-secret app settings already persisted in config. This includes categories such as:

- model selection defaults
- theme settings
- effort-related settings if persisted
- autonomous mode related settings if persisted in config
- interact settings
- chat history settings
- approval preferences that are not secret
- connect-specific settings and grant preferences
- custom endpoint URL and model metadata, but not endpoint API keys

### Unknown field policy

Unknown or unclassified fields are denied by default. This avoids accidental exposure if new config keys are added later.

## Approval model

### Config approvals

Approval prompt must show:

- keys being changed
- before and after values for non-secret fields
- explicit notice if any requested field was blocked

Approval outcomes:

- allow once
- allow for session for connect config changes
- deny

### Command approvals

Connect command approvals are separate from normal `run_command` approvals.

Approval prompt must show:

- command
- cwd if present
- risk classification

Approval outcomes:

- allow once
- allow for session for connect commands
- deny

High-risk commands always fall back to allow once or deny. Session grant must not bypass high-risk review.

### Grant storage

Session grants should live in process memory for the current MahanAI run. They do not persist across restarts.

Suggested grant flags:

- `config_session_granted`
- `command_session_granted`

## Slash commands

### `/connect`

Shows:

- summary of connect capabilities
- whether config session grant is active
- whether command session grant is active
- reminder that secrets are never exposed through connect

### `/connect grants`

Shows active connect session grants.

### `/connect revoke`

Clears active connect session grants.

## Error handling

Connect operations should return machine-readable JSON errors with clear policy messages.

Cases:

- secret access attempt
- blocked config field
- invalid payload
- user denied approval
- high-risk command requires per-action approval
- execution failure

## Testing plan

Tests should be written first.

### Config tests

- sanitized config view hides secret top-level fields
- sanitized config view hides secret nested fields
- non-secret fields remain visible
- blocked secret mutation is rejected before approval
- allowed non-secret mutation requests approval and writes on approval
- unknown config fields are denied

### Command tests

- connect command denial returns user-denied payload
- non-high-risk command executes after approval
- session grant bypasses repeated approval for non-high-risk commands
- high-risk command still requires per-action approval even with session grant

### Slash command tests

- `/connect` shows status
- `/connect grants` reflects current session state
- `/connect revoke` clears grants

## Implementation notes

- Reuse existing high-risk command detection logic where possible, but keep connect approval storage separate from `run_command`.
- Do not let connect expose `_read_config()` results directly to the model.
- Prefer explicit allowlists over broad "all non-secret" reflection.
- Keep the first version local to the CLI and tool system. Do not add server endpoints in this change.

## Open decisions resolved

- Exposure surface: tool plus slash commands
- Approval model: both per-action and per-session
- Config scope: most non-secret app settings
- Server API: excluded from v1
