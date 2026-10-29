# Homepage native integration audit — conservative first slice

Control job: https://github.com/sierra-alpha/ai-whisperer/pull/65

## Implemented in this draft

Homepage already runs in Kubernetes service-account mode (`homepage/config/kubernetes.yaml`) with read-only pod/node and metrics API RBAC (`homepage/rbac.yaml`). The previous dashboard work intentionally removed a crowded, poorly labelled cluster-metrics header. This change does **not** restore that header.

Instead, three existing Homepage tiles now use the native Kubernetes service integration to show per-service pod CPU/memory data when the cluster metrics API is available:

| Tile | Namespace | Actual Deployment pod label | Selector |
| --- | --- | --- | --- |
| Audiobookshelf | `audiobookshelf` | `app: audiobookshelf` | `app=audiobookshelf` |
| Coqui TTS | `tts-server` | `app: tts-server` | `app=tts-server` |
| Homepage | `homepage` | `app: homepage` | `app=homepage` |

The explicit `podSelector` is necessary because these manifests use `app`, not the `app.kubernetes.io/name` label that Homepage's default `app` lookup expects. No new RBAC privileges or secrets are needed. Existing links, layout, host validation, and uptime responsibilities are unchanged.

Official syntax: https://gethomepage.dev/configs/kubernetes/ (Services and `podSelector`).

## Deferred until safe credentials and validation exist

- **Argo CD native widget:** A useful next step, but it requires an API token. Do not commit tokens or embed them in generated ConfigMaps. First confirm the desired read-only Argo CD account and exact API endpoint, provision a narrowly scoped token through the operator's 1Password workflow, then wire a Kubernetes Secret to a `HOMEPAGE_VAR_*` environment variable and reference it in the widget. Keep the token out of logs, PRs, and browser-visible configuration. Review the RBAC and rotation path before enabling.
- **Other service widgets:** Audiobookshelf, Grafana, Gatus and Frigate have API-backed widgets, but the present service tiles are intentionally link-only. Do not guess API keys, cluster reachability, or widget endpoints.
- **Link reachability:** The existing links are source-verified from manifests or operator configuration; no live LAN/Tailscale/browser checks have been performed in this draft.

## Validation before rollout

1. Parse `homepage/config/services.yaml` and verify each native integration has a non-empty namespace and selector matching a current Deployment pod label. Ensure the three tiles are not duplicated.
2. Render `homepage/kustomization.yaml` with Kustomize. Confirm generated `homepage-config-<hash>` and the Deployment's ConfigMap reference match; a source change should produce a new pod-template reference even with `subPath` mounts.
3. Verify the metrics API is installed and the existing Homepage ServiceAccount can list/read pod and node metrics. Do not broaden RBAC speculatively.
4. After explicit operator merge/rollout approval, inspect Homepage logs and tile metrics from the operator's LAN/Tailscale browser. Missing metrics should not hide the working link.

No merge, deployment, secret changes, or live cluster mutations are authorized by this draft.
