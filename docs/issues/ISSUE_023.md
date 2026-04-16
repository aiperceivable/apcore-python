### Problem
The `Executor.validate()` preflight check was using a hardcoded sequence of 7 inline checks that was detached from the actual execution pipeline. This meant that any custom `pure=True` steps added by users would be ignored during validation, and changes to the standard pipeline would not be automatically reflected in the preflight results.

### Why
Validation was originally implemented as a separate, manual logic path to avoid the overhead of a full pipeline run. However, this led to maintenance overhead and a "drifting" implementation that did not accurately represent the true execution behavior.

### Solution
In v0.17.0, the `validate()` method was refactored to fully delegate to the `PipelineEngine` with `dry_run=True`. All steps marked as `pure=True` (including context creation, ACL, and input validation) automatically participate in the validation, ensuring the preflight check is always consistent with the real pipeline.

### Verification
Verified that `Executor.validate()` now correctly reports failures from user-added `pure=True` steps and that the returned `PreflightResult` correctly aggregates status from all participating steps.
