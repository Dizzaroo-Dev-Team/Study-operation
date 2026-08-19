"""#8 — sequential signing auto-handoff default.

The engine's ordered_signing already auto-advances when config.handoff=="auto"
(unified_signing._advance_engine_slot). These tests pin the DEFAULT: hand-off is
automatic unless a workflow explicitly opts into owner_gated — so multi-party signing
needs no manual poke between signers.
"""
from app.modules.agreements.services.unified_signing import _handoff


class _Step:
    def __init__(self, config):
        self.config = config


def test_handoff_defaults_to_auto_when_unset():
    assert _handoff(_Step(None)) == "auto"
    assert _handoff(_Step({})) == "auto"
    assert _handoff(_Step({"signers": []})) == "auto"  # config present, no handoff key


def test_handoff_respects_explicit_owner_gated():
    assert _handoff(_Step({"handoff": "owner_gated"})) == "owner_gated"


def test_handoff_normalizes_case():
    assert _handoff(_Step({"handoff": "AUTO"})) == "auto"
    assert _handoff(_Step({"handoff": "Owner_Gated"})) == "owner_gated"
