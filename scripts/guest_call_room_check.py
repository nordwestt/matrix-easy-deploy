#!/usr/bin/env python3
"""Check whether a room is joinable via Element Call guest links."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.apply import load_env_map

JOINABLE_RULES = {"public", "knock"}
GUEST_CALL_HINTS = {
    "public": "OK — Element Call will join directly.",
    "knock": "OK — Element Call shows Ask to join (requires feature_ask_to_join in Element Web).",
    "invite": (
        "Not joinable for guests — room is invite-only. In Element: Room settings → "
        "Access → set join rule to Public or Ask to join."
    ),
    "restricted": (
        "Not joinable for guests — room uses restricted join (often via a Space). "
        "Use a call room with join rule Public or Ask to join."
    ),
    "knock_restricted": (
        "Not joinable for guests — knock_restricted is not supported by Element Call v0.21. "
        "Use Public or plain Ask to join (knock)."
    ),
    "private": "Not joinable for guests — room join rule is private.",
}


def resolve_project_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    return Path(__file__).resolve().parent.parent


def fetch_room_summary(matrix_domain: str, room_id: str) -> tuple[dict, str]:
    encoded_room = urllib.parse.quote(room_id, safe="")
    candidates = [
        f"https://{matrix_domain}/_matrix/client/v1/room_summary/{encoded_room}",
        (
            "https://"
            f"{matrix_domain}/_matrix/client/unstable/im.nheko.summary/rooms/{encoded_room}/summary"
        ),
    ]
    errors: list[str] = []
    for url in candidates:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read().decode("utf-8")
            return json.loads(body), url
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{url} -> HTTP {exc.code}: {detail[:300]}")
        except Exception as exc:
            errors.append(f"{url} -> {exc}")
    raise RuntimeError("Could not fetch room summary:\n" + "\n".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Element Call guest joinability for a Matrix room (MSC3266 summary)."
    )
    parser.add_argument("room_id", help="Matrix room ID, e.g. !abc:matrix.example.com")
    parser.add_argument(
        "--project-root",
        default=None,
        help="matrix-easy-deploy root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--matrix-domain",
        default=None,
        help="Main client API host (default: MATRIX_DOMAIN from .env)",
    )
    args = parser.parse_args(argv)

    root = resolve_project_root(args.project_root)
    env = load_env_map(root / ".env")
    matrix_domain = (args.matrix_domain or env.get("MATRIX_DOMAIN", "")).strip()
    if not matrix_domain:
        print("Missing MATRIX_DOMAIN in .env or --matrix-domain.", file=sys.stderr)
        return 1

    room_id = args.room_id.strip()
    if not room_id.startswith("!") or ":" not in room_id:
        print("room_id must look like !abc:example.com", file=sys.stderr)
        return 1

    try:
        summary, url = fetch_room_summary(matrix_domain, room_id)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    join_rule = summary.get("join_rule") or "(missing — Synapse treats as public)"
    rule_key = join_rule if isinstance(join_rule, str) else str(join_rule)
    guest_can_join = summary.get("guest_can_join")
    world_readable = summary.get("world_readable")

    print(f"Fetched: {url}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print()
    print(f"join_rule: {join_rule}")
    if guest_can_join is not None:
        print(f"guest_can_join: {guest_can_join}")
    if world_readable is not None:
        print(f"world_readable: {world_readable}")

    if rule_key in ("(missing — Synapse treats as public)",) or rule_key in JOINABLE_RULES:
        hint = GUEST_CALL_HINTS.get(rule_key, "OK — Element Call will join directly.")
        print(f"\nElement Call: {hint}")
        return 0

    hint = GUEST_CALL_HINTS.get(
        rule_key,
        f"Not joinable for guests — join_rule '{rule_key}' is not public or knock.",
    )
    print(f"\nElement Call: {hint}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
