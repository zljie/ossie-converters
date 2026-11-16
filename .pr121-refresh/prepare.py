# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
"""Prepare a pinned, minimal PR121 merge in a disposable Actions checkout.

Only creates a LOCAL merge commit. It never pushes, changes PRs or approves CI.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ORIGINAL = "b01e15f5f737c340df6b4ea05b15b708fed67f64"
UPSTREAM = "6cc4392bb82f03511944e33af987f37025c25f64"
BRANCH = "fix/dbt-ratio-private-helpers-20261102"
EXPECTED = {
    "dbt/README.md": "f97b2af75549677dc033fbd2eeee2b75d5297334bed7e62b774f60982d16981d",
    "dbt/src/ossie_dbt/msi_to_ossie.py": "c2fae25433f7f2dbd8177880bb214fe3d7afea964bc6e0c86a8f54f956e797ba",
    "dbt/src/ossie_dbt/ossie_to_msi.py": "a5fa52eb92683b3d985c06da997ce7efa052ac3d57e3f4b576ea3f283c49e550",
    "dbt/src/ossie_dbt/ratio_helpers.py": "5491977435567ca2f1e67bf29aed087a150e0a7fd9eac6020a3859b7322ccbd3",
    "dbt/tests/test_msi_to_ossie.py": "e4213ead5dfa60c859d6c4bd6d40e8c54d6203b43ff25d78bedd6235532838de",
    "dbt/tests/test_ossie_to_msi.py": "6b40447300678db25f6193321520f6d083fde64f6ae830e6c875a58adb21cab5",
    "dbt/tests/test_ratio_helpers.py": "6277b7801cc91940f9f6b8d0cafd46d39a09a57ee1c124358ed4016f5e9457da",
    "dbt/tests/test_ratio_helpers_cli.py": "f296e59381131030e9251a3a5fd4fce46ff92433001039880e109713ba78ae71",
    "dbt/tests/test_ratio_helpers_meta_integration.py": "80e78633775e1c23c6d6957e9a9bc5a10c3b9192a74a130cae69f885d76eaaa6",
}


def git(*args: str, check: bool = True, env=None):
    result = subprocess.run(["git", *args], text=True, capture_output=True, env=env)
    print("+ git", *args, flush=True)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.returncode}")
    return result


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one occurrence of {old!r}")
    return text.replace(old, new, 1)


def remote_tip(url: str, branch: str) -> str:
    lines = git("ls-remote", "--exit-code", url, f"refs/heads/{branch}").stdout.splitlines()
    if len(lines) != 1:
        raise RuntimeError("Ambiguous remote branch")
    return lines[0].split()[0]


def check_pins() -> None:
    for url, branch, expected in (
        ("https://github.com/zljie/ossie-converters.git", BRANCH, ORIGINAL),
        ("https://github.com/apache/ossie-converters.git", "main", UPSTREAM),
    ):
        if remote_tip(url, branch) != expected:
            raise RuntimeError(f"Remote tip moved: {url} {branch}; stop without publication")


def main() -> None:
    evidence = Path(sys.argv[1]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    check_pins()
    git("diff", "--exit-code")
    git("diff", "--cached", "--exit-code")
    git("checkout", "--detach", ORIGINAL)
    merge = git("merge", "--no-ff", "--no-commit", UPSTREAM, check=False)
    conflicts = git("diff", "--name-only", "--diff-filter=U").stdout.splitlines()
    (evidence / "merge.log").write_text(merge.stdout + merge.stderr)
    if merge.returncode != 1 or conflicts != ["dbt/README.md"]:
        raise RuntimeError(f"Unexpected merge/conflicts: {merge.returncode}, {conflicts}")
    if git("rev-parse", "MERGE_HEAD").stdout.strip() != UPSTREAM:
        raise RuntimeError("Unexpected merge parent")
    readme = Path("dbt/README.md")
    text = readme.read_text()
    pattern = r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n"
    def resolve(match):
        ours, theirs = match.group(1), match.group(2)
        if "Generated helpers remain public" not in ours or "NULLIF(expr_b, 0)" not in theirs:
            raise RuntimeError("README conflict does not match the reviewed overlap")
        return replace_once(ours, "`(expr_a) / (expr_b)` → RATIO", "`(expr_a) / (expr_b)` or `(expr_a) / NULLIF(expr_b, 0)` → RATIO")
    text, count = re.subn(pattern, resolve, text, flags=re.M | re.S)
    if count != 1:
        raise RuntimeError("Expected exactly one README conflict")
    readme.write_text(text)
    test = Path("dbt/tests/test_ratio_helpers_cli.py")
    text = test.read_text()
    text = replace_once(text,
        '    "(SUM(orders.amount) / COUNT(*)) / SUM(orders.amount)",\n]',
        '    "(SUM(orders.amount) / COUNT(*)) / SUM(orders.amount)",\n'
        '    "SUM(orders.amount) / NULLIF(COUNT(orders.order_id), 0)",\n'
        '    "SUM(orders.amount) / NULLIF(COUNT(DISTINCT orders.order_id), 0)",\n'
        '    "SUM(orders.amount) / NULLIF(COUNT(*), 0)",\n'
        '    "SUM(orders.amount) / NULLIF(SUM(orders.amount), 0)",\n'
        '    "(SUM(orders.amount) / NULLIF(COUNT(orders.order_id), 0)) / NULLIF(SUM(orders.amount), 0)",\n]')
    text = replace_once(text,
        'IDS = ["count_column", "count_distinct", "count_star", "nested_count", "count_one", "qualified_star", "nested_distinct", "nested_star"]',
        'IDS = [\n'
        '    "count_column", "count_distinct", "count_star", "nested_count",\n'
        '    "count_one", "qualified_star", "nested_distinct", "nested_star",\n'
        '    "nullif_count_column", "nullif_count_distinct", "nullif_count_star",\n'
        '    "nullif_sum", "nested_nullif_count",\n]')
    text = replace_once(text,
        '    row_sets = [[(12.0, 1), (7.0, 1), (3.0, None), (2.0, 2)], [(2.0, None), (3.0, None)], []]',
        '    row_sets = [\n'
        '        [(12.0, 1), (7.0, 1), (3.0, None), (2.0, 2)],\n'
        '        [(2.0, None), (3.0, None)],\n'
        '        [],\n'
        '        [(0.0, 1), (0.0, None)],\n'
        '        [(-2.0, 1), (2.0, 2)],\n    ]')
    text = replace_once(text,
        '        sql = metric["expression"]["dialects"][0]["expression"]\n',
        '        sql = metric["expression"]["dialects"][0]["expression"]\n'
        '        # SQLite returns NULL for a raw division by zero too, so numeric\n'
        '        # equivalence alone does not prove upstream #163 was preserved.\n'
        '        assert "NULLIF(" in sql.upper(), sql\n')
    test.write_text(text)
    git("add", "dbt/README.md", "dbt/tests/test_ratio_helpers_cli.py")
    if git("diff", "--name-only", "--diff-filter=U").stdout.strip():
        raise RuntimeError("Unresolved conflicts remain")
    for path, expected in EXPECTED.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Candidate checksum differs: {path}")
    files = git("diff", "--cached", "--name-only", UPSTREAM).stdout.splitlines()
    if set(files) != set(EXPECTED):
        raise RuntimeError(f"Unexpected PR scope: {files}")
    git("diff", "--cached", "--check", UPSTREAM)
    git("diff", "--cached", "--exit-code", UPSTREAM, "--", ".github", "ossie", ".gitmodules")
    for path in files:
        if path.endswith(".py"):
            source = Path(path).read_text()
            compile(source, path, "exec")
            if "Licensed to the Apache Software Foundation" not in "\n".join(source.splitlines()[:20]):
                raise RuntimeError(f"Missing ASF source header: {path}")
    tree = git("write-tree").stdout.strip()
    env = os.environ.copy()
    env.update(GIT_AUTHOR_DATE=os.environ["FIXED_DATE"], GIT_COMMITTER_DATE=os.environ["FIXED_DATE"])
    git("commit", "-m", "Merge latest upstream and preserve ratio-helper NULLIF round trips", env=env)
    commit = git("rev-parse", "HEAD").stdout.strip()
    if git("show", "-s", "--format=%P", "HEAD").stdout.strip() != f"{ORIGINAL} {UPSTREAM}":
        raise RuntimeError("Wrong merge parents")
    if git("rev-parse", "HEAD^{tree}").stdout.strip() != tree:
        raise RuntimeError("Commit tree differs")
    git("submodule", "update", "--init", "--recursive")
    patch = subprocess.check_output(["git", "diff", "--binary", UPSTREAM, "HEAD"])
    (evidence / "integration.patch").write_bytes(patch)
    (evidence / "prepared.json").write_text(json.dumps({
        "original": ORIGINAL, "upstream": UPSTREAM, "tree": tree,
        "candidate_commit": commit, "files": files, "sha256": EXPECTED,
        "tests_executed": False, "published": False,
    }, indent=2) + "\n")
    git("diff", "--exit-code")
    git("diff", "--cached", "--exit-code")
    print("Prepared local candidate", commit, "tree", tree, flush=True)


if __name__ == "__main__":
    main()
