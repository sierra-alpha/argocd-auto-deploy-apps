# NAS storage health, capacity and backup freshness — audit

Control job: https://github.com/sierra-alpha/ai-whisperer/pull/62

## What is already declared (read-only Git review, 2026-10-29)

- The existing `sierra-alpha/salt-setup` Ansible roles deploy **Beszel agents**
  and a Beszel hub. This establishes host telemetry plumbing, but this review
  does not prove which physical disks, mounts or SMART attributes are collected
  or that a particular dashboard is healthy.
- The Ansible-owned **Gatus** inventory on the monitoring host declares
  MinIO node liveness and **separate cluster-quorum** HTTP checks every 120
  seconds. Preserve both: a live MinIO process does not imply the object store
  has quorum or can serve administrative operations.
- `restic_backup` and `offsite_backup` roles declare onsite and offsite
  timers, restic check/retention, and opt-in Pushover `OnFailure` handling.
  Failure-only alerts do not prove a recent successful snapshot or a successful
  offsite restore. Coordinate freshness and recovery checks with the
  backup coverage audit in AI Whisperer #53 and `sierra-alpha/homelab` PR #4.
- The checked Ansible tree has no dedicated SMART/Scrutiny role or explicit
  filesystem-health exporter. That is a repository finding, not proof that
  the live hosts lack vendor monitoring or hardware-level alerts.

This GitOps repository is not the owner of host disk devices or SMART access.
Do not grant privileged Kubernetes pods host disks merely to add metrics;
prefer a narrowly scoped host-side exporter or existing Beszel integration
managed by Ansible.

## Proposed coverage and failure thresholds

| Signal | Read-only source | Suggested handling (requires baseline) |
| --- | --- | --- |
| SMART/NVMe health | Host `smartctl -H/-A` or `nvme smart-log` on explicitly inventoried devices | Critical on overall health failure; warning on worsening media errors, reallocations or spare exhaustion; no unattended destructive tests |
| Filesystem free space and inode exhaustion | Existing Beszel metrics or node exporter on actual mounted filesystems | Warning at sustained 85%, critical at 95% or short time-to-full; exclude pseudo-filesystems and ephemeral mounts |
| Filesystem / pool integrity | Host-specific ZFS/Btrfs/mdadm status where actually used | Critical on degraded pool or uncorrectable errors; avoid guessing storage technology |
| MinIO availability and quorum | Existing Gatus node liveness and cluster-quorum endpoints | Preserve current independent checks; correlate node-down with quorum loss |
| Onsite backup freshness | Latest successful restic snapshot timestamp per host | Alert if older than agreed RPO plus grace; failed timer and stale-success are distinct |
| Offsite backup freshness | Last successful Wasabi copy and independent repository inventory | Alert on overdue copy, missing expected datasets or unverified credentials; do not treat a successful command exit as restore proof |
| Monitor self-health | Exporter heartbeat, scrape success and alert delivery | Missing/stale telemetry is unknown, never green |

Thresholds are proposals only. Measure device baselines, sleep schedules,
expected snapshot gaps and disk replacement policy before paging.

## Minimum safe implementation plan

1. Inventory the actual NAS hosts, device names, filesystem/pool types, disk
   serials and data mount paths via authorized **read-only** host inspection.
   Do not publish serials, credentials or raw host environment dumps.
2. Confirm which disk and filesystem metrics Beszel already exposes. Reuse
   existing data where possible; only then choose a host-side SMART exporter.
3. Keep privileged SMART access on the host with least privilege and explicit
   device allowlists; do not mount `/dev` into a general-purpose monitoring
   Kubernetes workload.
4. Reuse the shared Pushover provider/event contract (AI Whisperer #80) and
   existing Gatus alert ownership. Implement stale-success checks for restic
   and offsite copy separately from `OnFailure` alerts.
5. Test a missing-disk/failed-health fixture, a full filesystem fixture,
   a stale-backup fixture and monitor-unavailable behavior without touching
   production disks or triggering real failure.
6. Obtain operator approval for any new package, systemd timer, privileged
   device read, Ansible deployment, alert escalation or cluster change.

## Evidence required to close the monitoring gap

A host/device coverage matrix; sample metrics with timestamps; verified
backup freshness per host; explicit critical/warning thresholds; one
notification and recovery simulation; and proof that the checks continue
when K3s is down. SMART self-tests, restore tests and hardware changes are
separate human-gated operations.

No live disk commands, secrets, merges, deployments or infrastructure changes
were performed for this audit.
