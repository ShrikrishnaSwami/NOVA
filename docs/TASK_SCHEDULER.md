# NOVA task scheduler

NOVA's task scheduler stores jobs and run history in the same local SQLite database used for memory. It starts with the local API service and stops cleanly with that service.

## Current safe actions

- `system.snapshot`: collect CPU, memory, and platform status.
- `storage.report`: collect disk capacity and free-space information.

These first actions are read-only. A task is created in `pending_approval` and does not run until the user approves it. Approved jobs can run once, daily, or weekly. Jobs can be paused or cancelled, and each execution is recorded in local history. A failed execution is marked failed rather than silently retried. If Windows notifications are enabled, NOVA reports completed or failed scheduled jobs and significant system-monitor alerts using native Windows notifications.

## API

- `GET /tasks/capabilities` — supported actions and recurrence options.
- `POST /tasks` — create a task; requires a timezone-aware future `schedule_at` value.
- `GET /tasks` — list tasks; optional `status` and `limit` filters.
- `POST /tasks/{id}/approve` — approve the exact scheduled task.
- `POST /tasks/{id}/pause` — pause a scheduled task.
- `POST /tasks/{id}/cancel` — cancel a task.
- `GET /tasks/{id}/history` — inspect execution records.

Example request:

```json
{
  "title": "Daily system snapshot",
  "action_id": "system.snapshot",
  "parameters": {},
  "schedule_at": "2030-01-01T09:00:00-05:00",
  "recurrence": "daily"
}
```

## Security boundary

The scheduler does not execute arbitrary commands, scripts, model-generated code, or arbitrary filesystem operations. Only actions registered in the task handler registry can run. The initial registry contains read-only reporting actions only. Software installation, Windows Update, deletion, registry changes, shutdown/restart, and other mutating operations are deliberately not schedulable in this first milestone. They need separate typed implementations, scoped permissions, and explicit approval UX before they can be added.

The API is intended to remain bound to loopback. It is not a hardened multi-user scheduler service.
