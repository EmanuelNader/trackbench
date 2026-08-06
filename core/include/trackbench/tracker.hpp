#pragma once

#include <vector>

#include "trackbench/types.hpp"

namespace trackbench {

/// Multi-object tracker facade. M0: passthrough empty tracks per frame.
class Tracker {
 public:
  explicit Tracker(TrackerConfig config = {});

  /// Process one frame; returns tracks for that frame (empty in M0).
  FrameTracks step(const FrameDetections& frame);

  const TrackerConfig& config() const { return config_; }

 private:
  TrackerConfig config_;
  int64_t next_id_ = 1;
  std::vector<Track> tracks_;
};

}  // namespace trackbench
