# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Prepare randomly labelled output directories for a blind comparison."""
import argparse
import json
import os
import random
import secrets
import shutil
import sys
from pathlib import Path
from aggregate_benchmark import atomic_write


def validate_output_links(source):
    if source.is_symlink():
        raise ValueError(f"Outputs directory must not be a symlink: {source}")
    root = source.resolve()
    # Never descend into linked directories, including links that form cycles.
    for directory, directories, files in os.walk(source, followlinks=False):
        for name in directories + files:
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            try:
                target = path.resolve()
            except RuntimeError as exc:
                raise ValueError(f"Cyclic output symlink: {path}") from exc
            if not target.is_relative_to(root):
                raise ValueError(f"Output symlink points outside its outputs directory: {path}")


def skip_output_links(directory, names):
    skipped = []
    for name in names:
        path = Path(directory) / name
        if path.is_symlink():
            print(f"Note: skipping output symlink: {path}", file=sys.stderr)
            skipped.append(name)
    return skipped



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iteration", type=Path)
    parser.add_argument("--eval", required=True)
    parser.add_argument("--a", default="with_skill")
    parser.add_argument("--b", default="without_skill")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    try:
        for name in (args.eval, args.a, args.b):
            if not name or Path(name).name != name or name in {".", ".."}:
                raise ValueError("Eval and configuration names must be single path components")
        if args.run < 1 or args.a == args.b:
            raise ValueError("Run must be positive and configurations must differ")
        root = args.iteration.resolve()
        configs = [args.a, args.b]
        sources = {c: root / args.eval / c / f"run-{args.run}" / "outputs" for c in configs}
        for source in sources.values():
            validate_output_links(source)
            if not source.is_dir():
                raise ValueError(f"Missing outputs: {source}")
        destination = root / "blind" / args.eval
        if destination.exists():
            raise ValueError(f"Refusing to overwrite existing blind comparison: {destination}")
        seed = args.seed if args.seed is not None else secrets.randbits(64)
        random.Random(seed).shuffle(configs)
        destination.mkdir(parents=True)
        try:
            for label, config in zip(("A", "B"), configs):
                shutil.copytree(
                    sources[config],
                    destination / label,
                    symlinks=True,
                    ignore=skip_output_links,
                )
            key = destination.parent / f"{args.eval}.key.json"
            atomic_write(key, json.dumps(dict(A=configs[0], B=configs[1], seed=seed), indent=2) + "\n")
        except Exception:
            shutil.rmtree(destination)
            raise
        print(destination / "A")
        print(destination / "B")
        print(key)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
