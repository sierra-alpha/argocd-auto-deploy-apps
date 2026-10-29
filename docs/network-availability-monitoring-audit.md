# Network availability, latency and loss — evidence-backed design audit

Control job: https://github.com/sierra-alpha/ai-whisperer/pull/56

## Repository evidence and boundary

This repository contains Kubernetes application manifests and a Grafana dashboard
ConfigMap with K3s/node metrics, but it does **not** define the Gatus host
configuration or a verified WAN/LAN probe exporter. A Grafana dashboard alone
cannot establish network health. Do not add a speculative PrometheusRule or
Blackbox Exporter installation without confirming the installed monitoring
stack and its scrape/alert ownership. Gatus and host-side checks may belong
in the Ansible/IaC repository rather than this Argo CD repository.

## Monitoring matrix

| Signal | Proposed vantage point | Test and evidence | Failure interpretation |
| --- | --- | --- | --- |
| Local gateway availability | Always-on LAN host | ICMP/TCP to router LAN address; record response time and success | Gateway path unavailable; not proof of ISP outage |
| LAN DNS resolution | Always-on LAN host | Query configured resolver for a known internal name and a public name | Resolver, DNS routing or upstream issue; compare with direct upstream DNS |
| WAN reachability | LAN host, beyond router | HTTP/TLS to two unrelated known-good public origins, plus optional ICMP where permitted | Distinguish ISP outage from one provider outage |
| Packet loss and RTT | LAN host, bounded periodic samples | Repeated ICMP to gateway and external targets with sample count and p50/p95 RTT | Avoid treating a single dropped packet as an outage; record sample window |
| K3s service reachability | Cluster pod or existing Gatus vantage | HTTP/TCP against critical in-cluster Services and external ingress | Distinguish internal workload/network failure from WAN outage |
| Monitoring self-health | Independent service or host | Probe freshness, exporter `up`, last successful scrape and notifier delivery | Missing data is unknown, not a healthy zero |

The monitoring service must be independent of K3s for Internet/DNS/router
checks if K3s itself can be down. The user-facing dashboard should link to
the authoritative uptime view rather than duplicating alert logic.

## Alert design and noise control

Use the existing notification transport with deduplication and explicit
recovery messages. A reasonable *proposal*, pending measurement, is to alert
only after at least three consecutive failed 30-second probes for critical
reachability, and to summarize short latency spikes instead of paging.
Correlate gateway + DNS + external HTTP before labelling an incident as an
ISP outage. Escalate missing probe data separately; do not report unknown as
healthy. Include a working dashboard deep link and the failing vantage point.

## Implementation prerequisites and safe next steps

1. Locate the currently deployed Gatus configuration and Prometheus scrape
   definitions in the authorized IaC repository; do not assume this GitOps
   repository owns them. Identify existing probes, Pushover routing and
   alert deduplication to avoid duplicate pages.
2. Confirm probe host and DNS resolver addresses from live inventory without
   publishing credentials or sensitive internal topology.
3. Establish read-only baseline latency and loss for a week. Select
   thresholds from measurements and confirm whether ICMP is permitted.
4. Implement the smallest set of probes at the appropriate existing owner.
   Add deterministic syntax/config validation, failure simulation and
   explicit unknown/stale state tests before rollout.
5. Add Grafana panels only after verifying exporter metric names and labels;
   do not ship empty or misleading dashboards.
6. Obtain operator approval for any monitoring config deployment, firewall
   rule, service account, notification escalation or production restart.

## Acceptance evidence

Record probe config and owner, one simulated gateway failure, one DNS-only
failure, one external-origin failure, packet-loss/RTT samples, notification
deduplication/recovery, and an independent self-health check. Verify the
monitoring survives K3s downtime. All tests must be read-only or isolated
until approved.

This audit proposes no live change, new credentials, merge, deployment or
additional cluster privileges.
