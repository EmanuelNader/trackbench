#include "trackbench/tracker.hpp"

namespace trackbench {

Tracker::Tracker(TrackerConfig config) : config_(std::move(config)) {}

FrameTracks Tracker::step(const FrameDetections& frame) {
  // M0: passthrough — emit empty tracks for the same frame/t.
  // Later: predict → associate → update / birth / death using config_.seed
  // and stable ordering (no unordered_map iteration affecting output).
  (void)tracks_;
  (void)next_id_;
  FrameTracks out;
  out.frame = frame.frame;
  out.t = frame.t;
  out.tracks.clear();
  return out;
}

}  // namespace trackbench
