#!/usr/bin/env bash
# scripts/lib_matrix.sh — Matrix Easy Deploy helpers (product-specific)

med_services_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qE '^(caddy|matrix_|mautrix-|matrix-)'
}

wait_for_mas_http() {
    local homeserver_container="${1:-matrix_synapse}"
    local max_attempts="${2:-30}"
    local sleep_secs="${3:-5}"

    info "Waiting for MAS to be ready…"
    local attempt=0
    until docker exec "$homeserver_container" python3 -c \
        'import urllib.request; urllib.request.urlopen("http://matrix-mas:8080/health", timeout=5)' \
        2>/dev/null; do
        attempt=$((attempt + 1))
        if [[ $attempt -ge $max_attempts ]]; then
            error "Timed out waiting for MAS HTTP health at http://matrix-mas:8080/health"
            return 1
        fi
        echo -ne "    attempt ${attempt}/${max_attempts}…\r"
        sleep "$sleep_secs"
    done
    echo
    success "MAS is ready."
}

load_runtime_desired_state() {
    local project_root="$1"
    local state_script="${project_root}/scripts/runtime_state.py"
    [[ -f "$state_script" ]] || return 0

    local state_exports
    if state_exports="$(python3 "$state_script" --project-root "$project_root" --emit-shell 2>/dev/null)"; then
        [[ -n "$state_exports" ]] && eval "$state_exports"
    fi
}

build_caddy_compose_args() {
    CADDY_COMPOSE_ARGS=(-f docker-compose.yml)
    if [[ -f "${1}/caddy/docker-compose.guest.yml" ]]; then
        CADDY_COMPOSE_ARGS+=(-f docker-compose.guest.yml)
    fi
}

build_core_compose_args() {
    CORE_COMPOSE_ARGS=(-f docker-compose.yml)
    if [[ -f "${1}/modules/core/docker-compose.guest.yml" ]]; then
        CORE_COMPOSE_ARGS+=(-f docker-compose.guest.yml)
    fi
}

build_core_compose_start_profiles() {
    CORE_COMPOSE_PROFILES=(--profile "${HOMESERVER_COMPOSE_PROFILE:-synapse}")
    if [[ "${INSTALL_ELEMENT:-true}" == "true" ]]; then
        CORE_COMPOSE_PROFILES+=(--profile element)
    fi
}

build_core_compose_stop_profiles() {
    CORE_COMPOSE_PROFILES=(--profile synapse --profile tuwunel)
    if [[ "${INSTALL_ELEMENT:-true}" == "true" ]]; then
        CORE_COMPOSE_PROFILES+=(--profile element)
    fi
}

build_calls_compose_args() {
    CALLS_COMPOSE_ARGS=(-f docker-compose.yml)
    if [[ -f "${1}/modules/calls/docker-compose.guest.yml" ]]; then
        CALLS_COMPOSE_ARGS+=(-f docker-compose.guest.yml)
    fi
    if [[ "${GUEST_ACCESS_ENABLED:-false}" == "true" ]]; then
        CALLS_COMPOSE_ARGS+=(--profile guest-calls)
    fi
}

ensure_guest_tuwunel_data_permissions() {
    local project_root="$1"
    local guest_data_dir="${project_root}/modules/calls/guest/tuwunel_data"

    mkdir -p "$guest_data_dir"
    chmod -R a+rwX "$guest_data_dir" 2>/dev/null || true
}

ensure_homeserver_data_permissions() {
    local project_root="$1"
    local implementation="synapse"

    if [[ -f "${project_root}/.env" ]]; then
        implementation="$(sed -n 's/^SERVER_IMPLEMENTATION=//p' "${project_root}/.env" | head -n1)"
        implementation="${implementation:-synapse}"
    fi

    case "${implementation,,}" in
        tuwunel)
            ensure_tuwunel_data_permissions "$project_root"
            ;;
        *)
            ensure_synapse_data_permissions "$project_root"
            ;;
    esac

    if [[ "${GUEST_ACCESS_ENABLED:-false}" == "true" ]]; then
        ensure_guest_tuwunel_data_permissions "$project_root"
    fi
}

ensure_tuwunel_data_permissions() {
    local project_root="$1"
    local tuwunel_data_dir="${project_root}/modules/core/tuwunel_data"
    local appservices_dir="${tuwunel_data_dir}/appservices"

    mkdir -p "$appservices_dir"
    chmod -R a+rwX "$tuwunel_data_dir" 2>/dev/null || true
}

ensure_synapse_data_permissions() {
    local project_root="$1"
    local synapse_data_dir="${project_root}/modules/core/synapse_data"

    mkdir -p "$synapse_data_dir"

    local chown_ok="false"
    if chown -R 991:991 "$synapse_data_dir" 2>/dev/null; then
        chown_ok="true"
    fi
    find "$synapse_data_dir" -type d -exec chmod 750 {} + 2>/dev/null || true
    find "$synapse_data_dir" -type f -exec chmod 640 {} + 2>/dev/null || true

    if [[ "$chown_ok" != "true" ]] && command -v docker &>/dev/null; then
        info "Normalizing Synapse data permissions via helper container…"
        if docker run --rm \
            -v "${synapse_data_dir}:/data" \
            alpine:3 \
            sh -c "chown -R 991:991 /data && find /data -type d -exec chmod 750 {} + && find /data -type f -exec chmod 640 {} +" \
            >/dev/null 2>&1; then
            chown_ok="true"
        else
            warn "Could not normalize Synapse data ownership via helper container."
        fi
    fi

    local write_test="${synapse_data_dir}/.med-write-test"
    if ! touch "$write_test" 2>/dev/null; then
        warn "Synapse data directory is still not writable. Applying permissive fallback permissions."
        chmod -R a+rwX "$synapse_data_dir" 2>/dev/null || true
    else
        rm -f "$write_test"
    fi
}
