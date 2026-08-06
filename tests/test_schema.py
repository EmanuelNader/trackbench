"""Schema helper unit tests."""

from ingest.schema import (
    DETECTION_KEYS,
    GT_BOX_KEYS,
    is_valid_detection,
    validate_detection,
)


def _det(**overrides):
    base = {
        "cls": "car",
        "x": 1.0,
        "y": 2.0,
        "z": 0.0,
        "l": 4.5,
        "w": 1.8,
        "h": 1.5,
        "yaw": 0.1,
        "score": 0.9,
    }
    base.update(overrides)
    return base


def test_validate_detection_ok():
    assert validate_detection(_det()) == []
    assert is_valid_detection(_det())


def test_validate_detection_missing_key():
    d = _det()
    del d["yaw"]
    errs = validate_detection(d)
    assert any("yaw" in e for e in errs)
    assert not is_valid_detection(d)


def test_validate_gt_fields():
    d = _det(id="inst-1", visibility=3)
    assert validate_detection(d, require_gt_fields=True) == []
    assert is_valid_detection(d, require_gt_fields=True)

    bad = _det(id="inst-1", visibility=9)
    errs = validate_detection(bad, require_gt_fields=True)
    assert any("visibility" in e for e in errs)


def test_gt_requires_id():
    d = _det(visibility=2)
    errs = validate_detection(d, require_gt_fields=True)
    assert any("id" in e for e in errs)


def test_key_tuples_cover_expected_fields():
    assert "cls" in DETECTION_KEYS
    assert "score" in DETECTION_KEYS
    assert "id" in GT_BOX_KEYS
    assert "visibility" in GT_BOX_KEYS
