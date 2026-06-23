"""Unit tests for BKT engine helpers."""

import math

import pytest

from app.services.bkt_engine import _bkt_update


def test_bkt_update_increases_on_correct():
    p_l = _bkt_update(0.3, True, p_g=0.2, p_s=0.1)
    assert p_l > 0.3
    assert 0.0 <= p_l <= 1.0


def test_bkt_update_decreases_on_incorrect():
    p_l = _bkt_update(0.8, False, p_g=0.2, p_s=0.1)
    assert p_l < 0.8
    assert 0.0 <= p_l <= 1.0


def test_bkt_update_outputs_are_clamped_to_unit_interval():
    assert 0.0 <= _bkt_update(0.99, True, p_g=0.0, p_s=0.0) <= 1.0
    assert 0.0 <= _bkt_update(0.01, False, p_g=1.0, p_s=0.0) <= 1.0


def test_bkt_update_invalid_probabilities_raises():
    with pytest.raises(ValueError):
        _bkt_update(1.5, True, p_g=0.2, p_s=0.1)
    with pytest.raises(ValueError):
        _bkt_update(0.5, True, p_g=-0.1, p_s=0.1)
    with pytest.raises(ValueError):
        _bkt_update(0.5, True, p_g=0.2, p_s=1.2)


def test_bkt_update_is_deterministic():
    a = _bkt_update(0.5, True, p_g=0.2, p_s=0.1)
    b = _bkt_update(0.5, True, p_g=0.2, p_s=0.1)
    assert math.isclose(a, b)
