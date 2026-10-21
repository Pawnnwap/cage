from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evidence import EvidenceSigner


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Cage evidence JSON pack")
    parser.add_argument("path", help="Path to the evidence JSON file")
    args = parser.parse_args()

    with open(args.path, encoding="utf-8") as handle:
        pack = json.load(handle)

    signature = pack.pop("signature", None)
    public_key = pack.pop("public_key", None)
    pack.pop("signature_algorithm", None)
    pack.pop("key_fingerprint", None)

    if not signature or not public_key:
        print("INVALID: missing signature or public_key")
        return 1

    if EvidenceSigner.verify(pack, signature, public_key):
        print("VALID: Ed25519 signature matches the canonical evidence pack")
        return 0

    print("INVALID: signature does not match the evidence pack")
    return 1


if __name__ == "__main__":
    sys.exit(main())
