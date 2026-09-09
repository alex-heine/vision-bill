"""Fixture discovery — pure filesystem logic, no stack required."""

import json
from pathlib import Path

from e2e import discovery

VALID_RECEIPT = {
    "confidence": 95,
    "merchant_name": "Fixture Shop",
    "date": "2026-01-02",
    "line_items": [
        {"description": "Widget", "quantity": 2.0, "unit_price": "3.00", "total_price": "6.00"}
    ],
    "subtotal": "6.00",
    "tax_total": "0",
    "total": "6.00",
    "payment_method": "cash",
}


def _write_pair(data_dir: Path, name: str, receipt: dict) -> Path:
    (data_dir / f"{name}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + name.encode())
    (data_dir / f"{name}.json").write_text(json.dumps(receipt), encoding="utf-8")
    return data_dir / f"{name}.png"


def test_load_fixture_cases_reads_valid_pairs(tmp_path: Path) -> None:
    _write_pair(tmp_path, "alpha", VALID_RECEIPT)
    (tmp_path / "fixtures.toml").write_text('fixtures = ["alpha", "missing"]\n')

    cases = discovery.load_fixture_cases(tmp_path)

    assert [c.name for c in cases] == ["alpha"]
    assert cases[0].image_path.name == "alpha.png"
    assert cases[0].expected_receipt.merchant_name == "Fixture Shop"


def test_load_fixture_cases_skips_invalid_json(tmp_path: Path) -> None:
    _write_pair(tmp_path, "good", VALID_RECEIPT)
    (tmp_path / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "broken.json").write_text('{"merchant_name": "x", oops')
    (tmp_path / "fixtures.toml").write_text('fixtures = ["good", "broken"]\n')

    cases = discovery.load_fixture_cases(tmp_path)
    assert [c.name for c in cases] == ["good"]


def test_load_fixture_cases_skips_unparseable_receipt(tmp_path: Path) -> None:
    # A valid JSON object that is NOT a valid Receipt (e.g. the stale user-creation format).
    _write_pair(tmp_path, "stale", {"endpoint": "/users", "expected_status": 201})
    cases = discovery.load_fixture_cases(tmp_path)
    assert cases == []


def test_load_fixture_cases_skips_missing_image(tmp_path: Path) -> None:
    (tmp_path / "noimg.json").write_text(json.dumps(VALID_RECEIPT))
    assert discovery.load_fixture_cases(tmp_path) == []


def test_load_fixture_cases_no_manifest(tmp_path: Path) -> None:
    assert discovery.load_fixture_cases(tmp_path) == []


def test_first_case_returns_first_or_none(tmp_path: Path) -> None:
    assert discovery.first_case(tmp_path) is None
    _write_pair(tmp_path, "alpha", VALID_RECEIPT)
    (tmp_path / "fixtures.toml").write_text('fixtures = ["alpha"]\n')
    assert discovery.first_case(tmp_path) is not None
