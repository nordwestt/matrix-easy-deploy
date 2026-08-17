#!/usr/bin/env bash
# wizard.sh — standard Easy Deploy entrypoint (wraps matrix-wizard.sh)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/matrix-wizard.sh" "$@"
