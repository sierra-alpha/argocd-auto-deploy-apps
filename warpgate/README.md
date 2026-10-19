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

The web interface now uses the **same `networking.k8s.io/v1` Kubernetes
`Ingress` and `ingressClassName: traefik` routing pattern as Homepage**.
It routes `https://warpgate.app.sierraalpha.co.nz` on the existing
Traefik ingress and references the already provisioned
`warpgate-tls` cert-manager Secret. Homepage's existing
`traefik-redirecthttps@kubernetescrd` middleware handles HTTP → HTTPS.

Warpgate, unlike Homepage, terminates **its own HTTPS** on Service port 443.
The Service's Traefik annotations select HTTPS and reference the
`warpgate-verified-upstream` ServersTransport to validate its certificate
using `warpgate.app.sierraalpha.co.nz` as SNI. Do not disable TLS validation
or redirect Traefik to Warpgate over plaintext port 8888.

Just like Homepage, the active Ingress uses only
`traefik-redirecthttps@kubernetescrd`. The previous
`192.168.1.0/24` Traefik client-IP allowlist was rejecting legitimate
LAN visitors with HTTP 403 (for example, a different client subnet or
source-NAT at the ingress). It is **not attached to the active Ingress**.
A legacy Middleware remains attached only to the retired
`retired-warpgate-route.invalid` IngressRoute because ArgoCD automated
pruning is disabled.

The NetworkPolicy still allows only the `kube-system` Traefik pods to
reach Warpgate's HTTPS port 8888, while Tailscale proxy pods continue
serving HTTPS and SSH 2222 through the original private Service.
**SSH is not exposed by the LAN HTTP ingress.**

**Important: without the client-IP filter, the Warpgate login page is
reachable by anyone who can connect to the existing Traefik listener
with this hostname.** The LAN-only boundary must therefore be
enforced by your router/firewall and Tailscale ACLs: confirm Traefik is
not reachable from the WAN, including any port forward, public proxy,
Funnel, or external tunnel. This was not verified live. Do not load
production SSH credentials until it is verified.

LAN DNS in `salt-setup/dns-server/dns-server.conf` maps
`*.app.sierraalpha.co.nz` to `192.168.1.250` (rasomniac), the same
path used by Homepage. On a LAN client, check both names resolve to the
same ingress address and compare their HTTPS responses:

```sh
getent ahostsv4 homepage.app.sierraalpha.co.nz
getent ahostsv4 warpgate.app.sierraalpha.co.nz
curl -I https://homepage.app.sierraalpha.co.nz
curl -I https://warpgate.app.sierraalpha.co.nz
```

If you still see a **default nginx page**, first check that both requests
resolve to the same address and that ArgoCD synced the new Kubernetes
Ingress: `kubectl -n warpgate get ingress warpgate`.
A 403 after removing the ingress client-IP middleware can be issued
by Warpgate itself or another ingress policy; inspect the response
headers and Traefik logs to identify the rejecting component. A 502
may indicate backend HTTPS/SNI issues or NetworkPolicy endpoint labels;
inspect Traefik and Warpgate logs. Do not disable TLS verification.

The old `warpgate-lan` **IngressRoute** is retained with a deliberately
different `.invalid` hostname; ArgoCD's automated `prune: false` would
otherwise leave its previous live host route in the cluster, conflicting
with the new Ingress. The inert legacy object can be deleted manually
after verifying the replacement is healthy; don't enable broad automatic
pruning because the Warpgate PVC is intended to survive.

**WAN security:** this shares Homepage's existing Traefik listener.
The ingress is not equivalent to a router firewall; confirm there are no
WAN forwards, and preserve client source addresses so the allowlist cannot
be bypassed by source NAT. Use an off-LAN client *without Tailscale* to
verify Warpgate is not publicly reachable before provisioning high-value
SSH credentials.

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
