#pragma once

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

/// Munkres / Hungarian minimization on a rectangular cost matrix.
/// Returns column assignment for each row (-1 if unassigned / Inf cost).
/// Stable tie-breaking: when costs (or zeros) tie, prefer lower row then
/// lower column index (callers should order rows by track id).
std::vector<int> hungarian_minimize(const std::vector<std::vector<double>>& cost);

/// BEV IoU of two oriented boxes (center x,y; length l; width w; yaw).
/// Returns a value in [0, 1]. Degenerate (non-positive) sizes yield 0.
double bev_oriented_iou(double x1, double y1, double l1, double w1, double yaw1,
                        double x2, double y2, double l2, double w2, double yaw2);

/// Resolve BEV box size: use stored l/w when positive, else class defaults
/// (pedestrian → 0.8×0.6; bicycle/motorcycle → 1.8×0.6; else 4.5×1.8).
void resolve_box_size(const std::string& cls, double& l, double& w);

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
    std::array<uint64_t, static_cast<size_t>(timing::StageTimings::COUNT)>* timings = nullptr);

}  // namespace trackbench
