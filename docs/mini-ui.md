# Load a real mini run into the triage UI

After you have `data/normalized/scene-*` and `data/tracks/scene-*.jsonl` locally:

```bash
# 1. Postgres
make up && make migrate   # or local Postgres with DATABASE_URL

# 2. Write one aggregated Run (metrics + failures + clusters)
pip install -r requirements-full.txt   # needs psycopg
export DATABASE_URL=postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public
PYTHONPATH=. python -m eval.write_run \
  --normalized-dir data/normalized \
  --tracks-dir data/tracks \
  --mine --write-db \
  --notes "mini after M6 velocity/birth fix"

# 3. API — point at normalized + tracks (not only fixtures)
cd api && npm run build
DATABASE_URL=... \
  FIXTURES_ROOT=$PWD/../data/fixtures \
  NORMALIZED_ROOT=$PWD/../data/normalized \
  TRACKS_ROOT=$PWD/../data/tracks \
  node dist/index.js

# 4. Web
cd web && npm run dev
# open http://localhost:5173 — you should see the new run alongside the demo
```

Frame playback resolves GT from `NORMALIZED_ROOT/<scene>/gt.jsonl` and tracks from `TRACKS_ROOT/<scene>.jsonl` (falling back to fixtures for the synthetic demo).
