# Data dictionary — hourly weather comparison

**Source:** open_meteo_era5  
**Endpoint:** https://archive-api.open-meteo.com/v1/archive  
**Reanalysis:** ERA5 (with ERA5T for the most recent ~5 days)  
**Grid resolution:** ~10 km  
**Temporal resolution:** hourly

## Table: `data/curated/hourly_<tag>.parquet`

One row per (point, hour). Grain: hour beginning at `ts_utc`.

### Columns

| column | type | axis | unit | description |
|---|---|---|---|---|
| `region` | `VARCHAR` | meta |  | County region id (santa_clara_ca | eastside_king_wa) |
| `point` | `VARCHAR` | meta |  | Point id (san_jose, palo_alto, morgan_hill, bellevue, redmond, woodinville) |
| `ts_utc` | `TIMESTAMP WITH TIME ZONE` | meta |  | Start of hour, UTC |
| `ts_local` | `TIMESTAMP WITH TIME ZONE` | meta |  | Start of hour, America/Los_Angeles |
| `year` | `SMALLINT` | meta |  | Local year |
| `month` | `TINYINT` | meta |  | Local month (1-12) |
| `day` | `TINYINT` | meta |  | Local day-of-month |
| `hour_of_day` | `TINYINT` | meta |  | Local hour (0-23) |
| `dow` | `TINYINT` | meta |  | Day of week (Mon=0) |
| `temperature_2m` | `DOUBLE` | temp | °C | Air temperature at 2 m above ground |
| `apparent_temperature` | `DOUBLE` | temp | °C | Perceived feels-like temperature (wind chill / heat index blend) |
| `dew_point_2m` | `DOUBLE` | temp | °C | Dew point at 2 m — moisture content |
| `relative_humidity_2m` | `BIGINT` | temp | % | Relative humidity at 2 m |
| `precipitation` | `DOUBLE` | rain | mm | Total precipitation (rain + snow water equivalent) for the preceding hour |
| `rain` | `DOUBLE` | rain | mm | Liquid rainfall for the preceding hour |
| `snowfall` | `DOUBLE` | rain | cm | Snowfall for the preceding hour |
| `snow_depth` | `DOUBLE` | rain | m | Snow depth on the ground |
| `pressure_msl` | `DOUBLE` | other | hPa | Mean-sea-level pressure |
| `surface_pressure` | `DOUBLE` | other | hPa | Surface pressure |
| `cloud_cover` | `BIGINT` | sun | % | Total cloud cover |
| `cloud_cover_low` | `BIGINT` | sun | % | Low-altitude cloud cover (< 3 km) |
| `cloud_cover_mid` | `BIGINT` | sun | % | Mid-altitude cloud cover (3–8 km) |
| `cloud_cover_high` | `BIGINT` | sun | % | High-altitude cloud cover (> 8 km) |
| `shortwave_radiation` | `DOUBLE` | sun | W/m² | Global horizontal irradiance — total solar energy reaching surface |
| `direct_radiation` | `DOUBLE` | sun | W/m² | Direct beam solar irradiance on horizontal surface |
| `diffuse_radiation` | `DOUBLE` | sun | W/m² | Diffuse (scattered) solar irradiance |
| `direct_normal_irradiance` | `DOUBLE` | sun | W/m² | Direct beam solar irradiance on a surface normal to the sun |
| `sunshine_duration` | `DOUBLE` | sun | s | Seconds of sunshine within the hour (direct radiation ≥ 120 W/m²) |
| `wind_speed_10m` | `DOUBLE` | wind | m/s | Wind speed at 10 m |
| `wind_speed_100m` | `DOUBLE` | wind | m/s | Wind speed at 100 m (upper boundary layer) |
| `wind_direction_10m` | `BIGINT` | wind | ° | Wind direction at 10 m (meteorological convention, 0° = from north) |
| `wind_direction_100m` | `BIGINT` | wind | ° | Wind direction at 100 m |
| `wind_gusts_10m` | `DOUBLE` | wind | m/s | Maximum wind gust at 10 m during the hour |
| `et0_fao_evapotranspiration` | `DOUBLE` | other | mm | FAO reference evapotranspiration — proxy for atmospheric drying power |
| `vapour_pressure_deficit` | `DOUBLE` | other | kPa | Vapour pressure deficit — how "thirsty" the air is |
| `weather_code` | `BIGINT` | other | WMO | WMO weather code (0 clear, 1-3 partly cloudy, 45/48 fog, 51-67 rain, 71-77 snow, 80-82 showers, 95-99 thunderstorms) |
| `is_day` | `BIGINT` | sun | 0/1 | Daylight flag (1 = sun above horizon) |
| `lat` | `DOUBLE` | meta |  | Point latitude (degrees) |
| `lon` | `DOUBLE` | meta |  | Point longitude (degrees) |
| `elevation_m` | `BIGINT` | meta |  | Point elevation (meters, approximate) |
| `uv_index_est` | `DOUBLE` | uv | index | Estimated UV index derived from shortwave_radiation and solar geometry. Approximation: uv_index ≈ clip((direct_normal_irradiance / 1000) * sin(altitude) * clear_sky_factor * 11, 0, 14). ERA5 does not publish UV; this is a best-effort proxy — revisit with OpenUV or NOAA Brewer data if we need higher fidelity. |

### Axes

The five comparison axes that feed the weighted scoring formula:

| axis | variables |
|---|---|
| **temp** | temperature_2m, apparent_temperature, dew_point_2m, relative_humidity_2m |
| **rain** | precipitation, rain, snowfall, snow_depth |
| **sun**  | cloud_cover, cloud_cover_low/mid/high, shortwave_radiation, direct_radiation, diffuse_radiation, direct_normal_irradiance, sunshine_duration, is_day |
| **wind** | wind_speed_10m, wind_speed_100m, wind_direction_10m, wind_direction_100m, wind_gusts_10m |
| **uv**   | uv_index_est (derived) |

### Notes

- ERA5 has an ~5-day lag; the most recent hours may come from ERA5T (near-real-time).

- `uv_index_est` is a geometric proxy from shortwave radiation — not a measured UV index.

- Units are Open-Meteo defaults: wind in m/s (explicitly requested), temperature in °C, precipitation in mm.

- Timestamps are hour-beginning. `ts_utc` is the canonical key; `ts_local` is derived for convenience.

