from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from research_data_engine.analytics import calculate_price_analytics
from research_data_engine.exceptions import DataValidationError
from research_data_engine.market_samples import load_spot_prices, parse_eia_spot, verified_manifest

DIRECTORY = Path(__file__).resolve().parents[1] / "examples" / "market_data"


def test_frozen_samples_are_complete_and_have_explicit_sources():
    manifest = verified_manifest(DIRECTORY)
    assert [sample["symbol"] for sample in manifest["samples"]] == ["NVDA", "SNDK", "WTI"]
    assert [sample["rows"] for sample in manifest["samples"]] == [216, 216, 214]
    for sample in manifest["samples"]:
        assert sample["data_kind"] == "real"
        assert sample["start"] == "2025-02-24"
        assert sample["end"] == "2025-12-31"
        assert sample["source_url"].startswith("https://")
        frame = pl.read_csv(DIRECTORY / sample["path"])
        assert frame["date"][0] == sample["start"]
        assert frame["date"][-1] == sample["end"]
    assert manifest["samples"][2]["has_volume"] is False


def test_equity_and_spot_math_agree_with_independent_references():
    for relative in ("equities/NVDA.csv", "equities/SNDK.csv", "spot/WTI.csv"):
        frame = pl.read_csv(DIRECTORY / relative, try_parse_dates=True)
        computed = calculate_price_analytics(frame.lazy()).collect()
        prices = frame["close"].to_numpy()
        assert computed["simple_return"][0] is None
        assert computed["simple_return"].slice(1).to_list() == pytest.approx(
            prices[1:] / prices[:-1] - 1
        )
        expected = np.std(np.diff(np.log(prices[-21:])), ddof=1) * np.sqrt(252)
        assert computed["realized_vol_20"][-1] == pytest.approx(expected, rel=1e-10)
        assert computed["realized_vol_20"].head(20).null_count() == 20


def test_wti_is_price_only_with_actual_source_values():
    frame = load_spot_prices(DIRECTORY / "spot" / "WTI.csv")
    assert not ({"open", "high", "low", "volume"} & set(frame.columns))
    assert frame["close"][0] == 71.06
    assert frame["date"][0] == date(2025, 2, 24)
    assert frame["simple_return"][1] == pytest.approx(69.15 / 71.06 - 1)
    assert frame["_source_row"][0] == 2


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_spot_adapter_rejects_unsupported_prices(tmp_path, value):
    path = tmp_path / "spot.csv"
    path.write_text(f"symbol,date,close,source\nWTI,2025-02-24,{value},eia_wti_spot\n")
    with pytest.raises(DataValidationError, match="positive finite"):
        load_spot_prices(path)


def test_spot_adapter_rejects_duplicate_keys_even_when_prices_differ(tmp_path):
    path = tmp_path / "spot.csv"
    path.write_text(
        "symbol,date,close,source\nWTI,2025-02-24,71,eia_wti_spot\nWTI,2025-02-24,72,eia_wti_spot\n"
    )
    with pytest.raises(DataValidationError, match="Duplicate spot observation key"):
        load_spot_prices(path)


def test_snapshot_tampering_blocks_export(tmp_path):
    import shutil

    shutil.copytree(DIRECTORY, tmp_path / "samples")
    snapshot = tmp_path / "samples" / "spot" / "WTI.csv"
    snapshot.write_text(snapshot.read_text().replace("71.06", "71.99", 1))
    with pytest.raises(DataValidationError, match="checksum mismatch"):
        verified_manifest(tmp_path / "samples")


def test_eia_blank_cells_are_absent_and_cross_year_week_is_dated_correctly():
    body = b"""<tr><td class='B6'>2024 Dec-30 to Jan- 3</td>
    <td class='B3'>1</td><td class='B3'>2</td><td class='B3'></td>
    <td class='B3'>4</td><td class='B3'>5</td></tr>
    <tr><td class='B6'>2025 Feb-24 to Feb-28</td>
    <td class='B3'>71.06</td><td class='B3'></td><td class='B3'>68.87</td>
    <td class='B3'>70.62</td><td class='B3'>69.97</td></tr>
    <tr><td class='B6'>2025 Dec-29 to Jan- 2</td>
    <td class='B3'>58</td><td class='B3'>57</td><td class='B3'>56</td>
    <td class='B3'></td><td class='B3'>55</td></tr>"""
    frame = parse_eia_spot(body)
    assert frame.height == 7
    assert date(2025, 2, 25) not in frame["date"].to_list()
    assert frame["date"][-1] == date(2025, 12, 31)
    assert frame["close"][-1] == 56
