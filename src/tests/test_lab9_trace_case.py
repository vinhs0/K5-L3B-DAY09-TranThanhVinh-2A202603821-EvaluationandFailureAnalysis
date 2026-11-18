"""Regression for the Lab 9 trace case: C-014@11 pre_deducted (FM-05), see docs/trace_case.md.

The buggy variant subtracts the already-refunded 30000 from the proposal (event 5 `proposal`)
and the host then deducts it again, so the ledger holds 90000 instead of 120000.
The fixed variant must emit no `proposal` event and refund exactly the label amount.
"""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def cases():
    from lab9.trace_case import investigate

    return investigate("fixed", "C-014", 11), investigate("seeded_regression", "C-014", 11)


def first_wrong_step(case):
    """1-based index of the first event whose amount differs from the quote minus nothing (own proposal)."""
    quote = next(e for e in case["trial"]["events"] if e["kind"] == "quote")["payload"]["amount_vnd"]
    for i, e in enumerate(case["trial"]["events"], 1):
        if e["kind"] == "proposal" and e["payload"]["amount_vnd"] != quote:
            return i
    return None


def test_fixed_pays_label_amount_and_never_overrides_proposal(cases):
    fixed, _ = cases
    assert fixed["trial"]["snapshot"]["refund_vnd"] == fixed["label"]["refund_vnd"] == 120000
    assert fixed["trial"]["lab8_pass"]
    assert first_wrong_step(fixed) is None


def test_pre_deducted_variant_is_caught(cases):
    _, bad = cases
    assert not bad["trial"]["lab8_pass"]
    assert bad["trial"]["snapshot"]["refund_vnd"] == 90000 != bad["label"]["refund_vnd"]
    assert first_wrong_step(bad) == 5
