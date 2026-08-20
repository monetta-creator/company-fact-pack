"""`make validate` — the deterministic CI gate. Nonzero exit on any hard failure."""

from __future__ import annotations

import sys

from scripts.validate import orphans, refs_check, schema_check, staleness


def main() -> int:
    rc = 0
    print("== schema_check ==")
    rc |= schema_check.main()
    print("== refs_check ==")
    sys.argv = [sys.argv[0]]  # refs_check parses args; run without --hashes by default
    rc |= refs_check.main()
    print("== staleness ==")
    rc |= staleness.main()
    print("== orphans ==")
    rc |= orphans.main()
    print("VALIDATE:", "FAIL" if rc else "OK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
