# BMB-st

Stable-candidate channel for BADLOOM Manga Browser.

Stable finalization no longer uses a launcher-preparation marker or a blocking gate. `build_contract/finalize_candidate.py` packages a prepared Current build directly and records the exact BD source branch and commit in the build receipt.

BADLOOM Manga Launcher may still orchestrate checkout, build and publication, but BMB-st finalization itself is no longer conditional on launcher-created marker state.
