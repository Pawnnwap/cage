from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


class EvidenceSigner:
    """Ed25519 signer for evidence packs.

    The private key stays on the control plane. The public key is returned with
    every evidence pack so a judge can verify the pack without the secret.
    """

    def __init__(self, key_path: Path):
        self.key_path = key_path
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self._private = self._load_or_create()
        self._public = self._private.public_key()

    def _load_or_create(self) -> Ed25519PrivateKey:
        if self.key_path.is_file():
            data = self.key_path.read_bytes()
            loaded = serialization.load_pem_private_key(data, password=None)
            if isinstance(loaded, Ed25519PrivateKey):
                return loaded
            raise ValueError("evidence key is not an Ed25519 private key")
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.key_path.write_bytes(pem)
        try:
            os.chmod(self.key_path, 0o600)
        except OSError:
            pass
        return key

    def public_key_b64(self) -> str:
        raw = self._public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def fingerprint(self) -> str:
        raw = self._public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(raw).hexdigest()[:16]

    def sign(self, payload: dict[str, Any]) -> str:
        return base64.b64encode(self._private.sign(canonical(payload))).decode(
            "ascii"
        )

    @staticmethod
    def verify(
        payload: dict[str, Any], signature_b64: str, public_key_b64: str
    ) -> bool:
        try:
            public = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(public_key_b64)
            )
            public.verify(
                base64.b64decode(signature_b64), canonical(payload)
            )
            return True
        except Exception:
            return False

    def signed_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        signature = self.sign(payload)
        return {
            **payload,
            "signature_algorithm": "Ed25519",
            "signature": signature,
            "public_key": self.public_key_b64(),
            "key_fingerprint": self.fingerprint(),
        }
