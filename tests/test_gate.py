from eval.gate import check_gate


BASE = {
    "metrics": {"mota": 0.9, "ids": 0, "motp": 0.05, "fp": 0, "fn": 4, "frag": 0},
    "gates": {"mota_max_drop": 0.5, "ids_max_increase": 0, "p99_max_regression_ratio": 0.2},
    "latency": {"p99_ms": 1.0},
}


def test_gate_passes_on_equal():
    ok, _ = check_gate({"mota": 0.9, "ids": 0.0}, BASE)
    assert ok


def test_gate_fails_mota_drop():
    ok, msgs = check_gate({"mota": 0.3, "ids": 0.0}, BASE)
    assert not ok
    assert any("MOTA dropped" in m for m in msgs)


def test_gate_fails_ids_increase():
    ok, msgs = check_gate({"mota": 0.9, "ids": 1.0}, BASE)
    assert not ok
    assert any("IDS increased" in m for m in msgs)


def test_gate_fails_p99_regression():
    ok, msgs = check_gate(
        {"mota": 0.9, "ids": 0.0, "latency_p99_ms": 1.5},
        BASE,
    )
    assert not ok
    assert any("p99" in m for m in msgs)
