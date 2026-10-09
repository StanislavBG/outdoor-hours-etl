import pytest
import yaml

from etl.points import POINTS, REGIONS, by_id, load_registry

ORIGINAL_ORDER = [
    "santa_clara_ca", "eastside_king_wa", "san_francisco_ca", "snohomish_wa",
    "charlotte_fl", "albemarle_va", "westchester_ny", "maui_hi", "st_johns_fl",
    "sofia_bg", "miami_dade_fl", "gabrovo_bg",
]


def _region(points):
    return {"label": "L", "short": "S", "color": "#000000", "ink": "#111111",
            "default_on": False, "description": "d", "points": points}


def _pt(**over):
    p = {"id": "a", "name": "A", "lat": 1.0, "lon": 2.0, "elevation_m": 3,
         "timezone": "UTC"}
    p.update(over)
    return p


def _write(tmp_path, regions):
    f = tmp_path / "regions.yaml"
    f.write_text(yaml.safe_dump({"regions": regions}, sort_keys=False))
    return f


def test_counts():
    assert len(POINTS) == 32
    assert len(REGIONS) == 12


def test_region_order_and_keys():
    assert list(REGIONS) == ORIGINAL_ORDER
    for r in REGIONS.values():
        assert set(r) == {"label", "short", "color", "ink", "default_on"}


def test_miami_beach():
    p = by_id("miami_beach")
    assert (p.lat, p.lon, p.timezone) == (25.7907, -80.1300, "America/New_York")
    assert p.region == "miami_dade_fl"


def test_by_id_unknown():
    with pytest.raises(KeyError):
        by_id("nope")


def test_duplicate_point_id(tmp_path):
    f = _write(tmp_path, {"r1": _region([_pt(), _pt()])})
    with pytest.raises(ValueError, match="duplicate point id"):
        load_registry(f)


def test_duplicate_point_id_across_regions(tmp_path):
    f = _write(tmp_path, {"r1": _region([_pt()]), "r2": _region([_pt()])})
    with pytest.raises(ValueError, match="duplicate point id"):
        load_registry(f)


def test_duplicate_region_id(tmp_path):
    f = tmp_path / "regions.yaml"
    f.write_text(
        "regions:\n  r1:\n    label: L\n    points: []\n  r1:\n    label: L\n    points: []\n"
    )
    with pytest.raises(ValueError, match="duplicate region id"):
        load_registry(f)


def test_missing_field(tmp_path):
    bad = _pt()
    del bad["timezone"]
    f = _write(tmp_path, {"r1": _region([bad])})
    with pytest.raises(ValueError, match="timezone"):
        load_registry(f)


@pytest.mark.parametrize("over", [{"lat": 90.5}, {"lat": -91}, {"lon": 180.1}, {"lon": -181}])
def test_out_of_range(tmp_path, over):
    f = _write(tmp_path, {"r1": _region([_pt(**over)])})
    with pytest.raises(ValueError, match="out of range"):
        load_registry(f)
