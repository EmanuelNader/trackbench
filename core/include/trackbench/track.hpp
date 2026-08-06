#pragma once

#include "trackbench/types.hpp"

namespace trackbench {

/// Create a new tentative track from a detection.
Track make_track_from_detection(const Detection& det, int64_t id);

/// Promote / coast / kill lifecycle helpers (stubs for M0).
void mark_hit(Track& track, int promote_hits);
void mark_miss(Track& track, int coast_frames);
bool is_outputtable(const Track& track);

}  // namespace trackbench
