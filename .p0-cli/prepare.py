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
import json
import os
from pathlib import Path
import subprocess
import sys


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Unexpected source shape: {old!r}')
    return text.replace(old, new, 1)


original, upstream = os.environ['ORIGINAL'], os.environ['UPSTREAM']
assert git('rev-parse', 'HEAD') == original
subprocess.run(['git', 'submodule', 'update', '--init', '--recursive'], check=True)
assert not git('status', '--porcelain', '--untracked-files=no')
subprocess.run(['git', 'merge', '--no-commit', '--no-ff', upstream], check=True)
path = Path('dbt/src/ossie_dbt/ratio_helpers.py')
text = path.read_text()
text = replace_once(text,
    'from metricflow_semantic_interfaces.implementations.metric import PydanticMetric',
    'from metricflow_semantic_interfaces.errors import ModelTransformError\nfrom metricflow_semantic_interfaces.implementations.metric import PydanticMetric\nfrom metricflow_semantic_interfaces.implementations.project_configuration import PydanticProjectConfiguration\nfrom metricflow_semantic_interfaces.implementations.semantic_manifest import PydanticSemanticManifest\nfrom metricflow_semantic_interfaces.transformations.convert_count import ConvertCountMetricToSumRule')
text = replace_once(text,
    'def _signature(metrics: Sequence[PydanticMetric]) -> str:\n    payload',
    '''def _signature(metrics: Sequence[PydanticMetric], *, normalize_count: bool = True) -> str:
    if normalize_count:
        # The CLI parser applies this same rule before reverse conversion. Use
        # a private copy so signing never changes public helper definitions.
        # The rule is idempotent: already-rewritten SUM metrics stay unchanged.
        manifest = PydanticSemanticManifest(
            semantic_models=[],
            metrics=deepcopy(list(metrics)),
            project_configuration=PydanticProjectConfiguration(),
        )
        metrics = ConvertCountMetricToSumRule.transform_model(manifest).metrics
    payload''')
text = replace_once(text, '"version": 1,', '"version": 2,')
text = replace_once(text,
    '    Compare before MetricFlow transforms definitions (e.g. COUNT into SUM). Scan\n    all external serialized definitions conservatively for helper names, including',
    '    Version 2 compares COUNT-normalized definitions before or after CLI parsing.\n    Version 1 remains valid only for its exact original definitions; when they\n    have already changed, retain the helpers rather than infer ownership. Scan\n    all external serialized definitions conservatively for helper names, including')
text = replace_once(text, 'marker.get("version") != 1', 'marker.get("version") not in (1, 2)')
text = replace_once(text,
    '        if marker.get("signature") != _signature([index[name] for name in group]):\n            continue',
    '''        try:
            signature = _signature(
                [index[name] for name in group], normalize_count=marker["version"] == 2
            )
        except ModelTransformError:
            # Invalid/edited COUNT definitions are not proof of ownership.
            # The converter's normal validation still reports invalid input.
            continue
        if marker.get("signature") != signature:
            continue''')
text = replace_once(text, '# Generated metrics currently have no config; retain any future annotations.',
    '# Retain user annotations while adding converter provenance to the owner.')
compile(text, str(path), 'exec')
path.write_text(text)
test_path = Path('dbt/tests/test_ratio_helpers_cli.py')
assert not test_path.exists()
test_path.write_text(Path(sys.argv[1]).read_text())
readme = Path('dbt/README.md')
doc = readme.read_text()
doc = replace_once(doc, '## Development', '''### Generated ratio helper provenance

New helper families use provenance version 2. Signatures apply MetricFlow's
COUNT-to-SUM normalization to a private copy on both generation and inspection,
so the raw converter API and the CLI's dbt manifest parser agree. This does not
make the helpers private or rewrite their emitted definitions. All other
semantic fields and external-consumer checks remain part of the conservative
retention contract. Version 1 markers are accepted only when their exact original
definitions still match; otherwise helpers are retained rather than guessed.

## Development''')
readme.write_text(doc)
subprocess.run(['git', 'add', str(path), str(test_path), str(readme)], check=True)
# Check only the proposed PR diff, not whitespace inherited from upstream.
subprocess.run(['git', 'diff', '--cached', '--check', upstream], check=True)
assert not git('diff', '--name-only', '--diff-filter=U')
changed = git('diff', '--cached', '--name-only', upstream).splitlines()
assert changed and all(name.startswith('dbt/') for name in changed), changed
record = {'original': original, 'upstream': upstream, 'tree': git('write-tree'), 'files': changed}
Path(sys.argv[2]).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
