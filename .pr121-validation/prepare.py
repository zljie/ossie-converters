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
"""Integrate fixed source SHAs; keep test tooling outside the candidate tree."""
import json
import os
from pathlib import Path
import subprocess
import sys


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    original, upstream = os.environ["ORIGINAL"], os.environ["UPSTREAM"]
    if git("rev-parse", "HEAD") != original:
        raise SystemExit("Wrong starting commit")
    subprocess.run(["git", "merge", "--no-commit", "--no-ff", upstream], check=True)
    path = Path("dbt/tests/test_ratio_helpers_meta_integration.py")
    text = path.read_text()
    replacements = [
        ("PR #121/#53 integration", "PR #121/#145 integration"),
        ("from ossie import OssieCustomExtension, OssieDocument, OssieVendor", "from ossie import OssieCustomExtension, OssieDataType, OssieDocument, OssieVendor"),
        ("data=json.dumps(payload)", 'data=json.dumps({"meta": payload})'),
        ("_user_metadata(json.loads(extensions[0].data))", '_user_metadata(json.loads(extensions[0].data)["meta"])'),
        ('json.loads(metric.custom_extensions[0].data)["team"]', 'json.loads(metric.custom_extensions[0].data)["meta"]["team"]'),
        ("_user_metadata(json.loads(owner.custom_extensions[0].data))", '_user_metadata(json.loads(owner.custom_extensions[0].data)["meta"])'),
        ('data=json.dumps({"team": "other"})', 'data=json.dumps({"meta": {"team": "other"}})'),
    ]
    for before, after in replacements:
        if text.count(before) != 1:
            raise SystemExit(f"Unexpected fixture shape: {before!r}")
        text = text.replace(before, after)
    expected_end = '    owner = next(m for m in result.output.metrics if m.name == "avg")'
    if not text.rstrip().endswith(expected_end):
        raise SystemExit("Review the duplicate-metadata regression before updating it")
    text = text.rstrip() + '\n    assert _user_metadata(owner.config.meta) == USER_META\n'
    text += '''

@pytest.mark.parametrize("prefix", [
    {"materialized": "table"},
    {"meta": {}},
    {"team": "unwrapped-legacy-metadata"},
])
def test_non_meta_entries_do_not_shadow_ratio_user_metadata(prefix):
    doc = _document()
    doc.metrics[0].custom_extensions.insert(0, OssieCustomExtension(
        vendor_name=OssieVendor.DBT.value, data=json.dumps(prefix)))
    forward = OssieToMSIConverter().convert(doc)
    assert forward.issues == []
    owner = next(m for m in forward.output.metrics if m.name == "avg")
    assert _user_metadata(owner.config.meta) == USER_META
    assert set(unchanged_ratio_helpers(forward.output.metrics)) == {"avg"}
    reverse = MSIToOssieConverter().convert(forward.output)
    assert reverse.issues == []
    assert [m.name for m in reverse.output.metrics] == ["avg"]
    assert _user_metadata(json.loads(reverse.output.metrics[0].custom_extensions[0].data)["meta"]) == USER_META


@pytest.mark.parametrize("invalid_meta", [None, [], "invalid", 17])
def test_invalid_wrapped_meta_keeps_warning_and_valid_ratio_provenance(invalid_meta):
    doc = _document()
    doc.metrics[0].custom_extensions.insert(0, OssieCustomExtension(
        vendor_name=OssieVendor.DBT.value, data=json.dumps({"meta": invalid_meta})))
    forward = OssieToMSIConverter().convert(doc)
    assert [(i.issue_type, i.element_name) for i in forward.issues] == [
        (ConverterIssueType.INVALID_DBT_CUSTOM_EXTENSION, "avg")]
    owner = next(m for m in forward.output.metrics if m.name == "avg")
    assert _user_metadata(owner.config.meta) == USER_META
    assert all(m.type_params.is_private is False for m in forward.output.metrics)
    assert set(unchanged_ratio_helpers(forward.output.metrics)) == {"avg"}


@pytest.mark.parametrize("datatype", [OssieDataType.DECIMAL, OssieDataType.DATE_TIME_TZ])
def test_restored_datatype_is_applied_before_signing_ratio_family(datatype):
    meta = deepcopy(USER_META)
    meta["ossie"]["datatype"] = "Integer"
    doc = _document(meta=meta)
    doc = doc.model_copy(update={"metrics": [doc.metrics[0].model_copy(update={"datatype": datatype})]})
    expected = deepcopy(meta)
    expected["ossie"]["datatype"] = datatype.value
    for _ in range(3):
        before = doc.model_dump_json()
        forward = OssieToMSIConverter().convert(doc)
        assert doc.model_dump_json() == before
        assert forward.issues == []
        manifest = PydanticSemanticManifest.parse_raw(forward.output.json(by_alias=True, exclude_none=True))
        owner = next(m for m in manifest.metrics if m.name == "avg")
        assert _user_metadata(owner.config.meta) == expected
        assert set(unchanged_ratio_helpers(manifest.metrics)) == {"avg"}
        reverse = MSIToOssieConverter().convert(manifest)
        assert reverse.issues == []
        assert [m.name for m in reverse.output.metrics] == ["avg"]
        assert reverse.output.metrics[0].datatype == datatype
        assert _user_metadata(json.loads(reverse.output.metrics[0].custom_extensions[0].data)["meta"]) == expected
        doc = OssieDocument.model_validate_json(reverse.output.model_dump_json())
'''
    compile(text, str(path), "exec")
    path.write_text(text)
    subprocess.run(["git", "add", str(path)], check=True)
    subprocess.run(["git", "diff", "--cached", "--check"], check=True)
    if git("diff", "--name-only", "--diff-filter=U"):
        raise SystemExit("Unresolved conflicts")
    files = git("diff", "--cached", "--name-only", upstream).splitlines()
    if not files or any(not name.startswith("dbt/") for name in files):
        raise SystemExit(f"Unexpected candidate scope: {files}")
    record = {"original": original, "upstream": upstream, "tree": git("write-tree"), "files": files}
    Path(sys.argv[1]).write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
