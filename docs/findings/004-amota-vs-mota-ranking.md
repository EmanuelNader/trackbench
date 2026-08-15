# 004 — AMOTA ranks configs differently than MOTA/IDS

## What the system surfaced

Phase 5 added the nuScenes **AMOTA / AMOTP** recall-curve metrics
(`eval/amota.py`, devkit definition) and scored the same 24-cell ablation grid
that Phase 4 measured on CLEAR MOTA/IDS. Phases 1–3 ranked configs by "fewer
ID switches / higher MOTA": post003 (`gate1p5-vel4p0-iou2p0-birth0p7`) was the
winner on both. AMOTA does **not** agree with that ranking.

## Hypothesis

AMOTA is a recall-thresholded metric: it re-matches at 40 recall slots and
fills unachieved slots with the worst value (`amota.py` worst = 0.0,
`amotp` worst = 2.0). A config that raises MOTA/IDS by *hiding*
low-confidence-but-correct tracks — the mechanism behind the `min_birth_score`
raises in [001](001-dense-id-switch-velocity-gate.md) and
[003](003-harder-birth-score.md) — should be penalized under AMOTA even while
it wins on MOTA/IDS. So the reference-cell ranking under AMOTA should differ.

## Experiment

Re-scored the committed 24-cell grid with `eval/amota.py`, pooled across the 10
mini scenes per cell, exactly as Phase 5 Task 3 defined (`scripts/ablate_amota.py`
writes `bench/ablation/out/<cell>/amota.json`). No tracker, config, or eval-stack
changes; every number below comes from the committed `amota.json` / `summary.json`
cell files and `bench/ablation/pareto.md`. No significance testing — all of this
is as measured on the 10-scene mini set.

## Reference cells (AMOTA/AMOTP from `amota.json`, MOTA/IDS from `summary.json`)

| ref | cell | MOTA | IDS | AMOTA | AMOTP |
|-----|------|------|-----|-------|-------|
| baseline | `gate2p0-vel0p0-iou0p0-birth0p0` | −1.3512 | 890 | 0.1791 | 1.6452 |
| post001 | `gate1p5-vel4p0-iou0p0-birth0p5` | −0.3006 | 618 | 0.2250 | 1.5820 |
| post002 | `gate1p5-vel4p0-iou2p0-birth0p5` | −0.2818 | 619 | 0.2251 | 1.5821 |
| post003 | `gate1p5-vel4p0-iou2p0-birth0p7` | +0.6660 | 415 | 0.2197 | 1.6233 |

Sources: `bench/ablation/out/gate2p0-vel0p0-iou0p0-birth0p0/{summary,amota}.json`,
`.../gate1p5-vel4p0-iou0p0-birth0p5/{summary,amota}.json`,
`.../gate1p5-vel4p0-iou2p0-birth0p5/{summary,amota}.json`,
`.../gate1p5-vel4p0-iou2p0-birth0p7/{summary,amota}.json`.

## AMOTA rises with the fixes that cut IDS

baseline **0.1791 → post001 0.2250 (+26%)** — the velocity-gate + birth-0.5
stack that cut IDS 890 → 618 is AMOTA-positive as well. The per-class table
below adds an important caveat: `all` AMOTA is a **nanmean over non-null
classes** (`amota.py:_nanmean`), and the bicycle class (0.0116 in baseline)
drops to `null` in post001–post003 — no TP matches survive once
`min_birth_score ≥ 0.5`. So a slice of the pooled rise is a *class-coverage
change* (4 scored classes → 3), not per-class improvement. Stated as measured;
the per-class table keeps the caveat visible.

## IoU remains a null under AMOTA

post001 → post002 (the IoU knob): AMOTA **0.2250 → 0.2251**, AMOTP
**1.5820 → 1.5821**. The knob is unchanged on AMOTA to the same 4th decimal
where it was null on IDS (+1 in-stack, 618 → 619). This re-confirms
[002](002-bev-iou-association.md) from a second, independent metric.

## The tension: post003 wins MOTA/IDS, loses on AMOTA

post003 cuts IDS **619 → 415** and rockets MOTA to **+0.6660**, yet its AMOTA
**drops** 0.2251 → 0.2197 and AMOTP worsens 1.5821 → 1.6233 (AMOTP is a
distance — higher is worse). The mechanism matches the Hypothesis: birth 0.7
hides low-confidence-but-correct tracks, so the recall curve's high-recall
slots go unachieved and get worst-value fill (0.0 AMOTA / 2.0 AMOTP). The
config that best optimizes MOTA/IDS is **not** the best AMOTA config.

## The AMOTA-best cell is the baseline gate

AMOTA-best cell across all 24: `gate2p0-vel0p0-iou2p0-birth0p7` = **0.2385**
(AMOTP 1.5645, MOTA 0.8629, IDS 546) — a *looser* gate (2.0, the baseline
value) + IoU + birth 0.7. A looser gate maximizes matches/recall once birth is
strict, which is exactly what a recall-averaged metric rewards. Metric choice
changes the winner: under MOTA/IDS post003 is first, under AMOTA it is third
(0.2197 < post002 0.2251 < post001 0.2250).

## Per-class AMOTA for the 4 reference cells

From each cell's `amota.json` `per_class` (`null` = no GT boxes or no TP
matches at any threshold, `amota.py` — excluded from `all`):

| class | baseline | post001 | post002 | post003 |
|-------|----------|---------|---------|---------|
| bicycle | 0.0116 | null | null | null |
| bus | null | null | null | null |
| car | 0.0221 | 0.0136 | 0.0139 | 0.0101 |
| motorcycle | null | null | null | null |
| pedestrian | null | null | null | null |
| trailer | 0.6000 | 0.6000 | 0.6000 | 0.6000 |
| truck | 0.0826 | 0.0613 | 0.0613 | 0.0488 |

The dense-class (car) and truck AMOTA both decline monotonically from baseline
through post003 while the pooled `all` rises — again the class-pool composition
drives the pooled direction. AMOTA is computed pooled over all scenes
(per-scene breakdown is not produced by `amota.py`); per-scene IDS context is in
the `RESULTS.md` per-scene matrix.

## Pareto reference

`bench/ablation/pareto.svg` / `bench/ablation/pareto.md` (Task 4, deterministic,
machine-generated): one dot per cell, x = pooled p99 per-frame latency,
y = AMOTA / MOTA / IDS. Sorted by AMOTA, the top dot is
`gate2p0-vel0p0-iou2p0-birth0p7` (0.2385, p99 0.1617 ms); post003 sits mid-table
at 0.2197 (p99 0.1273 ms, the fastest reference). AMOTA best ≈ MOTA best on the
latency axis too (both at ~0.16 ms).

## Conclusion

**AMOTA does not rank the 24 cells the same way MOTA/IDS do.** The fixes that
cut IDS (gate + birth raises) are AMOTA-positive up to `min_birth_score=0.5`
(0.1791 → 0.2250), the IoU knob stays null under both metrics, and the
birth-0.7 raise that wins MOTA/IDS *reverses* under AMOTA (0.2251 → 0.2197) by
sacrificing recall at the top of the score curve. Which config is "best"
depends on the metric, and both the pooled and per-class numbers carry the
bicycle class-coverage caveat. All figures are as measured on the 10-scene mini
set; no significance claims.

## What I'd do next

1. Class-aware birth (ped/car/bicycle) so strict birth does not erase the whole
   bicycle class from the AMOTA pool.
2. Re-rank on the full nuScenes split once eval runs outside mini — the pooled
   class-mix effect only grows with more scenes.
3. Decouple `promote_hits` from birth score to recover high-recall slots lost at
   birth 0.7.
