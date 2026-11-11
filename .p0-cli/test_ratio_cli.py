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

"""Exercise the actual CLI and dbt manifest parser, not a mocked parser."""
import json
import subprocess
import sys

import pytest
import yaml

from tests.helpers import _ossie_dataset, _ossie_doc, _ossie_field, _ossie_metric


@pytest.mark.parametrize(
    "expression",
    [
        "SUM(orders.amount) / COUNT(orders.order_id)",
        "SUM(orders.amount) / COUNT(DISTINCT orders.order_id)",
        "SUM(orders.amount) / COUNT(*)",
        "(SUM(orders.amount) / COUNT(orders.order_id)) / SUM(orders.amount)",
    ],
    ids=["count_column", "count_distinct", "count_star", "nested_count"],
)
def test_real_cli_three_round_trips_do_not_grow_helpers(tmp_path, expression):
    document = _ossie_doc(
        datasets=[_ossie_dataset("orders", fields=[_ossie_field("amount"), _ossie_field("order_id")])],
        metrics=[_ossie_metric("avg", expression)],
    )
    input_path = tmp_path / "input.yaml"
    input_path.write_text(document.to_ossie_yaml(), encoding="utf-8")
    observed = []
    for round_number in range(3):
        manifest_path = tmp_path / f"manifest-{round_number}.json"
        output_path = tmp_path / f"round-{round_number}.yaml"
        for command, source, target in (
            ("ossie-to-msi", input_path, manifest_path),
            ("msi-to-ossie", manifest_path, output_path),
        ):
            result = subprocess.run(
                [sys.executable, "-m", "ossie_dbt.cli", command, "-i", str(source), "-o", str(target)],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert "[WARNING]" not in result.stderr, result.stderr
        manifest = json.loads(manifest_path.read_text())
        assert all(not metric["type_params"].get("is_private", False) for metric in manifest["metrics"])
        output = yaml.safe_load(output_path.read_text())
        observed.append([metric["name"] for metric in output["metrics"]])
        input_path = output_path
    print("Observed CLI output metric names:", observed)
    assert observed == [["avg"], ["avg"], ["avg"]], observed
