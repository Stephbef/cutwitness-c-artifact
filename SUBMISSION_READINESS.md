# Submission-support readiness

This repository has been cleaned of manuscript-planning result artifacts. The implementation, frozen protocol, analysis code, tests, and anonymization controls remain.

Submission-support readiness requires a sealed observed-results bundle under `results/`, including `FINAL_VERDICT.json` and the corresponding provenance required by the analysis pipeline.

The repository must fail closed when that observed bundle is absent. No planning, best-case, or simulated scientific values are used as a substitute.
