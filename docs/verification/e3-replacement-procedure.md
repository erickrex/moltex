# Replacing the E3 Golden Export

The Golden Export is a reviewed oracle. Tests must never regenerate or overwrite it.

1. Run a candidate into the ignored staging directory:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-golden-path.ps1
   ```

   The exporter runner captures bounded HTML but does not request, upload, or register
   screenshots. Automated source visuals are acquired from the H2 capture plan before H3.

2. Review `golden-output/candidate-report.json`, the bounded HTML, capability inventory,
   completeness counts, media map, and privacy canary result. Any count or validation
   mismatch stops the script before promotion.
3. Compare the candidate with the current sample and explain every intentional contract or
   fixture change in the replacement commit.
4. Only after review, explicitly copy `golden-candidate.zip` to
   `samples/golden-export.zip` and the report to `samples/golden-export.validation.json`.
5. Update `golden-export.bundle-id.txt`, `golden-export.expected.json`, the reconciliation,
   capability/privacy review, and verification receipt in the same change. After H2 is
   available, also regenerate and review the bundle-bound visual capture plan and receipt.
6. Run the immutable Golden Export PHPUnit test, standalone validator, complete PHPUnit
   suite, standalone regressions, and a fresh disposable WordPress workflow.

The candidate workflow deliberately has no promotion switch. This prevents a routine test
run from silently regenerating its own expected result.
