#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <utility>
#include <vector>

#include "trackbench/ekf.hpp"
#include "trackbench/timing.hpp"
#include "trackbench/types.hpp"

namespace trackbench {

/// Pair of (track_index, detection_index) after gated matching.
using Association = std::pair<std::size_t, std::size_t>;

/// Large finite cost used as "infinity" in the assignment problem.
constexpr double kCostInf = 1e9;

/// 2-D point used for BEV polygon clipping.
struct Vec2 {
  double x = 0.0;
  double y = 0.0;
};

/// Reusable per-frame scratch for the association stage.
///
/// The tracker is single-threaded; these buffers are reserved once and
/// cleared/refilled per frame to avoid per-frame heap churn (cost matrix,
/// Munkres working arrays, polygon clip buffers, match list).
struct AssociateScratch {
  /// n_t × n_d cost matrix for the current frame (kept intact so the
  /// post-solve Inf/assignment rejection sees the pre-solve costs).
  std::vector<std::vector<double>> cost;
  /// Square-padded working copy of `cost`, mutated in place by Munkres.
  std::vector<std::vector<double>> work;
  /// Munkres working arrays (reused across solves/frames).
  std::vector<int> row_star;
  std::vector<int> col_star;
  std::vector<int> row_prime;
  std::vector<char> col_covered;
  std::vector<char> row_covered;
  /// Row → column assignment from the solve (after Inf rejection).
  std::vector<int> assignment;
  /// Matched (track, detection) pairs for the current frame.
  std::vector<Association> matches;
  /// Ping-pong polygon clip buffers for bev_oriented_iou (reused across the
  /// whole cost-matrix build so clipping allocates no per-pair vectors).
  std::vector<Vec2> clip_a;
  std::vector<Vec2> clip_b;
  /// Spatial prefilter: linearized grid-cell key -> detection indices in that
  /// cell. Buckets and per-cell vectors are kept across frames; the vectors
  /// are cleared and refilled per frame so no per-frame allocation happens.
  std::unordered_map<int64_t, std::vector<std::size_t>> grid;
};

/// Munkres / Hungarian minimization on a rectangular cost matrix.
/// Returns column assignment for each row (-1 if unassigned / Inf cost).
/// Stable tie-breaking: when costs (or zeros) tie, prefer lower row then
/// lower column index (callers should order rows by track id).
std::vector<int> hungarian_minimize(const std::vector<std::vector<double>>& cost);

/// Greedy minimization on a rectangular cost matrix.
/// Sorts all finite-cost pairs by (cost, row, column) and greedily assigns
/// the cheapest available pair. Returns column assignment for each row
/// (-1 if unassigned / Inf cost). Deterministic and faster than Hungarian
/// but not globally optimal.
std::vector<int> greedy_minimize(const std::vector<std::vector<double>>& cost);

/// BEV IoU of two oriented boxes (center x,y; length l; width w; yaw).
/// Returns a value in [0, 1]. Degenerate (non-positive) sizes yield 0.
double bev_oriented_iou(double x1, double y1, double l1, double w1, double yaw1,
                        double x2, double y2, double l2, double w2, double yaw2);

/// Resolve BEV box size: use stored l/w when positive, else class defaults
/// (pedestrian → 0.8×0.6; bicycle/motorcycle → 1.8×0.6; else 4.5×1.8).
void resolve_box_size(const std::string& cls, double& l, double& w);

/// Associate tracks to detections, reusing `scratch` for the cost matrix,
/// the Hungarian working arrays and the match list. All other semantics match
/// `associate` (see below); it writes the result into `scratch.matches`.
/// If `timings` is non-null, the cost-matrix build and the Hungarian solve
/// phases are timed into timings[StageTimings::COST_MATRIX_CONSTRUCT] and
/// timings[StageTimings::ASSOCIATION_SOLVE].
void associate_to(const std::vector<Track>& tracks,
                  const std::vector<Detection>& detections, const Ekf& ekf,
                  AssociateScratch& scratch,
                  timing::StageNs* timings);

/// Associate tracks to detections.
/// Cost = squared Mahalanobis + soft lateral-velocity penalty
///        + iou_weight * (1 - bev_iou); INF outside gate.
/// Gate: class match AND Euclidean <= gate_m AND
/// squared Mahalanobis <= gate_mahalanobis.
/// Determinism: tracks are matched in caller order; ties broken by
/// (track id via row order, detection index).
/// If `timings` is non-null, the cost-matrix build and the Hungarian solve
/// phases are timed into timings[StageTimings::COST_MATRIX_CONSTRUCT] and
/// timings[StageTimings::ASSOCIATION_SOLVE].
std::vector<Association> associate(
    const std::vector<Track>& tracks,
    const std::vector<Detection>& detections,
    const Ekf& ekf,
    timing::StageNs* timings = nullptr);

}  // namespace trackbench
