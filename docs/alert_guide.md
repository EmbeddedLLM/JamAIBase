# JamAIBase Alerting Guide

> A quick reference for what’s already in `vm-alert-config.yaml`. Update thresholds only if needed, and **remember to set the Discord `webhook_url` correctly**. As of 2025-10-22

---

## Recording Rules

**Group:** `storage.rules` (interval: **30s**)

- **ClickHouse free disk (%)**

  - **Record:** `chi_clickhouse_disk_free_percentage`
  - **Expr:** `(DiskFreeBytes / DiskTotalBytes) * 100`
  - **Labels:** `unit=percent`, `component=clickhouse`

- **VictoriaMetrics cluster disk usage (%)**
  - **Record:** `vmcluster_disk_usage_percentage`
  - **Expr:** (derived from `vm_data_size_bytes` and free disk)
  - **Labels:** `unit=percent`, `component=vmcluster`

---

## Alert Rules

> Update the threshold according to your need, especially for PostgreSQL

- **ClickHouseDiskSpaceLow**

  - **Expr:** `chi_clickhouse_disk_free_percentage < 10`
  - **For:** `1h`
  - **Labels:** `severity=critical`, `component=clickhouse`
  - **Meaning:** Free space < **10%** for 1h.

- **PostgreSQLDatabaseSizeTooLarge**

  - **Expr:** `cnpg_pg_database_size_bytes / 1024 ^ 3 > 10`
  - **For:** `1h`
  - **Labels:** `severity=warning`, `component=postgresql`
  - **Meaning:** DB size > **10 GiB** for 1h.

- **VMClusterDiskSpaceHigh**
  - **Expr:** `vmcluster_disk_usage_percentage > 80`
  - **For:** `1h`
  - **Labels:** `severity=critical`, `component=vmcluster`
  - **Meaning:** VM storage usage > **80%** for 1h.

**Routing & Inhibition (as configured):**

- All alerts route to **`jamaibase-discord`**.
- Sub-routes match `component` but currently target the same receiver.
- Inhibition: a `critical` alert suppresses a `warning` of the **same `alertname`**.

---

## Log Alerts (VictoriaLogs → vmalert)

> Structured alerts from app logs (`owl`, `starling`) evaluated every **30s** by `vmalert-log` against **VictoriaLogs**.

- **JamAIBase Exception**

  - **Match:** `severity:i(critical)` and exception fields present
  - **Agg by:** `service.name`, `code.filepath`, `code.function`, `code.lineno`, `_msg`, `exception.message`, `exception.stacktrace`
  - **When:** `count() > 0`
  - **Labels:** `severity=exception`, `component=jamaibase-log`

- **JamAIBase Error**

  - **Match:** `severity:i(error)`
  - **Agg by:** `service.name`, `code.filepath`, `code.function`, `code.lineno`, `_msg`
  - **When:** `count() > 0`
  - **Labels:** `severity=critical`, `component=jamaibase-log`

- **JamAIBase Warning** _(optional; enable/disable per need)_
  - **Match:** `severity:i(warning)`
  - **Agg by:** `service.name`, `code.filepath`, `code.function`, `code.lineno`, `_msg`
  - **When:** `count() > 0`
  - **Labels:** `severity=warning`, `component=jamaibase-log`

**vmalert (logs):** `vmalert-log` selects `vmalert/rule-type=logs`, datasource `VictoriaLogs :9428`, notifier `Alertmanager :9093`, interval **30s**.

---

## Discord Integration

- Get the webhook url from discord (server settings > integration > webhook)
- Update the webhook_url with the url generated

```yaml
- webhook_url: "https://discord.com/api/webhooks/XXXX/YYYY"
```

## Manual Trigger (Alertmanager API)

> Prefer rule-based alerts in Prometheus/vmalert for real monitoring.

**Prereq:** Reach Alertmanager on `:9093`. If inside the cluster, port-forward:

```bash
kubectl -n vm-operator port-forward svc/vmalertmanager-vmalertmanager 9093:9093
```

**Fire a test alert (firing):**

```bash
curl -XPOST http://127.0.0.1:9093/api/v2/alerts   -H 'Content-Type: application/json'   -d '[
    {
      "labels": {
        "alertname": "ManualSmokeTest",
        "severity": "critical",
        "component": "clickhouse"
      },
      "annotations": {
        "summary": "Manual test alert",
        "description": "End-to-end Discord delivery check."
      }
    }
  ]'
```

**Resolve the same alert (identical labels + endsAt):**

```bash
curl -XPOST http://127.0.0.1:9093/api/v2/alerts   -H 'Content-Type: application/json'   -d '[
    {
      "labels": {
        "alertname": "ManualSmokeTest",
        "severity": "critical",
        "component": "clickhouse"
      },
      "annotations": {
        "summary": "Manual test resolved",
        "description": "Marking alert resolved."
      },
      "startsAt": "'"$(date -u -d "-10m" +"%Y-%m-%dT%H:%M:%SZ")"'",
      "endsAt":   "'"$(date -u +"%Y-%m-%dT%H:%M:%SZ")"'"
    }
  ]'
```

**Force a fresh notification immediately (change fingerprint):**

```bash
curl -XPOST http://127.0.0.1:9093/api/v2/alerts   -H 'Content-Type: application/json'   -d '[
    {
      "labels": {
        "alertname": "ManualSmokeTest",
        "severity": "critical",
        "component": "clickhouse",
        "run_id": "'"$(date +%s)"'"
      },
      "annotations": {
        "summary": "Another ping",
        "description": "Forcing a new notification."
      }
    }
  ]'
```

**Notes (matches current config):**

- `group_by: ["alertname"]` → alerts with the same `alertname` are grouped.
- `group_wait: 10s` / `group_interval: 10s` → small, intentional delays before/between sends.
- `repeat_interval: 3h` → duplicate alerts with the **same label set** won’t resend within 3 hours.
- All routes currently go to **`jamaibase-discord`**; `component` is mainly for title templating/inhibition now, but keep it for future per-component routing.

---

### Field reference (JSON payload)

> Minimal payload = `labels` + `annotations`. Timestamps are optional but recommended for clarity.

- **`labels`** _(object, required)_ — define the alert’s identity (**fingerprint**) and routing.

  - **`alertname`**: Logical name (e.g., `ManualSmokeTest`). Used by `group_by: ["alertname"]`.
  - **`severity`**: Freeform (`warning`, `critical`, …). Your template adds `@here` for `critical`.
  - **`component`**: Freeform (`clickhouse`, `postgresql`, `vmcluster`, …). Useful for titles and future routing.
  - **(optional)** e.g., `instance`, `hostname`, or **`run_id`** to force a new fingerprint/notification.

- **`annotations`** _(object, required)_ — human-readable content for messages.

  - **`summary`**: One-liner.
  - **`description`**: A few sentences of detail.

- **`startsAt`** _(RFC3339 UTC, optional)_ — when the alert **started firing**. If omitted, Alertmanager treats it as “now”. Example: `2025-10-11T05:00:00Z`.

- **`endsAt`** _(RFC3339 UTC, optional)_ — when the alert **stops**.

  - **Firing**: omit `endsAt`, or set it **in the future**; AM considers it active.
  - **Resolved**: set `endsAt` **in the past** (and keep the _same labels_) to immediately resolve it.

#### Firing vs. Resolved — quick examples

- **Fire (no timestamps):**

```json
[
  {
    "labels": { "alertname": "ManualSmokeTest", "severity": "critical", "component": "clickhouse" },
    "annotations": { "summary": "Manual test", "description": "End-to-end Discord check." }
  }
]
```

- **Resolve (same labels + past `endsAt`):**

```json
[
  {
    "labels": { "alertname": "ManualSmokeTest", "severity": "critical", "component": "clickhouse" },
    "annotations": { "summary": "Manual test resolved", "description": "Marking resolved." },
    "startsAt": "2025-10-11T04:50:00Z",
    "endsAt": "2025-10-11T05:00:00Z"
  }
]
```

- **Force a fresh notification (new fingerprint via `run_id`):**

```json
[
  {
    "labels": {
      "alertname": "ManualSmokeTest",
      "severity": "critical",
      "component": "clickhouse",
      "run_id": "1697000000"
    },
    "annotations": { "summary": "Another ping", "description": "New fingerprint via run_id." }
  }
]
```

#### Practical tips

- **Fingerprint ≈ labels only.** Same labels → same alert; change any label (e.g., `run_id`) → new alert.
- **Grouping.** With `group_by: ["alertname"]`, different severities/components sharing the same `alertname` are batched after `group_wait`.
- **Time helpers (UTC/Zulu):**

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"                # now
date -u -d "-10 minutes" +"%Y-%m-%dT%H:%M:%SZ"
date -u -d "+30 minutes" +"%Y-%m-%dT%H:%M:%SZ"
```

- **Auto-resolution.** If a client doesn’t refresh a firing alert, AM eventually considers it resolved. For manual tests, either send a resolved payload or let it expire.
- Resolution timeout is defined in the manifest, ref. https://prometheus.io/docs/alerting/latest/configuration/

```
global:
  # ResolveTimeout is the default value used by alertmanager if the alert does not
  # include EndsAt, after this time passes it can declare the alert as resolved if it has not been updated.
  # This has no impact on alerts from Prometheus, as they always include EndsAt.
  [ resolve_timeout: <duration> | default = 5m ]
```
