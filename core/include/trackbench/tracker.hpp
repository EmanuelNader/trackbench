#pragma once

#include <vector>

#include "trackbench/association.hpp"
#include "trackbench/ekf.hpp"
#include "trackbench/timing.hpp"
#include "trackbench/types.hpp"

namespace trackbench {

/// Multi-object tracker: CV-EKF + gated Hungarian + lifecycle.
class Tracker {
 public:
  explicit Tracker(TrackerConfig config = {});

  /// Process one frame; returns non-DEAD tracks for that frame.
  FrameTracks step(const FrameDetections& frame);

  const TrackerConfig& config() const { return config_; }

#ifdef TRACKBENCH_STAGE_TIMING
  const auto& frame_timings() const { return frame_timings_; }
#endif

 private:
  TrackerConfig config_;
  Ekf ekf_;
  int64_t next_id_ = 1;
  std::vector<Track> tracks_;
  double last_t_ = 0.0;
  bool has_last_t_ = false;

  // Per-frame scratch buffers, reserved once and cleared per frame, to avoid
  // per-frame heap churn (active subset, association cost/solve, match flags).
  std::vector<Track> active_;
  std::vector<std::size_t> active_idx_;
  std::vector<char> track_matched_;
  std::vector<char> det_matched_;
  AssociateScratch associate_scratch_;

#ifdef TRACKBENCH_STAGE_TIMING
  std::vector<std::array<uint64_t, static_cast<size_t>(timing::StageTimings::COUNT)>> frame_timings_;
#endif
};

}  // namespace trackbench
