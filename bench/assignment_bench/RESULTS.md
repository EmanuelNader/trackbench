# Assignment algorithm benchmark: Munkres vs auction (Task 14, Phase 3b)

`assignment_bench.cpp` links the production `trackbench::hungarian_minimize`
from the core static library and compares it against a self-contained Bertsekas
forward auction (ε = 1e-4·V/(n+1), cold start). Optimality is validated
empirically against Munkres as the oracle.

**Result: NO SWITCH.** The production Munkres stays. Reasons, all measured:

## 1. No alternative solver can produce identical output (the "without output
change" gate is structurally unattainable)
Tie test: on 100% of real-shaped cost matrices (quantized costs + ~30%
Inf-padding, sizes 8-40) there exist **multiple optimal assignments** —
Munkres with a micro-perturbation returns a different assignment with the same
optimal total cost (351/351 and 361/361 matrices across runs). Any solver with
different tie-breaking (JV, auction) necessarily changes the tracker output,
which the plan's gate forbids.

## 2. The auction is suboptimal on this cost structure
On dense random matrices the auction lands on the optimum, but with the
tracker's Inf-padded structure it converges to a local solution:

| N | munkres µs | auction µs | speedup | cost gap (auction vs optimal) |
|----|-----------|------------|---------|------------------------------|
| 10 | 2.5 | 0.4 | 6.1x | +0.51 |
| 20 | 19.6 | 2.2 | 8.9x | +0.82 |
| 40 | 126 | 2.4 | 53x | +1.08 |
| 60 | 427 | 5.2 | 82x | +1.34 |
| 100 | 2141 | 14 | 149x | +1.16 |
| 200 | 21689 | 44 | 499x | +2.39 |

(auction times are µs on the same 5-matrix average; cost gap is relative total
cost increase vs the optimal — e.g. +2.39 = 239% worse. The apparent speedup is
an artifact of not searching to optimality.) Across the 60-matrix validation,
the auction differed from the Munkres assignment in ~30% of rows even when
totals were near-equal, and violated the n·ε optimality bound by up to 1.5× on
Inf-padded matrices. Tightening ε to close the gap drives bid count toward
O(n·C/ε) — impractical (observed hang at ε = 1e-9·V/n). A correct LAPJV needs
the full dual-update machinery (out of scope to hand-roll safely); an oracle
check against Munkres caught a static-duals JV variant as suboptimal on 340/1000
matrices.

## 3. Even a free speedup would be a poor trade at typical N
Production Munkres solve cost measured from real tracker runs (HEAD, post-grid
prefilter), p50 over frames:

| N | solve | share of frame |
|----|-------|----------------|
| 10 | 0.21 µs | 7.2% |
| 20 | 0.62 µs | 10.3% |
| 40 | 2.46 µs | 17.7% |
| 60 | 5.46 µs | 23.4% |
| 100 | 20.5 µs | 31.9% |
| 200 | 154 µs | 68.8% |

At typical N (20-60) the solve is 10-23% of frame time; even an improbable 1.5×
solve speedup is ~4-8% of frame, and it would change outputs. Munkres remains
the right choice.

## Rebuild / run
```
cmake -S core -B build -DCMAKE_BUILD_TYPE=Release -DTRACKBENCH_BUILD_TESTS=ON
cmake --build build
clang++ -O3 -std=c++17 -I core/include bench/assignment_bench/assignment_bench.cpp build/libtrackbench.a -o /tmp/assignment_bench
TB_VAL_ROUNDS=40 /tmp/assignment_bench
```
(Timing numbers above were captured on the same host as PROFILE.md; they are
context, not gates.)
