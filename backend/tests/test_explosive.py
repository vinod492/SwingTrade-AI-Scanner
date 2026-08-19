from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.services.explosive import iv_rank_percentile, score_explosive

NOW = datetime(2026, 8, 19, 15, 0, tzinfo=timezone.utc)


@dataclass
class FakeCatalyst:
    ticker: str
    kind: str
    headline: str = ""
    sentiment: float | None = None
    event_date: datetime | None = None
    verified: bool = False


def trial_in(days: int, kind: str = "trial_readout", verified: bool = False) -> list[FakeCatalyst]:
    return [FakeCatalyst(ticker="X", kind=kind, headline="readout",
                         event_date=NOW + timedelta(days=days), verified=verified)]


def score(catalysts=(), short_pct_float=None, days_to_cover=None, iv_rank=None,
          iv_rising=False, float_shares=None, rel_volume=None, rel_volume_trend_up=False):
    return score_explosive(list(catalysts), short_pct_float, days_to_cover, iv_rank,
                           iv_rising, float_shares, rel_volume, rel_volume_trend_up, now=NOW)


class TestCatalystProximity:
    def test_no_catalyst_scores_zero_catalyst_points(self):
        bd = score()
        assert bd.catalyst == 0
        assert bd.catalyst_kind == ""
        assert bd.days_to_catalyst is None

    def test_imminent_catalyst_scores_max(self):
        bd = score(trial_in(2))
        assert bd.catalyst == 30
        assert bd.days_to_catalyst == 2
        assert bd.catalyst_kind == "trial_readout"

    def test_distant_catalyst_scores_less(self):
        near = score(trial_in(5))
        far = score(trial_in(40))
        assert near.catalyst > far.catalyst > 0

    def test_catalyst_beyond_lookahead_ignored(self):
        assert score(trial_in(60)).catalyst == 0

    def test_past_catalyst_ignored(self):
        assert score(trial_in(-1)).catalyst == 0

    def test_analyst_upgrade_is_not_a_binary_catalyst(self):
        cats = [FakeCatalyst(ticker="X", kind="upgrade", event_date=NOW + timedelta(days=1))]
        assert score(cats).catalyst == 0

    def test_fda_decision_counts_as_binary(self):
        bd = score(trial_in(3, "fda_decision"))
        assert bd.catalyst == 30
        assert bd.catalyst_kind == "fda_decision"

    def test_nearest_of_multiple_events_wins(self):
        cats = trial_in(20) + trial_in(4, "fda_decision")
        bd = score(cats)
        assert bd.days_to_catalyst == 4
        assert bd.catalyst_kind == "fda_decision"

    def test_unverified_catalyst_flagged_unverified(self):
        bd = score(trial_in(2, verified=False))
        assert bd.catalyst_verified is False
        assert any("unconfirmed" in r.lower() for r in bd.reasons)

    def test_verified_catalyst_flagged_verified(self):
        bd = score(trial_in(2, "earnings", verified=True))
        assert bd.catalyst_verified is True
        assert any("confirmed date" in r.lower() and "unconfirmed" not in r.lower()
                   for r in bd.reasons)

    def test_no_catalyst_is_not_verified(self):
        assert score().catalyst_verified is False


class TestSqueezeSetup:
    def test_no_short_interest_scores_zero(self):
        assert score().squeeze == 0

    def test_heavily_shorted_scores_more_than_light(self):
        heavy = score(short_pct_float=35, days_to_cover=3)
        light = score(short_pct_float=12, days_to_cover=3)
        assert heavy.squeeze > light.squeeze > 0

    def test_very_light_short_interest_scores_zero(self):
        assert score(short_pct_float=3, days_to_cover=3).squeeze == 0

    def test_days_to_cover_bonus_requires_meaningful_short_interest(self):
        with_dtc = score(short_pct_float=15, days_to_cover=8)
        without_dtc = score(short_pct_float=15, days_to_cover=1)
        assert with_dtc.squeeze > without_dtc.squeeze

    def test_squeeze_capped_at_25(self):
        assert score(short_pct_float=45, days_to_cover=10).squeeze <= 25


class TestFloatAmplifier:
    def test_small_float_scores_max(self):
        assert score(float_shares=20e6).float_amp == 15

    def test_large_float_scores_zero(self):
        assert score(float_shares=500e6).float_amp == 0

    def test_unknown_float_scores_zero(self):
        assert score().float_amp == 0


class TestIvAndVolume:
    def test_high_iv_rank_scores_more_than_low(self):
        high = score(iv_rank=90)
        low = score(iv_rank=10)
        assert high.iv > low.iv > 0

    def test_iv_rising_adds_points(self):
        rising = score(iv_rank=50, iv_rising=True)
        flat = score(iv_rank=50, iv_rising=False)
        assert rising.iv > flat.iv

    def test_iv_capped_at_20(self):
        assert score(iv_rank=100, iv_rising=True).iv <= 20

    def test_volume_build_and_relvol_both_contribute(self):
        both = score(rel_volume=3.0, rel_volume_trend_up=True)
        neither = score(rel_volume=0.8, rel_volume_trend_up=False)
        assert both.volume == 10
        assert neither.volume == 0


class TestCombinedScore:
    def test_perfect_setup_hits_100(self):
        bd = score(trial_in(1), short_pct_float=40, days_to_cover=10, iv_rank=100,
                   iv_rising=True, float_shares=15e6, rel_volume=4.0,
                   rel_volume_trend_up=True)
        assert bd.total == 100

    def test_reasons_populated_for_flagged_setup(self):
        bd = score(trial_in(2), short_pct_float=25, days_to_cover=6, iv_rank=80,
                  iv_rising=True, float_shares=20e6, rel_volume=2.0,
                  rel_volume_trend_up=True)
        assert len(bd.reasons) >= 4
        assert any("readout" in r.lower() for r in bd.reasons)


class TestIvRankPercentile:
    def test_needs_minimum_history(self):
        assert iv_rank_percentile([0.3, 0.4], 0.5) is None

    def test_top_of_range_is_100(self):
        history = [0.2, 0.3, 0.4, 0.5, 0.6]
        assert iv_rank_percentile(history, 0.6) == 100.0

    def test_bottom_of_range_is_low(self):
        history = [0.2, 0.3, 0.4, 0.5, 0.6]
        assert iv_rank_percentile(history, 0.1) < 30

    def test_none_latest_returns_none(self):
        assert iv_rank_percentile([0.2, 0.3, 0.4, 0.5, 0.6], None) is None
