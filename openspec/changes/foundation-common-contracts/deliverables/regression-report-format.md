# Regression Report Format (Task 5.4)

Source: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md

## JSON format

The canonical regression report is `report.json` produced by
`aegi_core.regression.report.write_regression_report()`.

Schema (v1):

```json
{
  "version": 1,
  "generated_at": "<ISO-8601>",
  "thresholds": { "<metric>": <float> },
  "fixtures": [
    {
      "fixture_id": "<string>",
      "domain": "<string>",
      "metrics": { "<metric>": <float> }
    }
  ],
  "summary": {
    "fixtures_count": "<int>",
    "<metric>_min": <float>
  }
}
```

## Markdown format

A human-readable `report.txt` is generated alongside the JSON.
Both files are written to the output directory by `write_regression_report()`.

## Gate rule

A PR MUST NOT be merged if any P0 threshold is violated in the regression report.
