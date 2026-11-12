import numpy as np
import pytest

from tempmarkets.buckets import parse_bucket
from tempmarkets.io.polymarket import taker_fee_per_share
from tempmarkets.market import EventSnapshot, blend, hypothetical_trade, price_at, scores


def snap(prices, winner="74-75°F", fee=0.0):
    labels = ["73°F or below", "74-75°F", "76-77°F", "78°F or higher"]
    return EventSnapshot(labels, [parse_bucket(x) for x in labels], np.array(prices, float), winner, fee)


def test_price_at_uses_last_known_and_rejects_stale():
    h = [{"t": 100, "p": 0.2}, {"t": 200, "p": 0.3}]
    assert price_at(h, 199) == 0.2 and price_at(h, 200) == 0.3
    assert price_at(h, 99) is None
    assert price_at(h, 200 + 7 * 3600) is None


def test_fee_formula_matches_docs():
    # docs: 100 shares at $0.50, rate 0.05 -> $1.25
    assert 100 * taker_fee_per_share(0.5, 0.05) == pytest.approx(1.25)


def test_scores_and_overround():
    s = snap([0.1, 0.5, 0.35, 0.1])
    assert s.overround == pytest.approx(0.05)
    assert np.isclose(s.implied.sum(), 1)
    sc = scores(s.implied, s)
    assert sc["p_winner"] == pytest.approx(0.5 / 1.05)


def test_blend_is_a_distribution_between_inputs():
    a, b = np.array([0.7, 0.2, 0.1]), np.array([0.1, 0.2, 0.7])
    for kind in ("linear", "log"):
        m = blend(a, b, 0.5, kind)
        assert np.isclose(m.sum(), 1) and m[0] == pytest.approx(m[2])


def test_hypothetical_trade_costs_and_pnl():
    s = snap([0.10, 0.40, 0.40, 0.10], winner="74-75°F", fee=0.05)
    model = np.array([0.05, 0.60, 0.30, 0.05])
    t = hypothetical_trade(model, s, threshold=0.05, half_spread=0.01)
    assert t["bucket"] == "74-75°F" and t["won"]
    shares = 1 / 0.41
    fee = shares * 0.05 * 0.41 * 0.59
    assert t["pnl"] == pytest.approx(shares - 1 - fee)
    assert hypothetical_trade(model, s, threshold=0.25) is None   # edge ~0.18 after costs


def test_best_quotes_and_paper_decision():
    from tempmarkets.paper.log import best_quotes, paper_decision
    q = best_quotes({"bids": [{"price": "0.30", "size": "10"}, {"price": "0.32", "size": "5"}],
                     "asks": [{"price": "0.36", "size": "50"}, {"price": "0.35", "size": "2"}]})
    assert q == {"bid": 0.32, "bid_size": 5.0, "ask": 0.35, "ask_size": 2.0}
    labels = ["a", "b", "c"]
    # b has the biggest edge but too little size for a $1 stake; c is taken instead.
    d = paper_decision(labels, [0.1, 0.6, 0.5], [0.1, 0.35, 0.40], [100, 2, 100], fee_rate=0.05)
    assert d["bucket"] == "c" and abs(d["edge"] - (0.5 - (0.40 + 0.05 * 0.40 * 0.60))) < 1e-12
    assert paper_decision(labels, [0.1, 0.36, 0.41], [0.1, 0.35, 0.40], [100] * 3, 0.0) is None
