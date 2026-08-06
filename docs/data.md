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

Use `megvii_val.json` (and/or train). Ingest filters to mini `sample_token`s.

Cite: Zhu et al. arXiv:1908.09492; listed in nuscenes-devkit tracking baselines.

## Normalize

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ingest.nuscenes_ingest --limit 1
cat data/normalized/*/detections.jsonl | head
```

## Fixtures

`data/fixtures/` holds tiny synthetic / checked-in JSONL for CI and unit tests. Do not commit the full mini set.
