# Weather Compare — Santa Clara, CA vs Eastside King, WA

Hourly weather comparison dashboard with user-weighted scoring.

## Stack
- **ETL**: Python 3.12, httpx, pandas, pyarrow
- **Storage**: Parquet (raw + curated), DuckDB for ad-hoc queries
- **Frontend** (planned): Vite + React + TS + DuckDB-WASM, reads Parquet directly

## Quick start
```bash
uv sync                               # install deps into .venv
uv run python -m etl.sources.open_meteo --sample   # last 30 days, 6 points
uv run python -m etl.curate
uv run python -m etl.dictionary_gen
```

## Layout
See `CLAUDE.md` / planning notes. Core dirs: `etl/`, `classifier/`, `data/`, `app/`.
