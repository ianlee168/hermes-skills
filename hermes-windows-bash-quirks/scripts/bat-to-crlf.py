#!/usr/bin/env python3
"""Rewrite Windows .bat/.cmd files to CRLF line endings.

cmd.exe mis-parses LF-only batch files (for /f, timeout and multi-line blocks
fail with errors that look like typos). write_file emits LF, so run this after
authoring any .bat and before handing it to the user.

Usage:
    python bat-to-crlf.py <file-or-dir> [<file-or-dir> ...]

Idempotent: CRLF input stays CRLF. Prints one line per file it touched.
"""
import os
import sys


def fix(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if not data:
        return False
    new = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if new == data:
        return False
    with open(path, "wb") as fh:
        fh.write(new)
    return True


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    targets = []
    for arg in argv:
        if os.path.isdir(arg):
            for name in sorted(os.listdir(arg)):
                if name.lower().endswith((".bat", ".cmd")):
                    targets.append(os.path.join(arg, name))
        elif os.path.isfile(arg):
            targets.append(arg)
        else:
            print("skip (not found):", arg)
    if not targets:
        print("no .bat/.cmd files found")
        return 1
    for path in targets:
        print(("CRLF fixed: " if fix(path) else "already CRLF: ") + path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
