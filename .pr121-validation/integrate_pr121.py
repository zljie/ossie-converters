#!/usr/bin/env python3
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Prepare a narrowly scoped, local-only merge for OSSIE converters PR #121.

Never pushes, changes a remote ref, installs dependencies, or edits workflows.
Unexpected conflicts or source shapes cause a hard failure, not an ours/theirs
fallback. Run the complete dbt suite before publishing the resulting tree.
"""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import subprocess

ORIGINAL = "336c709e474b413baec6a25f3ec2022fa402eeae"
UPSTREAM = "532585180b0bfdb8f29b1c3035719a31785c1883"
SOURCE = "dbt/src/ossie_dbt/ossie_to_msi.py"
TEST = "dbt/tests/test_ossie_to_msi.py"
NEW_TEST = "dbt/tests/test_ratio_helpers_meta_integration.py"
IMPORT = "from ossie_dbt.ratio_helpers import mark_ratio_helpers\n"
IMPORT_ANCHOR = "from ossie_dbt.converter_issues import ConverterIssue, ConverterIssueType, ConverterResult\n"
OLD = """                metrics.extend(
                    self._convert_metric(
                        metric.name,
                        dialect_expr.expression,
                        metric.description,
                        ossie_sm.datasets,
                        dialect,
                        taken_names=reserved_names,
                        config=config,
                    )
                )
"""
NEW = """                converted = self._convert_metric(
                    metric.name,
                    dialect_expr.expression,
                    metric.description,
                    ossie_sm.datasets,
                    dialect,
                    taken_names=reserved_names,
                    config=config,
                )
                # Sign after restoring user metadata; never replace that metadata.
                mark_ratio_helpers(converted)
                metrics.extend(converted)
"""
DOC_OLD = """        sub-metrics for its numerator and denominator. Their names are added to
        `taken_names`, which holds every metric name already in use.
"""
DOC_NEW = """        sub-metrics for its numerator and denominator. Helpers remain public,
        while the owning ratio carries provenance alongside its restored metadata.
        Their names are added to `taken_names`, which holds every name already in use.
"""
TEST_OLD = '        assert ratio.config.meta == {"group_label": "ARPU"}\n'
TEST_NEW = '''        assert ratio.config.meta["group_label"] == "ARPU"
        assert set(ratio.config.meta) == {"group_label", "ossie"}
        assert set(ratio.config.meta["ossie"]) == {"generated_ratio_helpers"}
        provenance = ratio.config.meta["ossie"]["generated_ratio_helpers"]
        assert provenance["version"] == 1
        assert provenance["names"] == ["arpu_numerator", "arpu_denominator"]
'''

def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact match, found {count}")
    return text.replace(old, new, 1)

def integrate_source(upstream_source: str) -> str:
    if IMPORT in upstream_source:
        raise RuntimeError("Upstream already contains ratio provenance; re-review required")
    text = once(upstream_source, IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, "import")
    text = once(text, OLD, NEW, "conversion block")
    text = once(text, DOC_OLD, DOC_NEW, "public helper documentation")
    ast.parse(text)
    return text

def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], text=True,
                          capture_output=True, check=check)

def prepare(repo: Path, regression_file: Path, evidence: Path) -> None:
    if git(repo, "rev-parse", "HEAD").stdout.strip() != ORIGINAL:
        raise RuntimeError("HEAD changed: refusing to integrate a different original revision")
    if git(repo, "status", "--porcelain").stdout:
        raise RuntimeError("A clean checkout is required")
    git(repo, "cat-file", "-e", UPSTREAM + "^{commit}")
    result = git(repo, "merge", "--no-commit", "--no-ff", UPSTREAM, check=False)
    conflicts = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
    if result.returncode not in (0, 1) or (result.returncode == 1 and not conflicts):
        raise RuntimeError(result.stdout + result.stderr)
    unexpected = set(conflicts) - {SOURCE}
    if unexpected:
        raise RuntimeError(f"Unreviewed conflicts: {sorted(unexpected)}; stop for inspection")
    upstream_source = git(repo, "show", f"{UPSTREAM}:{SOURCE}").stdout
    (repo / SOURCE).write_text(integrate_source(upstream_source), encoding="utf-8")
    tests = (repo / TEST).read_text(encoding="utf-8")
    tests = once(tests, TEST_OLD, TEST_NEW, "upstream metadata invariant")
    ast.parse(tests)
    (repo / TEST).write_text(tests, encoding="utf-8")
    additions = regression_file.read_text(encoding="utf-8")
    ast.parse(additions)
    if (repo / NEW_TEST).exists():
        raise RuntimeError("Integration test path already exists")
    (repo / NEW_TEST).write_text(additions, encoding="utf-8")
    git(repo, "add", SOURCE, TEST, NEW_TEST)
    if git(repo, "diff", "--name-only", "--diff-filter=U").stdout:
        raise RuntimeError("Unresolved conflicts remain")
    git(repo, "diff", "--cached", "--check")
    changed = git(repo, "diff", "--cached", "--name-only", UPSTREAM).stdout.splitlines()
    if not changed or any(not p.startswith("dbt/") for p in changed):
        raise RuntimeError(f"Unexpected scope relative to upstream: {changed}")
    if git(repo, "ls-files", "--stage", "ossie").stdout.split()[1] != git(repo, "ls-tree", UPSTREAM, "ossie").stdout.split()[2]:
        raise RuntimeError("Unexpected submodule pin change")
    tree = git(repo, "write-tree").stdout.strip()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({"original": ORIGINAL, "upstream": UPSTREAM,
        "conflicted_files": conflicts, "tree": tree, "changed_files": changed,
        "tests_executed": False, "remote_branch_updated": False}, indent=2) + "\n")
    print(result.stdout, end="")
    print(f"Prepared tree {tree}; tests must pass before any push")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--regression-file", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.repo.resolve(), args.regression_file.resolve(), args.evidence.resolve())
