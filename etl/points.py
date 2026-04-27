from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    id: str
    name: str
    region: str
    lat: float
    lon: float
    elevation_m: int
    timezone: str


POINTS: list[Point] = [
    # Santa Clara County, CA — South Bay suburbs
    Point("san_jose",       "San Jose",        "santa_clara_ca",   37.3382, -121.8863,  25, "America/Los_Angeles"),
    Point("palo_alto",      "Palo Alto",       "santa_clara_ca",   37.4419, -122.1430,   9, "America/Los_Angeles"),
    Point("morgan_hill",    "Morgan Hill",     "santa_clara_ca",   37.1305, -121.6544, 108, "America/Los_Angeles"),
    # Eastside King County, WA — Seattle suburbs east of the lake
    Point("bellevue",       "Bellevue",        "eastside_king_wa", 47.6101, -122.2015,  37, "America/Los_Angeles"),
    Point("redmond",        "Redmond",         "eastside_king_wa", 47.6740, -122.1215,  22, "America/Los_Angeles"),
    Point("woodinville",    "Woodinville",     "eastside_king_wa", 47.7540, -122.1635,  46, "America/Los_Angeles"),
    # San Francisco, CA — three distinct microclimates (foggy west vs sunny east)
    Point("mission_sf",     "Mission Dist.",   "san_francisco_ca", 37.7599, -122.4148,  30, "America/Los_Angeles"),
    Point("pacific_hts_sf", "Pacific Heights", "san_francisco_ca", 37.7923, -122.4326,  90, "America/Los_Angeles"),
    Point("ocean_beach_sf", "Ocean Beach",     "san_francisco_ca", 37.7594, -122.5107,  10, "America/Los_Angeles"),
    # Snohomish County, WA — Puget Sound north of Seattle
    Point("everett",        "Everett",         "snohomish_wa",     47.9790, -122.2021,  18, "America/Los_Angeles"),
    Point("mill_creek",     "Mill Creek",      "snohomish_wa",     47.8601, -122.2043, 140, "America/Los_Angeles"),
    Point("edmonds",        "Edmonds",         "snohomish_wa",     47.8107, -122.3775,  17, "America/Los_Angeles"),
    # Charlotte County, FL — Gulf Coast, Punta Gorda area
    Point("punta_gorda",    "Punta Gorda",     "charlotte_fl",     26.9298,  -82.0454,   3, "America/New_York"),
    Point("port_charlotte", "Port Charlotte",  "charlotte_fl",     26.9762,  -82.0907,   3, "America/New_York"),
    Point("englewood_fl",   "Englewood",       "charlotte_fl",     26.9617,  -82.3528,   3, "America/New_York"),
    # Albemarle County, VA — Blue Ridge foothills, contains Charlottesville
    Point("charlottesville","Charlottesville", "albemarle_va",     38.0293,  -78.4767, 177, "America/New_York"),
    Point("crozet",         "Crozet",          "albemarle_va",     38.0718,  -78.6961, 180, "America/New_York"),
    Point("earlysville",    "Earlysville",     "albemarle_va",     38.1251,  -78.5003, 167, "America/New_York"),
    # Westchester County, NY — affluent NYC suburb along the Hudson
    Point("white_plains",   "White Plains",    "westchester_ny",   41.0340,  -73.7629,  75, "America/New_York"),
    Point("scarsdale",      "Scarsdale",       "westchester_ny",   40.9890,  -73.7807,  92, "America/New_York"),
    Point("yonkers",        "Yonkers",         "westchester_ny",   40.9312,  -73.8987,  10, "America/New_York"),
    # Maui County, HI — tropical, three distinct shores (central / south-sunny / west)
    Point("kahului",        "Kahului",         "maui_hi",          20.8893, -156.4729,   8, "Pacific/Honolulu"),
    Point("kihei",          "Kihei",           "maui_hi",          20.7644, -156.4456,   9, "Pacific/Honolulu"),
    Point("lahaina",        "Lahaina",         "maui_hi",          20.8783, -156.6825,   9, "Pacific/Honolulu"),
    # St. Johns County, FL — Atlantic coast north of Daytona, contains St. Augustine
    Point("st_augustine",   "St. Augustine",   "st_johns_fl",      29.9012,  -81.3124,   3, "America/New_York"),
    Point("ponte_vedra",    "Ponte Vedra Bch", "st_johns_fl",      30.2394,  -81.3856,   3, "America/New_York"),
    Point("st_johns_town",  "St. Johns",       "st_johns_fl",      30.1372,  -81.5350,   9, "America/New_York"),
    # Sofia, Bulgaria — capital city, single point at the center
    Point("sofia_center",   "Sofia (center)",  "sofia_bg",         42.6977,   23.3219, 550, "Europe/Sofia"),
    # Gabrovo, Bulgaria — central Balkan town, single point at the center
    Point("gabrovo_center", "Gabrovo (center)","gabrovo_bg",       42.8742,   25.3194, 370, "Europe/Sofia"),
    # Miami-Dade County, FL — distinct microclimates: urban core, oceanfront, inland suburb
    Point("miami_downtown", "Miami (downtown)", "miami_dade_fl",    25.7617,  -80.1918,   2, "America/New_York"),
    Point("miami_beach",    "Miami Beach",      "miami_dade_fl",    25.7907,  -80.1300,   1, "America/New_York"),
    Point("coral_gables",   "Coral Gables",     "miami_dade_fl",    25.7215,  -80.2684,   3, "America/New_York"),
]


# Region registry — friendly labels + colors + display order.
# Palette chosen for colorblind safety (Wong palette).
REGIONS: dict[str, dict] = {
    "santa_clara_ca":   {"label": "Santa Clara County, CA",   "short": "SCC", "color": "#e45c3a", "ink": "#b43f21", "default_on": True},
    "eastside_king_wa": {"label": "Eastside King County, WA", "short": "WA",  "color": "#0e8f74", "ink": "#096a56", "default_on": True},
    "san_francisco_ca": {"label": "San Francisco, CA",        "short": "SF",  "color": "#8e54c4", "ink": "#6d2d85", "default_on": False},
    "snohomish_wa":     {"label": "Snohomish County, WA",     "short": "SNO", "color": "#cc8a1a", "ink": "#8a5b0e", "default_on": False},
    "charlotte_fl":     {"label": "Charlotte County, FL",     "short": "FL",  "color": "#ec4899", "ink": "#a12553", "default_on": False},
    "albemarle_va":     {"label": "Albemarle County, VA",     "short": "VA",  "color": "#16a34a", "ink": "#0f6d31", "default_on": False},
    "westchester_ny":   {"label": "Westchester County, NY",   "short": "NY",  "color": "#3b82f6", "ink": "#1d4ed8", "default_on": False},
    "maui_hi":          {"label": "Maui County, HI",           "short": "HI",  "color": "#06b6d4", "ink": "#0e7490", "default_on": False},
    "st_johns_fl":      {"label": "St. Johns County, FL",       "short": "STA", "color": "#f59e0b", "ink": "#a26508", "default_on": False},
    "sofia_bg":         {"label": "Sofia, Bulgaria",            "short": "SOF", "color": "#64748b", "ink": "#334155", "default_on": False},
    "miami_dade_fl":    {"label": "Miami-Dade County, FL",       "short": "MIA", "color": "#14b8a6", "ink": "#0f766e", "default_on": False},
    "gabrovo_bg":       {"label": "Gabrovo, Bulgaria",            "short": "GAB", "color": "#a16207", "ink": "#713f12", "default_on": False},
}


def by_id(point_id: str) -> Point:
    for p in POINTS:
        if p.id == point_id:
            return p
    raise KeyError(point_id)
