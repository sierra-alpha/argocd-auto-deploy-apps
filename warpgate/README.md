# Warpgate: disabled GitOps proof of concept

**Draft only. Merging these files does not install Warpgate.** Nothing references
this directory from `app-of-apps/`. The optional Application is a `.example`, has
no automated sync or deletion finalizer, and requires a reviewed commit SHA.
The workload also has **zero replicas**, no bootstrap Job, no generated Secret,
no external route, and deny-all ingress/egress. Do not add it to app-of-apps or
raise replicas as part of this PR. No cluster, host, DNS, ACL, secret or SSH
changes were made. Control: [AI Whisperer #84](https://github.com/sierra-alpha/ai-whisperer/pull/84).

## Package and repository decisions

- Upstream OCI chart: `oci://ghcr.io/warp-tech/helm-charts/warpgate:0.1.0`.
  Registry manifest digest: `sha256:6ded301e4550429804cba82f6dcb5391e01ce53afa35c055682d3e120a9bfbe3`.
  Unmodified archive in `vendor/` has SHA-256
  `bc08603ba778d4a76fa0090186bac6759a41170225f548bf15d0c8fb160d3e8d`.
- Image explicitly pinned to `ghcr.io/warp-tech/warpgate:0.29.2`, the stable
  release verified 2026-10-18 UTC. The published chart's `appVersion` and labels
  still say `0.29.0`; **the actual container image is 0.29.2**. No beta/latest.
- Prefer the upstream chart, but render it offline and commit the output:
  chart 0.1.0 has no probe, token-automount, or Deployment strategy controls.
  `manifests/kustomization.yaml` applies those small patches using the repo's
  existing Kustomize convention. This avoids a custom Argo plugin/post-renderer
  or a fork of upstream templates. Argo consumes only `warpgate/manifests`.
- Existing apps use Argo Applications, and some use Kustomize. Existing public
  Traefik/cert-manager ingress and automatic sync are intentionally unsuitable
  for this gateway. `tailscale-config` uses `OnePasswordItem`; reuse that
  provisioning convention only after an owner chooses actual vault items.
- SQLite plus one externally managed RWO PVC keeps the PoC small. Recreate
  prevents overlapping writers during upgrades. **Never scale SQLite above 1.**
  Local-path storage does not provide host failover; choose storage explicitly.

`values.yaml` is the Helm input; `manifests/upstream.yaml` is generated, not
hand-edited. The chart is vendored (about 10 KiB) so review and validation require
no registry, cluster, credentials or network. Its upstream license is included
in `vendor/LICENSE.warpgate`.

## Offline validation

Requires Helm 3, Kustomize 5, Python 3 and PyYAML. Tested with Helm 3.19.0,
Kustomize 5.7.1 and Python 3.13. These commands do not install anything:

```sh
helm lint warpgate/vendor/warpgate-0.1.0.tgz -f warpgate/values.yaml
sh warpgate/render.sh > /tmp/warpgate-upstream.yaml
cmp /tmp/warpgate-upstream.yaml warpgate/manifests/upstream.yaml
kustomize build warpgate/manifests > /tmp/warpgate-reviewed.yaml
python3 warpgate/validate.py
```

`HELM` and `KUSTOMIZE` may point to local binaries. The validator verifies the
archive checksum, renders twice to detect random credential/certificate drift,
checks committed output, and inspects the final Kustomize resources. Negative
cases reject enabled replicas, public Services, optional encryption keys, open
networking and extra listeners. No CI workflow is added.

Recorded result: Helm lint passed; all seven regression checks passed; final
Kustomize output passed kubeconform 0.7.0 strict validation against locally
cached Kubernetes 1.31.0 schemas (6 valid, 0 invalid/errors/skipped). The cluster
version is unverified; repeat against its actual version before rollout. For
an optional offline schema check, point kubeconform at a pre-fetched local
schema directory with `-schema-location` (do not use its network default).

Offline checks cannot prove runtime compatibility, storage ownership, actual CNI
policy enforcement, tailnet ACLs, TLS identity, native approval behaviour or
phone usability. These remain controlled staging acceptance checks. Resource
budgets are initial test limits, not measured sizing. Pinning is reproducibility,
not a claim of a completed vulnerability audit.

## Human-gated opt-in checklist (do not execute while owner is offline)

1. Review this draft and the [HA/integration design](DESIGN.md); approve a
   **test-only** deployment separately from merge. Check the current Argo
   application discovery paths still exclude this directory. Choose an Argo
   project limited to the Warpgate namespace; the example mirrors this repo's
   `default` project but is not a production RBAC recommendation.
2. Choose the storage class, retained-volume lifecycle, backup destination and
   recording retention. `storage.yaml.example` is deliberately excluded from
   Kustomize. Provision `warpgate-data` separately; ensure UID/GID 1000 can write
   it and restore works. Do not inherit an unknown default StorageClass.
3. Outside Git, provision `warpgate-encryption` with `encryptionKey`: one stable,
   cryptographically random 32-byte base64 value. Back it up separately from the
   database. Provision `warpgate-tls` (`tls.crt`, `tls.key`) for the **chosen**
   private hostname and trusted issuer. No hostname, vault item or TLS identity
   is invented here. The key reference is mandatory: a missing Secret prevents
   startup. Kubernetes Secrets are not encrypted merely because they are
   base64; require encrypted secret delivery, etcd/PVC/backup protection and
   namespace RBAC. Gateway encryption does not encrypt all recordings or logs.
4. Review private access before bootstrap. Keep the ClusterIP service; use a
   dedicated Tailscale operator proxy for **SSH 2222 and TLS 8888**, with a
   reviewed private hostname/tag and no Funnel/public ingress. Restrict grants
   to the isolated requester (SSH) and owner/approver (HTTPS); decide whether
   the requester needs a separate web-login path. Add narrowly scoped ingress
   allows matching the actual operator proxy namespace/pod labels, and egress
   only to the approved test host/IP and port. Add DNS egress only if needed.
   Do not permit every pod in the `tailscale` namespace by default. Verify how
   proxy source addresses appear before trusting source-IP policy. Require CNI
   NetworkPolicy enforcement and prove LAN/public/direct-ClusterIP denial.
   This PR intentionally supplies **no allow rules or operator annotations**:
   there is no usable network route until those site-specific controls exist.
5. Bootstrap under owner supervision with one temporary restricted container
   using the same pinned image, PVC, config, TLS and encryption Secret. Keep the
   Deployment at zero while the bootstrap container uses SQLite. Copy config
   and TLS into `/data` as the normal initContainer does. Supply a *new*
   bootstrap password only through an ephemeral external Secret/env
   `WARPGATE_NEW_USER_PASSWORD`, then run inside that container:
   `warpgate -c /data/warpgate.yaml create-user --role warpgate:admin poc-bootstrap`.
   Do not put a password on argv or in Git/logs. Remove the temporary container
   and bootstrap password reference afterward; use named administrator accounts
   and remove the bootstrap account after verification. No unattended setup
   hook is used: it can regenerate material/reset bootstrap state under Argo.
6. In a separately reviewed change, allow **one** replica and the approved
   private admin route, pin the example Application to that commit, then
   explicitly install/sync it. Verify HTTPS, probes, non-root PVC writes,
   encryption initialization and restart behaviour before adding any target.
   Missing TLS/key/PVC must fail closed. Secret rotations require an explicit
   restart because the encryption key is an env var and TLS is copied at init;
   config changes have a checksum restart annotation.
7. Create a dedicated requester account without administrative permissions and
   an access role containing **only one disposable TEST SSH target**. Configure
   the target's fixed SSH username, address, port and verified host key. Use a
   newly created gateway-to-test identity; authorize its public key only on that
   test account. Never copy personal/1Password keys or existing admin credentials.
   Keep requester-to-gateway identity distinct from gateway-to-target identity.
8. On the test target select `Access control` →
   **Require administrator approval for each connection**. Under `Config` →
   `Global parameters` → `Session approvals`, leave **Admin approval cache
   period = NONE/unset** (API `admin_approval_grace_period_seconds: null`).
   Set an explicit bounded pending-request timeout, e.g. 120 seconds, and test
   it. These are database/UI settings, **not Helm values**. Create a separate
   approver role with `Sessions > Approve` and only other permissions proven
   necessary by UI testing; no target editing, credential management or broad
   administrator role for the requester. Approve only the named target, never
   “all targets”. Screenshot/config evidence should exclude credentials.
9. On the test host deny sudo, agent/X11/TCP forwarding and unrelated resources;
   restrict login to the gateway source and, where useful, a forced command or
   disposable sandbox. Review command restrictions for the specific experiment.
   **Session approval authorizes a connection, not its commands.** Neither a task
   description nor Warpgate recording makes unrestricted shell access safe.
10. Complete the staging matrix below before granting the requester any route.
    Production accounts/targets, OIDC integration, HA, secret provisioning,
    key installation, DNS/firewalls/Tailscale policy, merges and deployments
    each require explicit approval. Keep the current 1Password native-prompt
    bridge and its keys unchanged.

## Staging acceptance matrix

Use only the new test identities; record results without private keys, tokens,
passwords or session content in this repository.

| Check | Required result |
| --- | --- |
| Unauthenticated/unauthorized requester | No target access; no self-approval |
| Pending request with no owner response | No target shell, expiry rejects it; fresh attempt needs new approval |
| Explicit deny | Target never connected; reconnect prompts again |
| One approved connection then reconnect | New request despite same user, source IP and target |
| Two simultaneous connections | Approving A leaves B blocked; each needs its own decision |
| Wrong target/changed identity or expired request | Existing decision cannot authorize the changed request |
| Direct SSH, LAN/public gateway path, unrelated pod | Network denied, including both 2222 and 8888 |
| Requester attempts admin UI/API or session approval | Forbidden; owner uses separately authenticated account |
| Restart and missing/malformed key | Correct key preserves access; missing Secret prevents pod start, malformed key fails; no silent key generation |
| Recording and audit | Approved session attributed correctly and playback accessible only to authorized reviewer |
| Restore and reboot | Test state, verified SSH host identity and recording playback survive; restricted policy remains |
| Revocation/termination | New connections denied and active test session explicitly terminated; deny is not assumed to kill existing sessions |

Warpgate may display session/request metadata but not the trusted AIW task intent.
Do not call this a production approval system until the broker binding in
`DESIGN.md` is implemented and audited.

## Recording, recovery and upgrades

Enable recordings in the final database/global settings and confirm the configured
`/data/recordings` path after first boot (the file setting is a legacy import).
Treat terminal output as sensitive: commands can contain passwords and personal
data. Agree retention, quota/capacity alerts, authorized playback roles and
third-party backup location before use; do not send transcripts to Pushover.

For SQLite backup, quiesce the single writer and snapshot/copy the whole retained
PVC (database plus any SQLite journals, config, TLS and recordings) consistently.
Escrow the encryption key separately with access-controlled recovery. Encrypt
backups, test retention and restore onto an isolated PVC/namespace with deny-all
networking. Never attach a second live instance to the same SQLite data. Verify
users/roles, pending-approval behaviour, host keys, TLS, decryption and recording
playback with test accounts before restoring a route. A new independently
initialized instance is not a restore and may present different SSH host keys.

Upgrade only after an isolated restore test: review release/migration notes,
verify a new chart archive checksum and image tag/digest, regenerate output,
run validation and review the Kustomize diff. Take a recoverable pre-upgrade
snapshot; do not assume database migrations can be rolled back with just an old
image. Stop access/scale down under approval if a test fails. Retain the PVC and
escrow key when removing the Application; deleting Argo must not erase recovery
material. Follow upstream coordinated key rotation; never replace the current
key without its recovery predecessor and a backup.

## Sources checked

- [Stable release](https://github.com/warp-tech/warpgate/releases/tag/v0.29.2)
  and [chart source](https://github.com/warp-tech/warpgate/tree/v0.29.2/helm/warpgate).
  Published OCI archive is the rendering authority (its metadata differs from
  the release source); checksum is verified by `render.sh`.
- [Helm installation](https://warpgate.null.page/getting-started-on-helm/),
  [credential encryption](https://warpgate.null.page/encryption/),
  [backup guide](https://warpgate.null.page/backup/).
- [Native session approval semantics](https://warpgate.null.page/approvals/) and
  [v0.29.2 parameters](https://github.com/warp-tech/warpgate/blob/v0.29.2/warpgate-db-entities/src/Parameters.rs).
- [v0.29.2 create-user](https://github.com/warp-tech/warpgate/blob/v0.29.2/warpgate/src/main.rs)
  supports the environment password path used in the supervised bootstrap.
