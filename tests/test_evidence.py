from __future__ import annotations

from app.evidence import EvidenceSigner


def test_sign_verify_and_tamper_detection(tmp_path):
    signer = EvidenceSigner(tmp_path / "evidence_key.pem")
    payload = {
        "task": {"id": "t1", "status": "completed"},
        "events": [{"id": 1, "kind": "command_finished", "payload": {"exit": 0}}],
    }
    signature = signer.sign(payload)
    public_key = signer.public_key_b64()

    assert EvidenceSigner.verify(payload, signature, public_key) is True

    tampered = {
        "task": {"id": "t1", "status": "completed"},
        "events": [{"id": 1, "kind": "command_finished", "payload": {"exit": 1}}],
    }
    assert EvidenceSigner.verify(tampered, signature, public_key) is False

    pack = signer.signed_pack(payload)
    assert pack["signature_algorithm"] == "Ed25519"
    assert pack["signature"] == signature
    assert pack["public_key"] == public_key
    assert pack["key_fingerprint"] == signer.fingerprint()
