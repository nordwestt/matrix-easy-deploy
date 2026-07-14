#!/usr/bin/env python3
"""Generate Element Call guest meeting links for external participants."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.apply import build_guest_call_share_url, load_env_map


def resolve_project_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an Element Call guest link for a Matrix room (Google Meet style)."
    )
    parser.add_argument("room_id", help="Matrix room ID, e.g. !AdAczRpx:matrix.example.com")
    parser.add_argument(
        "--project-root",
        default=None,
        help="matrix-easy-deploy root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--call-domain",
        default=None,
        help="Element Call domain (default: GUEST_CALL_DOMAIN from .env)",
    )
    parser.add_argument(
        "--server-name",
        default=None,
        help="Main Matrix server name for viaServers (default: SERVER_NAME from .env)",
    )
    parser.add_argument(
        "--intent",
        default="join_existing",
        help="Element Call intent query param (default: join_existing)",
    )
    args = parser.parse_args(argv)

    root = resolve_project_root(args.project_root)
    env = load_env_map(root / ".env")

    call_domain = (args.call_domain or env.get("GUEST_CALL_DOMAIN", "")).strip()
    server_name = (args.server_name or env.get("SERVER_NAME", "")).strip()

    if env.get("GUEST_ACCESS_ENABLED", "false").strip().lower() != "true":
        print(
            "Warning: GUEST_ACCESS_ENABLED is not true in .env — link may not work for anonymous guests.",
            file=sys.stderr,
        )
    if not call_domain:
        print("Missing Element Call domain. Set GUEST_CALL_DOMAIN in .env or pass --call-domain.", file=sys.stderr)
        return 1
    if not server_name:
        print("Missing server name. Set SERVER_NAME in .env or pass --server-name.", file=sys.stderr)
        return 1

    try:
        url = build_guest_call_share_url(
            call_domain,
            args.room_id,
            server_name,
            intent=args.intent,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
