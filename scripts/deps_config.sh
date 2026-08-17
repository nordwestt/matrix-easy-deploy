#!/usr/bin/env bash
# scripts/deps_config.sh — extra keys on top of easydeploy-lib defaults
# (docker, compose, openssl, curl, python3, borg, borgmatic, age).

easydeploy_required_deps() {
    printf '%s\n' docker docker-compose openssl curl python3 borg borgmatic age
}
