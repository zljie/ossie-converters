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
tools = Path(__file__).parent
path = Path('dbt/src/ossie_dbt/ratio_helpers.py')
assert git('hash-object', str(path)) == '28193710fbf8fcd0710696e2c3cb6004e2ef0729'
text = (tools / 'ratio_helpers.py').read_text()
compile(text, str(path), 'exec')
path.write_text(text)
test_path = Path('dbt/tests/test_ratio_helpers_cli.py')
assert not test_path.exists()
tests = Path(sys.argv[1]).read_text() + (tools / 'additional_tests.py').read_text()
compile(tests, str(test_path), 'exec')
test_path.write_text(tests)
existing_tests = Path('dbt/tests/test_ossie_to_msi.py')
existing_tests.write_text(replace_once(existing_tests.read_text(), 'assert provenance["version"] == 1', 'assert provenance["version"] == 2'))
readme = Path('dbt/README.md')
doc = replace_once(readme.read_text(), '## Development', '''### Generated ratio helper provenance

New helper families use provenance version 2. Signatures reuse MetricFlow's
COUNT-to-SUM, boolean-SUM, and MEDIAN-to-percentile rules on a private copy,
so the raw converter API and the CLI's dbt manifest parser agree, including
later round trips that re-express a COUNT as a boolean aggregation. This does
not make the helpers private or rewrite their emitted definitions. All other
semantic fields and external-consumer checks remain part of the conservative
retention contract. Version 1 markers are accepted only when their exact original
definitions still match; otherwise helpers are retained rather than guessed.

## Development''')
readme.write_text(doc)
subprocess.run(['git', 'add', str(path), str(test_path), str(existing_tests), str(readme)], check=True)
subprocess.run(['git', 'diff', '--cached', '--check', upstream], check=True)
assert not git('diff', '--name-only', '--diff-filter=U')
changed = git('diff', '--cached', '--name-only', upstream).splitlines()
assert changed and all(name.startswith('dbt/') for name in changed), changed
record = {'original': original, 'upstream': upstream, 'tree': git('write-tree'), 'files': changed}
Path(sys.argv[2]).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
