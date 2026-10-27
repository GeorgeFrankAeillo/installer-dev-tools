#!/usr/bin/env python3
"""Prepare a chart-generator config with temporary component source overrides.

The MCH generator accepts --config but not --component-branch/--component-fork.
Keep the configured release branch for chart transforms while using a local Git
mirror to supply the commit from a component's development branch.
"""

import argparse
import subprocess
from pathlib import Path

import yaml


def parse_overrides(value, flag):
    overrides = {}
    for item in value.split():
        name, separator, target = item.partition(":")
        if not separator or not name or not target:
            raise ValueError(f"Invalid {flag} value {item!r}; expected component:target")
        overrides[name] = target
    return overrides


def run_git(*args):
    command = ["git", *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mirror-dir", required=True, type=Path)
    parser.add_argument("--component-branches", default="")
    parser.add_argument("--component-forks", default="")
    args = parser.parse_args()

    branches = parse_overrides(args.component_branches, "--component-branches")
    forks = parse_overrides(args.component_forks, "--component-forks")
    config = yaml.safe_load(args.config.read_text())
    components = config.get("components", [])

    args.mirror_dir.mkdir(parents=True, exist_ok=True)
    for index, component in enumerate(components):
        name = component.get("repo_name")
        source = forks.get(name, component.get("github_ref"))
        branch = branches.get(name)

        if name in forks:
            component["github_ref"] = source
        if branch is None:
            continue
        if not source or not component.get("branch"):
            raise ValueError(f"{name}: branch override requires github_ref and branch")

        configured_branch = component["branch"]
        if branch == configured_branch:
            continue

        mirror = args.mirror_dir / f"{args.output.stem}-{index}.git"
        run_git("clone", "--bare", "--single-branch", "--depth", "1", "--branch", branch, source, mirror)
        commit = run_git("-C", mirror, "rev-parse", "HEAD")
        run_git("-C", mirror, "update-ref", f"refs/heads/{configured_branch}", commit)
        component["github_ref"] = str(mirror)
        print(f"{name}: using {branch} as {configured_branch} for chart generation", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(config, sort_keys=False))


if __name__ == "__main__":
    main()
