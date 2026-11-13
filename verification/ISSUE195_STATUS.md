# Issue 195 independent verification status

Upstream issue: https://github.com/apache/ossie-converters/issues/195

This is a contributor-owned verification branch, not an Apache PR or an accepted upstream fix. It stores a patch and verification workflows; the workflows apply the patch to a separate complete checkout of the pinned upstream source. No production source files in Apache were modified.

## Pinned inputs

- Upstream converter source: `7bd9c32614fd884f14624fa98289ff556eb68a49`.
- Ossie SDK submodule: `a498fce5455dcc209605cdbb30b21e47068ff15e`.
- Verification commit: `b48162890f317672b14af576d4029440101cf92c`.
- Candidate patch: [immutable patch](https://github.com/zljie/ossie-converters/blob/b48162890f317672b14af576d4029440101cf92c/verification/issue195/candidate.patch).
- Patch SHA-256: `1dbb8cd4036acf66044f4916c2098036eea5d4520edbe7f19671aadceddae2e4`.
- Tested source tree in completed matrix jobs: `9f267b2cafbbeda92e2323b5064b00fbaafa5a39` (upstream source plus candidate; this is not the verification branch's tree).

## Work actually executed

1. [Independent baseline and CLI reproduction](https://github.com/zljie/ossie-converters/actions/runs/43413252726): the complete unmodified Sigma suite passed 175 tests. Running the issue's CLI input produced `[calendar_date]`. A regression assertion expecting `[dim_date_vw/calendar_date]` failed as intended, without a collection error.
2. The complete source, submodule, and locked third-party wheels were retrieved from that run. The artifact SHA-256 was checked before local extraction. A separate offline Python 3.13 environment reproduced the 175-test baseline and then passed the 202-test candidate suite.
3. [Candidate matrix](https://github.com/zljie/ossie-converters/actions/runs/43414202018): completed Python 3.11, 3.12, and 3.13 jobs each report the results below. Their downloaded JUnit reports and result.json records were cross-checked, including identical patch and tested-tree fingerprints.

| Stage | Tests | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unmodified full Sigma suite | 175 | 175 | 0 | 0 | 0 |
| New regressions against unmodified production code | 27 | 12 | 15 expected | 0 | 0 |
| Full suite with candidate | 202 | 202 | 0 | 0 | 0 |

The exact issue CLI input produces `[dim_date_vw/calendar_date]` after applying the candidate. The new suite also invokes actual CLI export/import/export and checks repeated round trips.

**Python 3.14 is still in progress at this status update, at the initial checkout stage. It is not counted as passed.** Consult the linked run for later state; a started job is not test evidence.

## Candidate scope

Only direct SQL column expressions in warehouse-table sources gain a physical source-table prefix. Logical dataset aliases, field renaming, identifier case, native source/formula overrides, calculated expressions, element-scoped metrics, the other five source kinds, and repeated round trips are covered by tests. Existing tests that pinned the old direct-reference strings have their expectations updated; numeric/date formatting assertions remain intact.

Five candidate files: the exporter, formula translator, existing exporter tests, a new regression test module, and the Sigma README. The dependencies and importer are unchanged. Fully qualified SQL paths and source-path parsing remain outside the candidate's scope.

Reference: https://help.sigmacomputing.com/docs/example-representation-data-model-with-a-table-and-a-calculated-column

## Unfinished gates and publication state

- No live Sigma upload/query was performed; offline CLI tests do not prove platform execution.
- No Apache-hosted CI was run for this candidate.
- No competing PR was opened, no issue was assigned, and no community approval is claimed.
- A single attempt to post collaborative validation evidence to issue #195 returned HTTP 403, `Resource not accessible by integration`; no upstream comment was published by that attempt.
- The original reporter has offered to contribute. Coordinate with that contributor and obtain a platform check before proposing the final upstream fix.

AI assistance was used for the candidate and tests. The contributor remains responsible for reviewing the change and verification evidence.
