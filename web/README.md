# OutdoorHours · KOUT-7

Vite + React frontend for the weather report at https://bilko.run/projects/outdoor-hours/.

The app now lives in outdoor-hours-etl/web (this directory); the old standalone repo is retired.

Hosted on bilko.run via the **static-path** contract (see `~/Projects/Bilko/docs/host-contract.md`):
- `pnpm build` produces `dist/`.
- Bilko serves the bundle at `/projects/outdoor-hours/`; React Router uses that as basename.

Data files live at `bilko.run/outdoor-hours/*.json` and are produced by this repo's ETL (`scripts/export_outdoor_hours.py`).

## Develop

```
pnpm --dir web install
pnpm --dir web dev
```

## Ship

Publish with `bash scripts/publish_web.sh` from the repo root.
