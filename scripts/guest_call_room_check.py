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
from typing import Any

from scripts.apply import load_env_map

JOINABLE_RULES = {"public", "knock"}
GUEST_CALL_HINTS = {
    "public": "OK — Element Call will attempt a direct join.",
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
    "(missing)": (
        "Not joinable for guests — Element Call treats a summary without join_rule as private. "
        "Guest Tuwunel often omits join_rule when federating; re-run apply.sh so Caddy proxies "
        "room-summary requests to the main homeserver, then recreate the caddy container."
    ),
}


def resolve_project_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    return Path(__file__).resolve().parent.parent


def normalize_summary_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Return flat summary fields and note if the response used a nested wrapper."""
    if "summary" in payload and isinstance(payload["summary"], dict):
        note = "response nests fields under 'summary' (Element Call reads top-level join_rule)"
        merged = dict(payload["summary"])
        if payload.get("membership") is not None and "membership" not in merged:
            merged["membership"] = payload["membership"]
        return merged, note
    return payload, None


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise RuntimeError(f"{url} returned non-object JSON")
    return data


def fetch_room_summary_candidates(
    host: str,
    room_id: str,
    *,
    via_server: str | None = None,
    label: str,
) -> list[dict[str, Any]]:
    encoded_room = urllib.parse.quote(room_id, safe="")
    via_query = f"?via={urllib.parse.quote(via_server, safe='')}" if via_server else ""
    candidates = [
        (
            f"https://{host}/_matrix/client/unstable/im.nheko.summary/summary/{encoded_room}{via_query}",
            "unstable /summary (Element Call tries this first)",
        ),
        (
            "https://"
            f"{host}/_matrix/client/unstable/im.nheko.summary/rooms/{encoded_room}/summary{via_query}",
            "unstable /rooms/.../summary (js-sdk fallback)",
        ),
        (
            f"https://{host}/_matrix/client/v1/room_summary/{encoded_room}{via_query}",
            "stable v1 room_summary",
        ),
    ]
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for url, api_kind in candidates:
        try:
            payload = fetch_json(url)
            summary, wrapper_note = normalize_summary_payload(payload)
            results.append(
                {
                    "label": label,
                    "host": host,
                    "url": url,
                    "api_kind": api_kind,
                    "payload": payload,
                    "summary": summary,
                    "wrapper_note": wrapper_note,
                }
            )
            return results
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{url} -> HTTP {exc.code}: {detail[:300]}")
        except Exception as exc:
            errors.append(f"{url} -> {exc}")
    if errors:
        raise RuntimeError("\n".join(errors))
    raise RuntimeError(f"No summary endpoints attempted for {label}")


def element_call_verdict(summary: dict[str, Any]) -> tuple[str, str, int]:
    join_rule = summary.get("join_rule")
    if join_rule is None or join_rule == "":
        rule_key = "(missing)"
    else:
        rule_key = join_rule if isinstance(join_rule, str) else str(join_rule)

    if rule_key in JOINABLE_RULES:
        return rule_key, GUEST_CALL_HINTS[rule_key], 0
    hint = GUEST_CALL_HINTS.get(
        rule_key,
        f"Not joinable for guests — join_rule '{rule_key}' is not public or knock.",
    )
    return rule_key, hint, 2


def print_probe(probe: dict[str, Any]) -> tuple[str, int]:
    summary = probe["summary"]
    join_rule, hint, code = element_call_verdict(summary)

    print(f"[{probe['label']}] {probe['api_kind']}")
    print(f"Fetched: {probe['url']}")
    if probe.get("wrapper_note"):
        print(f"Note: {probe['wrapper_note']}")
    print(json.dumps(probe["payload"], indent=2, sort_keys=True))
    print()
    print(f"join_rule (Element Call sees): {join_rule}")
    for key in ("guest_can_join", "world_readable", "membership"):
        if key in summary:
            print(f"{key}: {summary[key]}")
    print(f"Element Call: {hint}")
    print()
    return join_rule, code


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
    parser.add_argument(
        "--guest-server",
        default=None,
        help="Guest homeserver name (default: GUEST_SERVER_NAME from .env)",
    )
    args = parser.parse_args(argv)

    root = resolve_project_root(args.project_root)
    env = load_env_map(root / ".env")
    matrix_domain = (args.matrix_domain or env.get("MATRIX_DOMAIN", "")).strip()
    guest_server = (args.guest_server or env.get("GUEST_SERVER_NAME", "")).strip()
    server_name = env.get("SERVER_NAME", "").strip()
    if not matrix_domain:
        print("Missing MATRIX_DOMAIN in .env or --matrix-domain.", file=sys.stderr)
        return 1
    if not guest_server:
        print("Missing GUEST_SERVER_NAME in .env or --guest-server.", file=sys.stderr)
        return 1

    room_id = args.room_id.strip()
    if not room_id.startswith("!") or ":" not in room_id:
        print("room_id must look like !abc:example.com", file=sys.stderr)
        return 1

    via_server = server_name or matrix_domain
    print(
        "Element Call registers guests on the guest homeserver, then calls getRoomSummary() "
        "against that server (unstable MSC3266 path, with via=). The main-server summary alone "
        "is not what the browser uses.\n"
    )

    exit_code = 0
    probes: list[dict[str, Any]] = []

    try:
        probes.append(
            fetch_room_summary_candidates(
                matrix_domain,
                room_id,
                label="main homeserver",
            )[0]
        )
    except RuntimeError as exc:
        print(f"[main homeserver] FAILED\n{exc}\n", file=sys.stderr)
        exit_code = 1

    try:
        probes.append(
            fetch_room_summary_candidates(
                guest_server,
                room_id,
                via_server=via_server,
                label="guest homeserver (Element Call path)",
            )[0]
        )
    except RuntimeError as exc:
        print(f"[guest homeserver (Element Call path)] FAILED\n{exc}\n", file=sys.stderr)
        exit_code = max(exit_code, 1)

    guest_rule: str | None = None
    main_rule: str | None = None
    for probe in probes:
        rule, code = print_probe(probe)
        exit_code = max(exit_code, code)
        if probe["label"] == "main homeserver":
            main_rule = rule
        else:
            guest_rule = rule

    if main_rule == "public" and guest_rule and guest_rule not in JOINABLE_RULES:
        print(
            "Mismatch: main homeserver reports a joinable room, but the guest summary is what "
            "Element Call uses. If join_rule is missing, run apply.sh and recreate Caddy "
            "(see README guest-call troubleshooting). Also retry in a private browser window "
            "in case an old summary is cached."
        )
        exit_code = max(exit_code, 2)

    if main_rule == "public":
        print(
            "guest_can_join: false on the main server is normal here — it only applies to "
            "legacy anonymous Synapse guest accounts, not registered @user:guest-server MXIDs."
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
