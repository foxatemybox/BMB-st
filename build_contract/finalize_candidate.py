from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
MARKER_KIND = "BADLOOM_BMB_ST_LAUNCHER_PREPARED"
ERROR_CODE = "BMB_ST_LAUNCHER_PREP_REQUIRED"
PACKAGE_EXE = "BADLOOM_Manga_Browser_Current_TEST.exe"


def fail(message: str) -> "NoReturn":
    raise RuntimeError(f"{ERROR_CODE}: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_marker(path: Path, expected_commit: str) -> dict:
    if not path.is_file():
        fail("BMB-st candidate must be prepared by BADLOOM Manga Launcher")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"launcher marker is unreadable: {exc}")
    if payload.get("schema") != SCHEMA or payload.get("kind") != MARKER_KIND:
        fail("launcher marker contract is invalid")
    if payload.get("source_commit") != expected_commit:
        fail("launcher marker does not match the requested BD source commit")
    if not payload.get("launcher_version") or not payload.get("build_id"):
        fail("launcher marker identity is incomplete")
    return payload


def make_zip(package_dir: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package_dir).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize a launcher-prepared BADLOOM Manga Browser stable candidate.")
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--launcher-marker", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-branch", required=True)
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    output_dir = args.output_dir.resolve()
    marker = load_marker(args.launcher_marker.resolve(), args.source_commit)

    exe = package_dir / PACKAGE_EXE
    internal = package_dir / "_internal"
    if not exe.is_file() or not internal.is_dir():
        fail("launcher-prepared Current package is incomplete")

    short_commit = args.source_commit[:12]
    candidate = output_dir / f"BADLOOM_Manga_Browser_BMB-st_{short_commit}.zip"
    make_zip(package_dir, candidate)

    receipt = {
        "schema": SCHEMA,
        "kind": "BADLOOM_BMB_ST_CANDIDATE",
        "status": "passed",
        "source_repository": "foxatemybox/BD",
        "source_branch": args.source_branch,
        "source_commit": args.source_commit,
        "launcher_version": marker["launcher_version"],
        "launcher_build_id": marker["build_id"],
        "prepared_utc": marker.get("prepared_utc"),
        "finalized_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate.name,
        "candidate_sha256": sha256(candidate),
        "candidate_bytes": candidate.stat().st_size,
        "executable": PACKAGE_EXE,
        "executable_sha256": sha256(exe),
        "stable_gate": "BMB_ST_LAUNCHER_PREP_REQUIRED",
    }
    (output_dir / "BMB_ST_BUILD_RECEIPT.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(23)
