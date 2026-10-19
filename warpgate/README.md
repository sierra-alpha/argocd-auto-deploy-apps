# Warpgate trial

This revision activates Warpgate through `app-of-apps/warpgate.yaml` with one
replica, automatic sync and no automatic pruning. It replaces the original
zero-replica proposal after explicit owner approval. Missing 1Password items or
the cert-manager certificate prevent startup; no fallback credentials are made.
No Gatus Linux account or sudo policy is changed. The owner accepted the existing
`readonly-audit` account's sudo permissions; it is not technically read-only.

## Create one 1Password Login item

Vault: **K8s Service Account**. Item title: **warpgate**. Type: **Login**.

| Location | Field label | Value |
| --- | --- | --- |
| Standard Login fields | `username` | `admin` (or your preferred initial administrator name) |
| Standard Login fields | `password` | A new strong password |
| Standard Login fields | website | `https://warpgate.app.sierraalpha.co.nz` |
| Custom section **Encryption** | `encryption-key` | Concealed field; exactly 32 random bytes, base64 encoded; generate once with `openssl rand -base64 32` |

Keep username/password/website as the built-in Login fields for browser autofill,
not duplicate custom fields. Section names organize the item; field labels must
be unique across the whole item. Use the exact lowercase `encryption-key` label.
The operator maps item fields to one Kubernetes Secret, `warpgate`, in namespace
`warpgate`. The main container references only `encryption-key`; the init container
also reads username/password. No `envFrom` imports the entire item into the pod.
See [the operator's field mapping documentation](https://github.com/1Password/onepassword-operator/blob/main/USAGEGUIDE.md#how-1password-items-map-to-kubernetes-secrets).

Keep the encryption key permanently backed up; do not regenerate it on a sync or
restart. Never paste its value or your password in Git/chat. Bootstrap creates
the named administrator idempotently; changing the vault password does not reset
an already-created user's password. Update it in Warpgate and keep the Login item
in sync. Changing the username would create another administrator on the next
pod initialization, so keep that field stable after bootstrap.

**TLS is not a 1Password item.** A Certificate uses the existing
`letsencrypt-production` ClusterIssuer/Cloudflare DNS-01 configuration to create
`warpgate-tls` for `warpgate.app.sierraalpha.co.nz`. No public ingress is created.
The TLS Secret is mounted directly. The main container watches its content and
restarts Warpgate on renewal (active sessions will disconnect). Encryption-key
rotation still requires a coordinated rollout and upstream key-rotation steps.

## Private access and remaining runtime checks

The Service is ClusterIP, exposed only through the existing Tailscale operator
as device `warpgate`, on HTTPS 443 and SSH 2222. Its proxy uses the operator's
existing default tags/tailnet grants. No tailnet ACL is widened by this commit;
verify those existing grants before adding sensitive targets. The namespace's
network policy allows incoming traffic only from this Service's labelled proxy
pods in `tailscale`; other ingress and all egress remain denied.

The certificate hostname must resolve to the new proxy's tailnet IP on your
client. cert-manager's DNS-01 challenge does **not** create this A/AAAA record.
After the operator assigns the proxy IP, configure private DNS for
`warpgate.app.sierraalpha.co.nz`; then visit `https://warpgate.app.sierraalpha.co.nz`.
Do not bypass TLS verification or point this name at the public ingress address.
The generated MagicDNS name alone does not match this custom-domain certificate.
The operator labels/network policy, actual tailnet grants and DNS need runtime
verification; they were not tested against the live cluster.

A retained 2Gi PVC uses K3s `local-path` storage. If that StorageClass is absent,
the PVC will remain pending. It is single-node storage, not HA or a backup.
Quiesce the single writer before consistent PVC backups; retain the encryption
key separately. The Argo PVC annotations disable automatic pruning/deletion.

## LAN HTTPS access (alongside Tailscale)

A dedicated Traefik `IngressRoute` now accepts **only HTTPS** on the existing
`websecure` entrypoint for `warpgate.app.sierraalpha.co.nz`. The original
Tailscale operator proxy still exposes HTTPS 443 and SSH 2222; no Service
LoadBalancer/NodePort, public Funnel or router-port-forwarding is introduced.
Traefik forwards HTTPS to the existing Warpgate port 443 and uses a
`ServersTransport.serverName` matching the cert-manager certificate hostname
to **verify** the backend TLS connection. No insecure TLS verification option.

LAN DNS already maps `*.app.sierraalpha.co.nz` to
`192.168.1.250` in the infrastructure repository's
`dns-server/dns-server.conf`. When using the LAN resolver, opening
`https://warpgate.app.sierraalpha.co.nz` should reach the K3s Traefik
websecure listener. The LAN `Middleware` permits `192.168.1.0/24` only;
update that CIDR **after review** if your client is in a different VLAN.
The new NetworkPolicy authorizes traffic to Warpgate's HTTPS pod port
`8888` only from the `kube-system` Traefik controller pods, leaving SSH
private to the Tailscale proxy.

**Do not publish this Traefik listener through the WAN or a public reverse
proxy.** The IP allowlist checks Traefik's observed client IP; a source-NAT
router, forwarded port, or proxy may hide the true client origin, so the
allowlist alone is not sufficient proof that this is LAN-only. Preserve
client source addresses and verify the router has no WAN forward for
this route. From a device with no Tailscale, test that an external
connection to this hostname cannot access Warpgate before placing
privileged credentials behind it.

On LAN you can use the **web administration UI only**. The LAN ingress does
not expose raw SSH port `2222`; it remains accessible via the Tailscale
operator. Don't point a public DNS record at the LAN Traefik proxy merely
to make access work from a remote network.

## Gatus target: configure after login

The UI can start without a Gatus SSH credential. Keep the current
`readonly-audit` account; no new Linux account is required. Configure its existing
valid SSH credential through Warpgate's authenticated target editor, for
`rampidv1-2--1.sierraalpha.co.nz`, username `readonly-audit`, SSH port 22, with a
verified host key. Do not import personal administrator keys. An SSH private key
stored in 1Password is **not automatically registered as a Warpgate target** by
the Kubernetes operator; native target configuration is still needed.

Target connectivity remains denied until a narrowly scoped egress rule is added
for the verified Gatus address (or a dedicated tailnet egress proxy). No guessed
address or blanket network allow is included. This does not block exploring the
admin UI. Before target use, require administrator approval on that target and
set approval cache to NONE; separate requester from approver. Test deny, expiry,
reconnect and simultaneous requests. Session approval does not constrain commands.

## Offline checks

Requires Helm 3, Kustomize 5, Python 3 and PyYAML:

```sh
helm lint warpgate/vendor/warpgate-0.1.0.tgz -f warpgate/values.yaml
python3 warpgate/validate.py
python3 warpgate/test_tls_watch.py
kustomize build warpgate/manifests
```

`HELM`/`KUSTOMIZE` may point to local binaries. The chart archive remains upstream
0.1.0 with its verified checksum, explicitly using Warpgate 0.29.2. Rendered output
is checked into `manifests/upstream.yaml`; rerender it with `sh warpgate/render.sh`.
No CI or live infrastructure validation is needed to run these checks. See
`DESIGN.md` for the original HA and future broker/phone approval analysis.
