"""Legacy psychro stage CTA helpers still work via app.stage_cta aliases."""

from __future__ import annotations

from app.psychro_stage_cta import (
    COUNT_KEY,
    STAGE_THRESHOLD,
    psychro_single_calc_count,
)


PUBLIC = "/tools/psychrometric-calculator"

VALID = {
    "action": "calculate",
    "s_t": "21",
    "s_prop": "rh",
    "s_val": "50",
    "altitude": "0",
}


def test_legacy_count_key_still_updated(app):
    client = app.test_client()
    for n in range(1, STAGE_THRESHOLD + 1):
        client.post(PUBLIC, data=VALID, follow_redirects=True)
        with client.session_transaction() as sess:
            assert sess.get(COUNT_KEY) == n
            assert sess.get("stage_cta_count:psychrometric_single") == n


def test_helpers_default_outside_request(app):
    assert psychro_single_calc_count() == 0
