#pragma once

#include <vector>

#include "trackbench/ekf.hpp"
#include "trackbench/types.hpp"

namespace trackbench {

/// Multi-object tracker: CV-EKF + gated Hungarian + lifecycle.
class Tracker {
 public:
  explicit Tracker(TrackerConfig config = {});

  /// Process one frame; returns non-DEAD tracks for that frame.
  FrameTracks step(const FrameDetections& frame);

  const TrackerConfig& config() const { return config_; }

 private:
  TrackerConfig config_;
  Ekf ekf_;
  int64_t next_id_ = 1;
  std::vector<Track> tracks_;
  double last_t_ = 0.0;
  bool has_last_t_ = false;
};

}  // namespace trackbench
