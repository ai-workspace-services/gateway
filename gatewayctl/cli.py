from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .render import render_manifest
from .validation import ManifestError, load_yaml, validate_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gatewayctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("validate", "render"):
        command = subparsers.add_parser(name)
        command.add_argument("manifest", help="path to a public YAML manifest")
        command.add_argument(
            "--profile",
            action="append",
            default=[],
            help="optional non-sensitive profile YAML; checked for valid YAML only",
        )
        if name == "render":
            command.add_argument("--adapter", required=True, choices=["caddy", "kong", "apisix", "nginx"])
            command.add_argument("--output-dir", default=None)
    return parser


def _load_and_validate(args: argparse.Namespace) -> tuple[dict, dict]:
    manifest = load_yaml(args.manifest)
    summary = validate_manifest(manifest)
    for profile in args.profile:
        load_yaml(profile)
    return manifest, summary


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest, summary = _load_and_validate(args)
        if args.command == "validate":
            print(json.dumps({"valid": True, **summary}, ensure_ascii=False, indent=2))
            return 0

        output_dir = args.output_dir or str(Path("build") / args.adapter)
        result = render_manifest(manifest, args.adapter, output_dir)
        print(json.dumps({"valid": True, **summary, **result}, ensure_ascii=False, indent=2))
        return 0
    except (ManifestError, ValueError, OSError) as exc:
        print(f"gatewayctl: error: {exc}", file=sys.stderr)
        return 2
