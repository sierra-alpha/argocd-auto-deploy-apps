# Warpgate configuration is held in Warpgate's persistent database, not in
# Kubernetes manifests. The official provider manages the SSH target via API.
# This configuration is deliberately NOT automatically applied by Argo CD.
terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  required_providers {
    warpgate = {
      source  = "warp-tech/warpgate"
      version = "= 1.1.12"
    }
  }
}

provider "warpgate" {
  host = var.warpgate_api_url
  # WARPGATE_TOKEN is provided by the operator at runtime, never by Git.
}

variable "warpgate_api_url" {
  description = "Trusted HTTPS endpoint for the already running Warpgate API"
  type        = string
  default     = "https://warpgate.app.sierraalpha.co.nz"
}

# A restricted role is the ONLY role granted access to this test SSH target.
# No user is assigned to this role until an independently approved test
# requester has a verified SSH public-key credential in Warpgate.
resource "warpgate_role" "gatus_audit_requester" {
  name        = "gatus-audit-requester"
  description = "Limited test access to the Gatus readonly-audit SSH identity"
}

resource "warpgate_target" "gatus_audit" {
  name             = "gatus-audit"
  description      = "Initial human-approved SSH target: Gatus host audit account"
  require_approval = true

  ssh_options {
    host     = "rampidv1-2--1.sierraalpha.co.nz"
    port     = 22
    username = "readonly-audit"

    # Warpgate uses its own database-managed SSH client key. Do not import
    # the operator's personal 1Password SSH private key into the gateway.
    public_key_auth {}
  }
}

resource "warpgate_target_role" "gatus_audit_requester" {
  target_id = warpgate_target.gatus_audit.id
  role_id   = warpgate_role.gatus_audit_requester.id
}
