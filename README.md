# BMB-st

Stable-candidate channel for BADLOOM Manga Browser.

This repository intentionally does **not** contain the launcher preparation marker required by `build_contract/finalize_candidate.py`. Running stable finalization directly returns `BMB_ST_LAUNCHER_PREP_REQUIRED`.

The normal Current/dev build in `BD` is unaffected. BADLOOM Manga Launcher checks `BD`, builds the exact current commit in an isolated worktree, temporarily prepares the BMB-st contract, finalizes the candidate here, removes the temporary marker and publishes the candidate receipt.
