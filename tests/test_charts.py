import pandas as pd
import pytest

from charts import build_bar_df, build_grouped_scatter_df, build_tag_bar_df
from constants import Col


# ---------- build_bar_df ----------

def test_build_bar_df_grouped_sums_across_sources(sample_positions):
    bar = build_bar_df(sample_positions, grouped=True)
    aapl = bar[bar[Col.TICKER] == "AAPL"]
    assert len(aapl) == 1
    assert aapl["Value"].iloc[0] == pytest.approx(169.5 + 84.75)


def test_build_bar_df_grouped_has_required_columns(sample_positions):
    bar = build_bar_df(sample_positions, grouped=True)
    assert {"Label", Col.SOURCE, "Value"}.issubset(bar.columns)
    assert bar[Col.SOURCE].isna().all()  # source is None when grouped


def test_build_bar_df_ungrouped_labels_include_source(sample_positions):
    bar = build_bar_df(sample_positions, grouped=False)
    assert "AAPL (UBS)" in bar["Label"].tolist()
    assert "AAPL (401K)" in bar["Label"].tolist()


def test_build_bar_df_return_mode_uses_pct(sample_positions):
    bar = build_bar_df(sample_positions, grouped=True, return_mode=True)
    aapl = bar[bar[Col.TICKER] == "AAPL"]
    # Aggregated AAPL: PnL=254.25, SOD=15000 → Value=254.25/15000
    assert aapl["Value"].iloc[0] == pytest.approx(254.25 / 15000)


def test_build_bar_df_sort_by_value(sample_positions):
    bar = build_bar_df(sample_positions, grouped=True, sort_by_name=False)
    # Sorted by |Value| ascending — last entry has largest magnitude
    assert abs(bar["Value"].iloc[-1]) >= abs(bar["Value"].iloc[0])


def test_build_bar_df_sort_by_name(sample_positions):
    bar = build_bar_df(sample_positions, grouped=True, sort_by_name=True)
    labels = bar["Label"].tolist()
    assert labels == sorted(labels, reverse=True)


# ---------- build_grouped_scatter_df ----------

def test_build_grouped_scatter_df_sources_string(sample_positions):
    scatter = build_grouped_scatter_df(sample_positions)
    aapl = scatter[scatter[Col.TICKER] == "AAPL"].iloc[0]
    assert aapl["Sources"] == "401K, UBS"  # sorted unique


def test_build_grouped_scatter_df_return_is_pnl_over_sod(sample_positions):
    scatter = build_grouped_scatter_df(sample_positions)
    aapl = scatter[scatter[Col.TICKER] == "AAPL"].iloc[0]
    assert aapl["Return"] == pytest.approx((169.5 + 84.75) / 15000)


def test_build_grouped_scatter_df_single_source(sample_positions):
    scatter = build_grouped_scatter_df(sample_positions)
    msft = scatter[scatter[Col.TICKER] == "MSFT"].iloc[0]
    assert msft["Sources"] == "UBS"


# ---------- build_tag_bar_df ----------

def test_build_tag_bar_df_groups_by_tag(sample_positions):
    tag = build_tag_bar_df(sample_positions)
    tech = tag[tag[Col.TAG] == "Tech"].iloc[0]
    # Tech: AAPL+AAPL+MSFT = 169.5 + 84.75 + 200.0 = 454.25
    assert tech["Value"] == pytest.approx(454.25)


def test_build_tag_bar_df_has_label_value(sample_positions):
    tag = build_tag_bar_df(sample_positions)
    assert "Label" in tag.columns
    assert "Value" in tag.columns
    assert set(tag[Col.TAG]) == {"Tech", "Semis"}


def test_build_tag_bar_df_sort_by_name(sample_positions):
    tag = build_tag_bar_df(sample_positions, sort_by_name=True)
    labels = tag["Label"].tolist()
    assert labels == sorted(labels, reverse=True)
