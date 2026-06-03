# Level 1 Grader Package

This `test1/` folder is the clean package copied into a student submission.
The source of truth is `level1/grader/`; regenerate this folder with:

```bash
python level1/scripts/build_test1_package.py
```

From a submission root, run:

```bash
python test1/main.py
```

Equivalent explicit command:

```bash
python -m test1.grader.main . --event-file input/aperiodic_n_sporadic.json --report-dir test1/reports
```

`--event-file` is optional. If omitted, the grader reads
`input/aperiodic_n_sporadic.json` from the submission folder.

Reports are written to:

- `test1/reports/grader_report.json`
- `test1/reports/grader_report.txt`
