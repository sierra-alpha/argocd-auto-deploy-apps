# K3s workload, storage and alerting — evidence-backed audit

Control job: https://github.com/sierra-alpha/ai-whisperer/pull/59

## Already declared in GitOps (2026-10-29 repository inspection)

- `app-of-apps/kube-prometheus-stack.yaml` deploys Helm chart
  `kube-prometheus-stack` version `91.8.2` in `monitoring`. Prometheus
  ServiceMonitor selectors are configured to allow discovery across namespaces.
  The chart may include default alert rules, but this repository does not
  demonstrate their live status, alert routing or notification delivery.
- `app-of-apps/grafana-dashboards.yaml` manages a Grafana dashboard ConfigMap
  through Argo CD with `prune: true` and `selfHeal: true`.
- `grafana-dashboards/dashboards.yaml` already defines a **K3s overview**
  with ready-node count, running/unhealthy pod counts, 24-hour container
  restarts, node CPU/memory and top restarting containers. It also defines
  a Trivy security dashboard.
- `app-of-apps/trivy-operator.yaml` enables a ServiceMonitor for Trivy.

Do not duplicate these metrics or claim they are absent. This is Git
configuration evidence, not proof the exporters, queries or alerts are
currently healthy. No dedicated Loki/Vector/Fluent Bit log collector or
custom `PrometheusRule` manifests were found in this GitOps tree; they may
be deployed from other owners or chart defaults.

## Gaps to validate before adding anything

| Need | Existing repository evidence | Safe next validation |
| --- | --- | --- |
| Critical node health | Ready-node count and CPU/memory panels | Verify node exporter and kube-state-metrics series exist, then test node-down alert and notification route |
| Pod restarts and failures | 24h restarts and unhealthy pod panels | Check alert rule ownership, distinguish CrashLoopBackOff from intentional rollouts, set `for` durations |
| Persistent volumes and free space | No dedicated PVC capacity panel in checked dashboard | Verify `kubelet_volume_stats_*` and `kube_persistentvolumeclaim_status_phase` metrics for each PVC; identify hostPath volumes absent from PVC metrics |
| Critical application endpoints | Workload metrics alone cannot prove HTTP/DNS service availability | Reuse existing Gatus service checks and add missing critical services in the appropriate owner, avoiding duplicate pages |
| Log search and retention | No declared collector in this GitOps tree | Decide whether existing host journal/container logs suffice; only then consider Loki with retention, resource and privacy limits |
| Alertmanager routing and silence | Helm chart present, route/receivers not verified here | Inspect actual Alertmanager config and secret ownership without exposing credentials; test delivery and deduplication |
| Observability self-health | Scrape/alert health not established by a dashboard | Alert on missing scrape targets, failed evaluation and stale metrics, not just zero values |

## Candidate queries (do not deploy as rules without checking live metrics)

- Node readiness: `kube_node_status_condition{condition="Ready",status="true"} == 0`.
- Pending PVC: `sum(kube_persistentvolumeclaim_status_phase{phase="Pending"}) > 0`.
- High PVC usage: `100 * kubelet_volume_stats_used_bytes / clamp_min(kubelet_volume_stats_capacity_bytes, 1) > 85`, grouped by namespace/PVC and guarded against missing series.
- Restart bursts: `sum by (namespace, pod) (increase(kube_pod_container_status_restarts_total[15m])) > 3`, excluding intentional rollouts where appropriate.

These are **design candidates**, not validated alerts. Confirm labels,
scrape coverage, default rule overlap, noise and operator notification
preferences before applying. Use warning vs critical severity and a bounded
`for` window; do not page on a single restart.

## Safe implementation sequence

1. Read-only query the deployed Prometheus API for the metrics above, count
   missing series, inspect Alertmanager route/receivers without copying secrets.
2. Check existing default kube-prometheus-stack alerts and Gatus/host alert
   ownership to avoid duplicate Pushover messages. Reuse the shared
   notification provider/event contract from AI Whisperer control job #80
   (implementation `sierra-alpha/salt-setup` PR #11); do not create a
   separate ad-hoc notification provider.
3. Choose the smallest missing visibility slice (PVC capacity + critical
   workload restart alert), and add a reviewed dashboard/PrometheusRule only
   after verifying the chart's rule label selector.
4. Render manifests offline and simulate one failure/recovery in an isolated
   environment. Verify no accidental Argo CD prune or ServiceMonitor change.
5. Obtain explicit operator approval for merge, deployment and any notification
   escalation. Do not turn on a log collector without resource/retention sizing.

No live queries, credentials, merges, deployments or cluster mutations were
performed for this audit.
