# Data setup (public only)

## nuScenes mini (~4 GB)

```bash
mkdir -p data/raw/nuscenes
wget -O data/raw/v1.0-mini.tgz https://www.nuscenes.org/data/v1.0-mini.tgz
tar -xf data/raw/v1.0-mini.tgz -C data/raw/nuscenes
```

Devkit expects `dataroot` containing `samples/`, `sweeps/`, `maps/`, and `v1.0-mini/`.

Official tutorial: https://www.nuscenes.org/tutorials/nuscenes_tutorial.html

## Megvii published detections

```bash
mkdir -p data/raw/detections
wget -O data/raw/detections/detection-megvii.zip https://www.nuscenes.org/data/detection-megvii.zip
unzip -d data/raw/detections data/raw/detections/detection-megvii.zip
```

Cite: Zhu et al. arXiv:1908.09492; listed in nuscenes-devkit tracking baselines.

### Merge train ∪ val for mini (`megvii_mini_merged.json`)

Mini’s 10 scenes straddle the official train/val split. Using only one file leaves some scenes with empty dets (see [decisions.md](decisions.md) D6). Merge with the committed helper:

```bash
python scripts/merge_megvii_mini.py
# → data/raw/detections/megvii_mini_merged.json
```

Point ingest at the merge (already the default in `.env.example`):

```bash
export DETECTIONS_JSON=./data/raw/detections/megvii_mini_merged.json
```

## Normalize

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ingest.nuscenes_ingest --limit 1
cat data/normalized/*/detections.jsonl | head
```

Ingest keeps tracking classes only and drops dets with score < 0.3 (D7).

## Fixtures

`data/fixtures/` holds tiny synthetic / checked-in JSONL for CI and unit tests. Do not commit the full mini set.

## Eval all normalized scenes

After ingest (+ `make core`):

```bash
./scripts/eval_all_scenes.sh
# writes data/tracks/<scene>_eval.json and prints mota / ids / n_failures
```

Synthetic smoke (no download): `make eval-fixture`.
