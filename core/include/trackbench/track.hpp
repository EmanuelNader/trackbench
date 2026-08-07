#pragma once

#include "trackbench/types.hpp"

namespace trackbench {

/// Create a new tentative track from a detection (hits = 1, age = 1).
Track make_track_from_detection(const Detection& det, int64_t id,
                                const TrackerConfig& config);

/// On match: reset misses; promote TENTATIVE after promote_hits consecutive hits;
/// COASTING → CONFIRMED.
void mark_hit(Track& track, int promote_hits);

/// On miss: reset consecutive hits; CONFIRMED → COASTING; after coast_frames
/// misses → DEAD. TENTATIVE dies on first miss.
void mark_miss(Track& track, int coast_frames);

/// True for any non-DEAD track (including tentative).
bool is_outputtable(const Track& track);

/// Sync cov_trace from P.
void refresh_cov_trace(Track& track);

}  // namespace trackbench
