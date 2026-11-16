#!/usr/bin/env python3
"""Copy a large directory tree to another drive, verify it, then (optionally) delete the source.

Why a script instead of one-liners: the copy and the verification must be the SAME
run with the SAME manifest, otherwise "it copied fine" and "it verified fine" can be
true of two different file sets. Default mode copies + verifies + writes a manifest and
touches nothing else; the source is only deleted when you pass --delete-source.

Usage:
  python move-verify-delete.py --src D:\big\cache --dst H:\dev\cache\big --manifest D:\hermes-test\move.json
  python move-verify-delete.py --src ... --dst ... --check-only        # re-verify an existing copy
  python move-verify-delete.py --src ... --dst ... --delete-source --manifest D:\hermes-test\move.json

Exit codes: 0 ok / 2 verification mismatch (source left intact) / 3 delete step had failures.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

BIG = 50 * 1024 * 1024  # files at or above this get a sha256 comparison


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(root: Path):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = Path(dirpath) / name
            try:
                yield p, p.stat().st_size
            except OSError as ex:
                # e.g. ACL denies read but the file is still listed
                print(f"!! stat failed: {p} ({type(ex).__name__})")


def copy_tree(src: Path, dst: Path) -> list:
    errors = []
    dst.mkdir(parents=True, exist_ok=True)

    # copy2 per file (not copytree): copytree aborts the WHOLE tree on one
    # unreadable file (shutil.Error), which looks like total failure.
    for dirpath, _dirs, files in os.walk(src):
        rel = Path(dirpath).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            try:
                shutil.copy2(Path(dirpath) / name, dst / rel / name)
            except Exception as ex:  # noqa: BLE001 - report, keep going
                errors.append(f"{Path(dirpath) / name}: {type(ex).__name__}: {ex}")
                print(f"!! copy error: {errors[-1]}")
    return errors


def verify(src: Path, dst: Path) -> tuple:
    src_files = dict(walk(src))
    dst_files = dict(walk(dst))
    missing, size_bad, big_bad, big_checked = [], [], [], 0
    for p, size in src_files.items():
        rel = p.relative_to(src)
        if rel not in dst_files:
            missing.append(str(rel))
            continue
        if dst_files[rel] != size:
            size_bad.append(str(rel))
        if size >= BIG:
            big_checked += 1
            if sha256(p) != sha256(dst / rel):
                big_bad.append(str(rel))
    result = {
        "src_files": len(src_files), "dst_files": len(dst_files),
        "src_bytes": sum(src_files.values()), "dst_bytes": sum(dst_files.values()),
        "missing": missing, "size_mismatch": size_bad,
        "sha256_checked": big_checked, "sha256_mismatch": big_bad,
    }
    return result, src_files


def delete_source(src: Path, manifest: dict) -> int:
    """Delete only files that verified clean: re-check size against the manifest first."""
    expected = {e["rel"]: e["size"] for e in manifest["files"]}
    failures = 0
    for p, size in list(walk(src)):
        rel = str(p.relative_to(src))
        if expected.get(rel) != size:
            print(f"skip (not in manifest or size changed): {rel}")
            failures += 1
            continue
        try:
            p.unlink()
        except OSError as ex:
            print(f"!! delete failed: {rel} ({type(ex).__name__}: {ex})")
            failures += 1
    for dirpath, _dirs, files in os.walk(src, topdown=False):
        if not files:
            try:
                Path(dirpath).rmdir()
            except OSError:
                pass
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, type=Path)
    ap.add_argument("--dst", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--check-only", action="store_true", help="do not copy, only verify")
    ap.add_argument("--delete-source", action="store_true",
                    help="delete source files AFTER verification passes (needs user consent)")
    a = ap.parse_args()

    if not a.src.is_dir():
        print(f"!! --src is not a directory: {a.src}")
        return 1
    src, dst = a.src.resolve(), a.dst.resolve()

    if not a.check_only:
        print(f"copying {src} -> {dst}")
        errors = copy_tree(src, dst)
        if errors:
            print(f"!! {len(errors)} file(s) failed to copy; verification continues")

    result, src_files = verify(src, dst)
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, list)}, indent=2))
    for key in ("missing", "size_mismatch", "sha256_mismatch"):
        if result[key]:
            print(f"!! {key}: {len(result[key])} -> {result[key][:10]}")

    manifest = {
        "src": str(src), "dst": str(dst),
        "files": [{"rel": str(p.relative_to(src)), "size": s} for p, s in src_files.items()],
        "verify": result,
    }
    if a.manifest:
        a.manifest.parent.mkdir(parents=True, exist_ok=True)
        a.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"manifest: {a.manifest}")

    clean = (result["src_files"] == result["dst_files"]
             and result["src_bytes"] == result["dst_bytes"]
             and not result["missing"] and not result["size_mismatch"]
             and not result["sha256_mismatch"])
    if not clean:
        print("VERIFY FAILED - source left untouched")
        return 2
    print(f"VERIFY OK ({result['src_files']} files, {result['src_bytes']} bytes, "
          f"{result['sha256_checked']} sha256 checked)")

    if a.delete_source:
        failures = delete_source(src, manifest)
        print(f"delete: {result['src_files'] - failures} removed, {failures} skipped/failed")
        return 3 if failures else 0
    print("source kept (pass --delete-source after the user approves)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
