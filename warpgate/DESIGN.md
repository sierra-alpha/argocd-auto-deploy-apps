# Placement, HA and phone approval design

Research snapshot: 2026-10-18 UTC. This is a proposal, not a live inventory or
permission to change hosts. Local `salt-setup` checkout at
`6ff36e42a36c71928cf403047235380474041230` was read only. No SSH, Ansible,
1Password, Kubernetes API, metrics or capacity probes were run.

## Evidence and coordination

`ansible/inventory/hosts.yml` places `rasomniac.sierraalpha.co.nz` in
`k3s_server`, with airsomniac2/prosomniac as agents. It places
`mediasomniac.sierraalpha.co.nz` in `standalone`, Docker and Tailscale groups,
with Jellyfin, Immich, Filestash, rclone/WOL and music/media roles.
`rampidv1-2--1.sierraalpha.co.nz` is the Gatus/Docker/Tailscale host and also
carries monitoring/Beszel and ntfy roles. It is not in the K3s groups.
The current inventory does **not** establish either as a second Kubernetes
cluster, nor prove physical power/network independence or actual running state.

`ansible/roles/gatus/defaults/main.yml` pins Gatus and uses port 8080; its tasks
follow `present.yml`/`absent.yml` dispatch. A future standalone Warpgate role
should follow those idempotent Ansible conventions and existing external-secret
patterns, without modifying Gatus or its ports. Inventory contains a prerequisite
for default-deny Tailscale policy, not evidence that policy has been enforced.
The gateway should use local persistent storage, not mediasomniac's media mount
or WOL-dependent storage as its online credential database.

Related control jobs remain independent; none clearly supersedes #84:

| Job | Boundary and handoff |
| --- | --- |
| [#66 Kubernetes reliability](https://github.com/sierra-alpha/ai-whisperer/pull/66) | Pending audit of probes/resources/restarts. This PR covers only Warpgate and records chart gaps; do not refactor other apps. |
| [#40 security audit](https://github.com/sierra-alpha/ai-whisperer/pull/40) | Queued assessment includes this repo read-only. Supply the fail-closed network, secret, broker and backup requirements here for review; no security rollout is implied. |
| [#78 repository rename](https://github.com/sierra-alpha/ai-whisperer/pull/78) | Queued local rename to `iaac-sierra-alpha`; use current `salt-setup` evidence and re-resolve the same repository identity before future Ansible changes. No rename in this PR. |
| [#80 Pushover](https://github.com/sierra-alpha/ai-whisperer/pull/80) | Human-gated reusable notification work. Reuse its eventual event contract/adapter; do not create a second notification daemon. |

Other same-target queue requests cover Homepage, storage monitoring, logs and
network monitoring. They are compatible separate scopes, not replacements for
this gateway PoC. No other job ownership/state was changed.

## Placement decision

Start with the disabled, single-instance K3s PoC to verify the product and native
approval semantics. If independent recovery access is needed next, prefer a
small **always-on standalone** service after measuring host capacity and failure
domains. Do not add a Kubernetes cluster merely to host a gateway.

| Option | Primary K3s outage | State and operational cost | Decision |
| --- | --- | --- | --- |
| One K3s replica, SQLite/RWO PVC | If its node/storage fails, gateway unavailable. Control-plane failure alone may leave an existing pod serving, but no dependable rescheduling/reconciliation. | Lowest effort; local-path volume can tie recovery to one node. Backups restore service, not continuous availability. | Best PoC; not an independent emergency-access path. |
| Ansible-managed container/systemd on mediasomniac | Can remain usable if independent of K3s, its storage and its routes. | Existing Docker/Tailscale footprint; substantial media/Immich load and storage dependencies. Need measured RAM/CPU/disk headroom, always-on policy and separate gateway data. | Plausible second placement; do not call it independent until power/NAS/router dependencies are mapped. |
| Ansible-managed container/systemd on Gatus host | Can remain usable if the host, tailnet and network survive. | Already carries monitoring and notifications; small-host capacity is unverified. Gateway failure/resource pressure must not blind the outage monitor. | Candidate only after RAM/architecture/disk/endurance/UPS and resource limits are checked. Preserve Gatus availability first; not automatically the preferred HA node. |
| Multiple Warpgate nodes across hosts or clusters | Can accept new sessions if a node, database quorum and client route survive outside K3s. | Shared resilient DB, encryption key distribution, peer routing, recordings, load balancing, migrations and recovery tests. Highest complexity. | Defer until an explicit availability target justifies it; separate clusters are optional. |

Multiple standalone installs with unrelated SQLite databases are **not HA**:
users, credentials, approvals, host keys and audit records diverge. A cold restore
or separately managed break-glass gateway can be useful but must be labelled as
such. Preserve the functioning 1Password native-prompt fallback; do not migrate
its keys or assume the gateway replaces its trust boundary.

## What real HA would require

Upstream clustering shares PostgreSQL/MySQL, encryption material and recording
storage; peers must reach each other on the HTTPS listener for cross-node
proxying. See [upstream clustering](https://warpgate.null.page/clustering/).
For this environment, evaluate PostgreSQL with replication/failover, fencing and
backups **outside the primary K3s failure domain**. The chart's bundled single
PostgreSQL StatefulSet is not a database HA design.

Define owner-approved RTO/RPO first. A synchronous quorum across only two machines
cannot simply promise both availability and partition safety; pick a supported
DB topology/witness or managed service and test fencing. Protect DB connections
and restrict access to gateway nodes. Coordinate schema upgrades and test the
previous backup restoration before rolling forward.

Distribute the same protected encryption key and recoverable gateway identities
to each node through external secret management. Use shared, independently
available recording storage with access controls and lifecycle rules. Avoid a
supposedly redundant DB/recording service that ultimately depends on the same
NAS, sleeping host, switch, UPS or K3s server. Budget capacity for encryption,
concurrent sessions and recordings, not just idle memory.

Use a stable private client address with health-aware routing for both SSH and
HTTPS. A single Tailscale operator/proxy inside failed K3s would negate an
external node. Evaluate independent tailnet endpoints and a supported private
failover route; plain DNS with cached records is not guaranteed failover. Peer
addresses must be reachable across hosts (pod IP discovery is insufficient
across isolated clusters). Authenticate peer traffic and open only required
ports. Enable PROXY protocol only when both the trusted balancer and corresponding
Warpgate listeners are configured for it.

A failed node's live SSH/TCP sessions should be expected to disconnect; HA should
restore **new** connections, each subject to fresh approval. Do not promise
transparent session migration. Test loss of each gateway, DB primary, recording
backend and routing component, then a full primary-K3s outage and network
partition. Confirm approval decisions cannot cross users/targets or remain
cached after failover. HA readiness depends on measured results, not replica count.

## Phone notifications and trusted worker boundary

Proposed flow (design only):

1. A trusted broker accepts a bounded AIW job/action identifier, validates the
   durable job lease, allowed target and operation against operator-controlled
   policy, and assigns an expiring request nonce and isolated worker identity.
2. That worker can reach only the gateway and approved support services. It
   cannot reach target SSH directly, the host SSH-agent/1Password socket, X11,
   VNC, desktop automation, hypervisor/container sockets, Kubernetes admin API,
   gateway database/keys, or approver browser cookies. Use a separate VM or
   similarly enforceable trust boundary; an environment-variable convention or
   an unrestricted local Codex process is insufficient.
3. The broker records the task/action, immutable target ID, gateway requester
   identity, intended target username, expiry and native pending session ID.
   Resolve ambiguity by refusing to associate/approve a session; prevent replay,
   substitution and two simultaneous sessions sharing one authorization.
   Codex's prose is explanatory data, never authority to broaden this mapping.
4. A notifier publishes a generic pending-approval event through #80's eventual
   adapter: source, severity, safe summary, dedupe key and a configured private
   Warpgate UI link. Use opaque IDs where names reveal infrastructure. No keys,
   passwords, session cookies, signed bearer links, terminal output or private
   task content in Pushover. Deduplicate, expire stale notices and bound retries.
5. The owner opens the authenticated native Warpgate UI over Tailscale, checks
   the broker's trusted context and the matching requester/target/session, then
   explicitly approves that session. **Pushover acknowledgement is never
   authorization**, and the notifier must not hold approval credentials.
   A notification outage leaves access pending/denied.
6. The broker records the decision/result without credentials and closes the
   worker route on expiry/completion. Session duration and target-side command
   restrictions remain separately enforced policies.

Optional Authentik OIDC/passkeys can strengthen named administrator sign-in.
Keep it optional for the PoC: an IdP living solely in K3s may defeat independent
recovery. Review MFA, administrator recovery and tailnet dependencies together.
Do not create a home-grown approval engine, callback that approves on a phone
notification, or broad gateway-admin token for Codex.

## Upstream integration evidence and unresolved checks

v0.29.2's [native session approval API](https://github.com/warp-tech/warpgate/blob/v0.29.2/warpgate-admin/src/api/session_approvals.rs)
provides list/approve/reject operations and a stream. Listing/decisions require
`ApproveSessions`; pending items include session ID, protocol, source address,
username and target. The source does not establish an AIW task-binding field or
an approval-list-only service permission. Do not give a notification collector
an approval-capable credential just to enumerate requests. Determine whether a
supported read-only event source exists, or accept manual UI discovery first.

The native UI is the authorization authority. No production API integration is
implemented here. Verify the deployed OpenAPI contract, authentication/CSRF,
request expiry and stable UI link shape before implementing the notifier.
A generic verified admin UI URL is safer than guessing a session deep link.

Phone ergonomics have not been tested: on an actual iPhone confirm tailnet
connectivity, TLS trust, readable target/requester details, deliberate approve
versus reject, pending expiry, concurrent requests, sign-in/MFA, and return from
Pushover without cached privilege. The upstream request model alone does not
prove the owner can see the trusted task context. Lack of trustworthy binding
or independent worker isolation blocks production Codex access even if manual
Warpgate approvals work correctly.

## Inputs needed later

No question blocks this draft. Before a supervised staging rollout the owner
must select a test host/account and allowed commands, private DNS/TLS identity,
operator tags/grants, storage/backup/recording policy and approver accounts.
Before HA, measure host resources and verify physical/network failure domains,
then choose RTO/RPO, database/recording topology and independent routing.
Before Codex integration, approve the isolated execution boundary and trusted
session-to-task mapping. All live actions remain gated separately.
