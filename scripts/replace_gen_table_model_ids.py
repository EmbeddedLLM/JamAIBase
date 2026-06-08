#!/usr/bin/env python3
"""
Submit and poll a GenTable model ID replacement task through the public API.

Examples:
  python scripts/replace_gen_table_model_ids.py one-to-one old/model new/model --yes
  python scripts/replace_gen_table_model_ids.py many-to-one old/a old/b --to new/model --yes
  python scripts/replace_gen_table_model_ids.py file mapping.json --organizations org_1,org_2 --yes
  python scripts/replace_gen_table_model_ids.py poll gen_table_model_replace:...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

from jamaibase import JamAI
from jamaibase.types import GenTableModelReplaceRequest, ProgressState


DEFAULT_API_BASE = os.getenv("JAMAI_API_BASE", "http://localhost:6969/api")
DEFAULT_TOKEN = os.getenv("JAMAI_TOKEN") or os.getenv("OWL_SERVICE_KEY") or ""
DEFAULT_USER_ID = os.getenv("JAMAI_USER_ID", "0")
DEFAULT_PROJECT_ID = os.getenv("JAMAI_PROJECT_ID", "default")


def parse_organization_ids(value: str | None) -> list[str] | None:
    if value is None:
        return None
    organization_ids = [item.strip() for item in value.split(",") if item.strip()]
    return organization_ids or None


def load_mapping_file(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        raise SystemExit(f"Cannot read mapping file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit("Mapping file must contain a JSON object like {\"old\": \"new\"}.")
    return {str(old_id): str(new_id) for old_id, new_id in data.items()}


def validate_mapping(mapping: dict[str, str]) -> None:
    if not mapping:
        raise SystemExit("Mapping is empty.")

    self_mappings = [old_id for old_id, new_id in mapping.items() if old_id == new_id]
    if self_mappings:
        raise SystemExit(
            "Model replacement cannot map an ID to itself: " + ", ".join(self_mappings)
        )


def format_request(mapping: dict[str, str], organization_ids: list[str] | None) -> str:
    return json.dumps(
        {
            "mapping": mapping,
            "organization_ids": organization_ids,
        },
        indent=2,
        sort_keys=True,
    )


def make_client(args: argparse.Namespace) -> JamAI:
    return JamAI(
        api_base=args.api_base,
        token=args.token,
        user_id=args.user_id,
        project_id=args.project_id,
    )


def print_progress(progress: dict[str, Any]) -> None:
    state = progress.get("state", "")
    error = progress.get("error")
    data = progress.get("data") or {}
    stats = data.get("stats") or {}

    parts = [f"state={state or 'UNKNOWN'}"]
    if stats:
        parts.extend(
            [
                f"orgs={stats.get('organizations_scanned', '?')}",
                f"projects={stats.get('projects_scanned', '?')}",
                f"tables={stats.get('tables_scanned', '?')}",
                f"updated_tables={stats.get('tables_updated', '?')}",
                f"failed_tables={stats.get('tables_failed', '?')}",
                f"updated_columns={stats.get('updated_columns', '?')}",
                f"failed_columns={stats.get('failed_columns', '?')}",
            ]
        )
    if error:
        parts.append(f"error={error}")
    print("  ".join(parts), flush=True)


def poll_progress(
    client: JamAI,
    progress_key: str,
    *,
    initial_wait: float,
    max_wait: float,
) -> dict[str, Any]:
    index = 1
    started_at = perf_counter()
    last_state_line = ""

    while (perf_counter() - started_at) < max_wait:
        sleep(min(initial_wait * index, 5.0))
        progress = client.tasks.get_progress(progress_key)
        state_line = json.dumps(progress.get("data", {}).get("stats", {}), sort_keys=True)
        state = progress.get("state")

        if state_line != last_state_line or state in {ProgressState.COMPLETED, ProgressState.FAILED}:
            print_progress(progress)
            last_state_line = state_line

        if state == ProgressState.COMPLETED:
            return progress
        if state == ProgressState.FAILED:
            raise SystemExit(progress.get("error") or "Replacement task failed.")
        index += 1

    raise SystemExit(f"Timed out waiting for progress key {progress_key!r}.")


def confirm_submission(args: argparse.Namespace, mapping: dict[str, str]) -> None:
    organization_ids = parse_organization_ids(args.organizations)
    print("Replacement request:")
    print(format_request(mapping, organization_ids))
    print()
    print(f"API base: {args.api_base}")
    print(f"User ID: {args.user_id}")
    print()

    if args.print_request:
        raise SystemExit(0)

    if args.dry_run:
        print(
            "This endpoint does not support server-side dry-run. "
            "The request above was not submitted."
        )
        raise SystemExit(0)

    if args.yes:
        return

    answer = input("Submit this replacement task? Type 'replace' to continue: ").strip()
    if answer != "replace":
        raise SystemExit("Aborted.")


def submit_and_poll(args: argparse.Namespace, mapping: dict[str, str]) -> None:
    validate_mapping(mapping)
    organization_ids = parse_organization_ids(args.organizations)
    confirm_submission(args, mapping)

    client = make_client(args)
    response = client.models.replace_model_ids(
        GenTableModelReplaceRequest(
            mapping=mapping,
            organization_ids=organization_ids,
        )
    )
    print(f"Progress key: {response.progress_key}", flush=True)

    if args.no_poll:
        return

    progress = poll_progress(
        client,
        response.progress_key,
        initial_wait=args.initial_wait,
        max_wait=args.max_wait,
    )
    print("Final progress:")
    print(json.dumps(progress, indent=2, sort_keys=True))


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="JamAI API base URL.")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Bearer token or service key.")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="User ID to send as X-USER-ID.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="Project ID header.")
    parser.add_argument(
        "--organizations",
        "-o",
        help="Comma-separated organization IDs to scan. If omitted, all organizations are scanned.",
    )
    parser.add_argument("--initial-wait", type=float, default=0.5, help="Initial poll wait seconds.")
    parser.add_argument("--max-wait", type=float, default=30 * 60.0, help="Max poll wait seconds.")
    parser.add_argument("--no-poll", action="store_true", help="Submit the task and exit.")
    parser.add_argument("--yes", "-y", action="store_true", help="Submit without confirmation.")
    parser.add_argument(
        "--print-request",
        action="store_true",
        help="Print the API request payload and exit without submitting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for printing the request and refusing submission; the endpoint has no dry-run.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replace GenTable model IDs through /v2/models/replace and poll progress."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    one_to_one = subparsers.add_parser("one-to-one", help="Replace one model ID with another.")
    add_common_options(one_to_one)
    one_to_one.add_argument("old_model_id")
    one_to_one.add_argument("new_model_id")

    many_to_one = subparsers.add_parser("many-to-one", help="Replace many model IDs with one ID.")
    add_common_options(many_to_one)
    many_to_one.add_argument("old_model_ids", nargs="+")
    many_to_one.add_argument("--to", "-t", required=True, dest="new_model_id")

    file_parser = subparsers.add_parser("file", help="Read {old_id: new_id} mapping from JSON.")
    add_common_options(file_parser)
    file_parser.add_argument("mapping_file", type=Path)

    poll_parser = subparsers.add_parser("poll", help="Poll an existing replacement progress key.")
    poll_parser.add_argument("progress_key")
    poll_parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="JamAI API base URL.")
    poll_parser.add_argument("--token", default=DEFAULT_TOKEN, help="Bearer token or service key.")
    poll_parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="User ID for X-USER-ID.")
    poll_parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="Project ID header.")
    poll_parser.add_argument(
        "--initial-wait", type=float, default=0.5, help="Initial poll wait seconds."
    )
    poll_parser.add_argument("--max-wait", type=float, default=30 * 60.0, help="Max poll wait.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "one-to-one":
        mapping = {args.old_model_id: args.new_model_id}
        submit_and_poll(args, mapping)
    elif args.command == "many-to-one":
        mapping = {old_model_id: args.new_model_id for old_model_id in args.old_model_ids}
        submit_and_poll(args, mapping)
    elif args.command == "file":
        mapping = load_mapping_file(args.mapping_file)
        submit_and_poll(args, mapping)
    elif args.command == "poll":
        client = make_client(args)
        progress = poll_progress(
            client,
            args.progress_key,
            initial_wait=args.initial_wait,
            max_wait=args.max_wait,
        )
        print("Final progress:")
        print(json.dumps(progress, indent=2, sort_keys=True))
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
