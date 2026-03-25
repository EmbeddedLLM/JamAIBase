"""Unit tests for quota threshold notification logic (pure functions, no DB)."""

import pytest

from jamaibase.types import ProductType
from owl.utils.notifications import check_quota_thresholds

QUOTA_ALERT_THRESHOLDS = (50, 80, 99, 100)


def _check_quota_thresholds(
    *,
    old_usage: float,
    new_usage: float,
    quota: float | None,
    product_type: ProductType,
) -> list[dict]:
    results = []
    intents = check_quota_thresholds(
        organization_id="test_org",
        old_usage=old_usage,
        new_usage=new_usage,
        quota=quota,
        product_type=product_type,
        quota_alert_thresholds=QUOTA_ALERT_THRESHOLDS,
    )
    for intent in intents:
        results.append(
            dict(
                event_type=intent.event_type,
                threshold=intent.meta["threshold"],
                usage=intent.meta["usage"],
                quota=intent.meta["quota"],
                unit=intent.meta["unit"],
            )
        )
    return results


class TestCheckQuotaThresholds:
    @pytest.mark.parametrize(
        "old_usage,new_usage,expected_thresholds",
        [
            pytest.param(0.1, 0.2, [], id="no_crossing"),
            pytest.param(0.4, 0.55, [50], id="single_crossing"),
            pytest.param(0.4, 0.85, [50, 80], id="multiple_crossings"),
            pytest.param(0.0, 1.0, [50, 80, 99, 100], id="all_crossings"),
            pytest.param(0.0, 0.5, [50], id="exact_boundary"),
            pytest.param(0.55, 0.60, [], id="already_past"),
            pytest.param(0.95, 1.2, [99, 100], id="over_100_percent"),
        ],
    )
    def test_threshold_crossings(self, old_usage, new_usage, expected_thresholds):
        results = _check_quota_thresholds(
            old_usage=old_usage,
            new_usage=new_usage,
            quota=1.0,
            product_type=ProductType.LLM_TOKENS,
        )
        assert [r["threshold"] for r in results] == expected_thresholds

    def test_unlimited_quota_no_alert(self):
        results = _check_quota_thresholds(
            old_usage=100.0, new_usage=200.0, quota=None, product_type=ProductType.LLM_TOKENS
        )
        assert results == []

    def test_zero_quota_no_alert(self):
        results = _check_quota_thresholds(
            old_usage=0.0, new_usage=1.0, quota=0.0, product_type=ProductType.LLM_TOKENS
        )
        assert results == []
