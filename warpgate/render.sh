#!/bin/sh
# Entirely offline. Requires Helm 3; vendored chart is checksum verified.
set -eu
cd "$(dirname "$0")"
printf '%s  %s\n' bc08603ba778d4a76fa0090186bac6759a41170225f548bf15d0c8fb160d3e8d vendor/warpgate-0.1.0.tgz | sha256sum -c - >&2
rendered=$(mktemp)
trap 'rm -f "$rendered"' EXIT HUP INT TERM
"${HELM:-helm}" template warpgate vendor/warpgate-0.1.0.tgz \
  --namespace warpgate --kube-version 1.31.0 --values values.yaml > "$rendered"
sed 's/[[:blank:]]*$//' "$rendered"
