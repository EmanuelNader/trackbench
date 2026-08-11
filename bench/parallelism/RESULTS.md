# Intra-frame parallelism experiment (Task 15, Phase 3e) — NOT LANDED

Thread pool (std::thread, fixed size, atomic work-stealing) for the predict and
cost-matrix-construction stages, gated behind `TRACKBENCH_THREADS` env and an
object-count threshold (64). Per-thread BEV clip buffers kept the parallel cost
build race-free. Determinism was verified first (outputs byte-identical at 4
and 8 threads on a 300-frame dense run), then the speedup curve was measured.

**Result: parallelism NEVER wins. Left out per the plan's gate** ("if never
wins at typical N -> leave out, document"). Code reverted; measurements below.

## Speedup curve: serial vs TRACKBENCH_THREADS=4 (interleaved A/B, 3 runs each,
p50 over frames after warmup, same host as PROFILE.md)

| N | serial p50 | serial p99 | par4 p50 | par4 p99 | p50 delta |
|----|-----------|-----------|----------|----------|-----------|
| 10 | 3.3 us | 10.1 us | 22.7 us | 54.7 us | +577% |
| 40 | 14.3 us | 40.6 us | 31.1 us | 51.3 us | +117% |
| 100 | 46.9 us | 66.6 us | 76.2 us | 108.2 us | +62% |
| 200 | 209 us | 240 us | 242 us | 270 us | +16% |

## Why (per-stage p50 at N=200)

| stage | serial | par4 | delta |
|-------|--------|------|-------|
| predict | 9.4 us | 21.8 us | +132% |
| cost_matrix_construct | 17.3 us | 26.7 us | +54% |
| association_solve | 148 us | 159 us | +7% |
| total | 214 us | 248 us | +16% |

Even the two parallelized stages got SLOWER: the fixed dispatch/join overhead
(~12 us per parallel_for) exceeds the entire parallelizable work even at N=200
(predict+cost ~ 27 us). And the dominant stage at high N — the Hungarian solve
(148 us at N=200, 68% of the frame) — is sequential; parallel assignment is out
of scope. Below the 64-item threshold the pool is never engaged, so typical N
(20-60) is purely serial + pool overhead whenever the threshold trips.

## Verdict
The O(n^2) cost build was the frame bottleneck before the spatial prefilter
(Task 13) shrank it 5.8x; with that landed, the remaining parallelizable work
is too small to amortize thread-pool overhead at any N measured. No threshold
exists where parallel predict/cost wins. Reverted; production tracker is
unchanged (all 17 unit tests + golden + eval-fixture gates green after revert).

## Reproduce
Rebuild with the experiment patch, then:
```
TRACKBENCH_THREADS=4 trackbench_run --dets <dense N dets> --config core/config/default.json --timing-csv out.csv
```
compare against the same run without TRACKBENCH_THREADS (interleaved on an idle
host; see PROFILE.md).
