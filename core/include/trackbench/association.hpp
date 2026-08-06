#pragma once

#include <utility>
#include <vector>

#include "trackbench/ekf.hpp"
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

/// Associate tracks to detections.
/// Cost = squared Mahalanobis distance in position; INF outside gate.
/// Gate: class match AND Euclidean distance <= gate_m AND
/// squared Mahalanobis <= gate_mahalanobis AND (for moving tracks with
/// hits >= 2) velocity-consistency: lateral / rear innovation limits.
/// Determinism: tracks are matched in caller order; ties broken by
/// (track id via row order, detection index).
std::vector<Association> associate(
    const std::vector<Track>& tracks,
    const std::vector<Detection>& detections,
    const Ekf& ekf);

}  // namespace trackbench
