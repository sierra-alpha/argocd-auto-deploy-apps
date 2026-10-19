# Gatus SSH target as infrastructure as code

This directory is the **desired Warpgate target configuration**, stored beside
its ArgoCD-managed Kubernetes installation. It uses the
[official Warpgate OpenTofu/Terraform provider](https://github.com/warp-tech/terraform-provider-warpgate).

**Current status: declarative module only, NO automatic apply.** ArgoCD does
not natively reconcile the external Warpgate database or OpenTofu state. Do
not assume merging this repository makes a Gatus target appear in the UI.
This module is intentionally separate from `warpgate/manifests` so the
existing production ArgoCD application stays unchanged.

## What is declared

- `gatus-audit`: `rampidv1-2--1.sierraalpha.co.nz:22`, login
  `readonly-audit`, Warpgate-managed SSH public-key authentication.
- `require_approval = true`: an administrator must authorize connections.
- `gatus-audit-requester`: narrowly scoped role with access to only that
  target. **No requester is attached to it yet.** Administrator privileges
  are not granted to the role.
- No passwords, personal SSH private keys, API tokens, host fingerprints, or
  secret values are committed.

The provider target flag needs Warpgate >= 0.29; the deployed version is 0.29.2.
The provider is pinned to 1.1.12 until explicitly upgraded and validated.

## Human-gated prerequisites before applying

1. **Warpgate token:** create a purpose-limited, expiring API token for an
   administrator who can manage targets and roles. Inject it securely as
   `WARPGATE_TOKEN`. For a future in-cluster runner, provision via a
   separately created **1Password item**, consumed as a Kubernetes Secret,
   not an inline Terraform/ArgoCD value. Do not reuse the bootstrap password.
2. **Durable remote state:** choose/configure encrypted, access-controlled
   OpenTofu remote state with locking and backup (e.g. an appropriately
   configured S3-compatible backend). Never run automated in-cluster apply
   with disposable local state. A lost state may recreate identities, delete
   resources unexpectedly, or leak sensitive material. Do not use the
   Warpgate PVC as a shared, writable state backend.
3. **Verified SSH destination:** verify where the Gatus hostname resolves
   *from the gateway pod* and Gatus's SSH host-key fingerprint against a
   trusted source. Configure Warpgate to reject unknown/mismatched host keys;
   do not silently auto-accept host keys for this target.
4. **NetworkPolicy:** `warpgate-default-deny` currently blocks ALL outgoing
   SSH. Add a minimal, verified egress rule to the actual Gatus address
   on TCP 22 (and DNS resolution only where required). Do not guess a CIDR
   or allow `0.0.0.0/0` egress.
5. **Target client identity:** obtain the **Warpgate-managed public SSH key**
   (not its private key), then authorize it on Gatus under the existing
   `readonly-audit` account using the Ansible-managed `authorized_keys`
   workflow in `sierra-alpha/salt-setup` (eventually
   `iaac-sierra-alpha`). Avoid replacing this account's other keys.
6. **Requester and approvals:** create a dedicated, non-admin test requester
   with public-key authentication, assign only the
   `gatus-audit-requester` role, set the Warpgate global **administrator
   approval cache period to none**, and verify a second SSH connection
   requires a fresh approval. The target flag alone does NOT disable caching.

### Initial operator-only plan and apply (after prerequisites)

From this directory, with OpenTofu and the required credentials configured:

```sh
tofu init
tofu validate
tofu plan -out=gatus.tfplan
# Review the plan and approve the live target/role write before applying:
tofu apply gatus.tfplan
```

Before `tofu init` for a real plan/apply, configure a durable encrypted,
locking backend; this repository intentionally doesn't specify an unverified
bucket/endpoint/credentials. No `tofu apply` has been run.

If `gatus-audit` or its role were already manually created in Warpgate,
**import** them into the chosen state instead of creating duplicates. Use
the provider's documented target/role/association import IDs.

## Recommended future ArgoCD-driven reconciliation

Once the above prerequisites are verified, create a **separate opt-in**
ArgoCD Application or approved PostSync Job (never a Warpgate init container)
that:
- mounts a pinned, reviewed OpenTofu runner;
- loads `WARPGATE_TOKEN` from an externally synchronized Kubernetes Secret;
- uses remote encrypted state with locking and retries only safe failures;
- waits for the Warpgate HTTPS API to be ready and validates its TLS certificate;
- runs against a trusted reachable endpoint (no insecure TLS bypass);
- has tightly scoped Kubernetes network permissions and an appropriate
  ServiceAccount; cannot modify unrelated cluster objects;
- is idempotent and cannot accidentally destroy gateway users/targets on
  a bad sync; real apply requires an explicit operator-approved cutover.

This avoids adding a bespoke API provisioning script or directly modifying
Warpgate's SQLite DB. **Do not let ArgoCD auto-apply the resource at this stage:**
the external state, API token, Gatus network path, host key, target public key,
and approval-cache policy are not provisioned or verified.

## Validation / completion checklist

- `tofu fmt -check`, `tofu init -backend=false` and `tofu validate`.
- The ArgoCD Warpgate app remains unchanged; no live cluster/SSH calls.
- No role grants production access to Codex until the dedicated requester and
  isolated worker boundary have been separately reviewed.
- Test approve/deny, timeout, disconnect/reconnect, and two simultaneous
  sessions. Warpgate approves *sessions*, not individual remote commands.
