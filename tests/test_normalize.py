import pandas as pd

from draft_data.normalize.ids import match_names, norm_name, norm_team
from draft_data.normalize.scoring import add_point_columns


def test_norm_name():
    assert norm_name("Ja'Marr Chase") == "jamarr chase"
    assert norm_name("Marvin Harrison Jr.") == "marvin harrison"
    assert norm_name("Kenneth Gainwell") == norm_name("Kenny Gainwell")
    assert norm_name("Amon-Ra St. Brown") == "amonra st brown"


def test_norm_team_aliases():
    assert norm_team("JAC") == "JAX"
    assert norm_team("SFO") == "SF"
    assert norm_team(None) is None


def _master():
    return pd.DataFrame({
        "player_id": ["00-0001", "00-0002", "00-0003", "DST_BAL"],
        "name": ["Zay Flowers", "Chase Brown", "Chase Brown", "Ravens D/ST"],
        "position": ["WR", "RB", "RB", "DST"],
        "team": ["BAL", "CIN", "LV", "BAL"],
        "status": ["ACT", "ACT", "CUT", "ACT"],
    })


def test_exact_match_and_team_tiebreak():
    df = pd.DataFrame({"name": ["Zay Flowers", "Chase Brown"],
                       "position": ["WR", "RB"], "team": ["BAL", "CIN"]})
    review = []
    got = match_names(df, _master(), "test", review)
    assert list(got) == ["00-0001", "00-0002"]
    assert review == []


def test_dst_matches_by_team_name():
    df = pd.DataFrame({"name": ["Baltimore Ravens"], "position": ["DST"], "team": [None]})
    got = match_names(df, _master(), "test", [])
    assert list(got) == ["DST_BAL"]


def test_fuzzy_goes_to_review_never_silent():
    df = pd.DataFrame({"name": ["Zay Flower"], "position": ["WR"], "team": ["BAL"]})
    review = []
    got = match_names(df, _master(), "test", review)
    assert list(got) == ["00-0001"]
    assert len(review) == 1 and review[0]["score"] > 0


def test_scoring_variants():
    df = pd.DataFrame([{
        "g": 10, "pass_yards": 0, "pass_int": 0, "rush_yards": 100, "rec_yards": 100,
        "rush_td": 1, "rec_td": 1, "two_pt": 0, "fumbles_lost": 1, "receptions": 10,
        "pass_td": 2, "pass_att": 3,
    }])
    out = add_point_columns(df.copy())
    # base: 20 yds pts + 12 td - 2 fumble = 30; +2 pass td at 4/6; receptions vary
    assert out.loc[0, "pts_2025_std_pass4"] == 38.0
    assert out.loc[0, "pts_2025_std_pass6"] == 42.0
    assert out.loc[0, "pts_2025_ppr_pass4"] == 48.0
    assert out.loc[0, "pts_2025_half_pass4"] == 43.0
    assert out.loc[0, "ppg_2025_ppr_pass4"] == 4.8
