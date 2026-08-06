#pragma once

#include <utility>
#include <vector>

#include "trackbench/types.hpp"

namespace trackbench {

/// Pair of (track_index, detection_index) after gated matching.
using Association = std::pair<std::size_t, std::size_t>;

/// Associate tracks to detections (Mahalanobis / gate_m). Stub for M0.
/// Determinism: when costs tie, prefer lower track index then lower det index;
/// use stable sorts — never rely on unordered_map iteration order.
std::vector<Association> associate(
    const std::vector<Track>& tracks,
    const std::vector<Detection>& detections,
    double gate_m);

}  // namespace trackbench
