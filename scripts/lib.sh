#!/usr/bin/env bash
# scripts/lib.sh — shared utilities for matrix-easy-deploy scripts
# Source this file; do not execute it directly.

_lib_sh_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_med_project_root="$(cd "${_lib_sh_dir}/.." && pwd)"

# shellcheck source=easydeploy-lib/lib/init.sh
source "${_med_project_root}/easydeploy-lib/lib/init.sh"
# shellcheck source=scripts/lib_matrix.sh
source "${_lib_sh_dir}/lib_matrix.sh"
