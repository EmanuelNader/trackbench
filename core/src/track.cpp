#include "trackbench/track.hpp"

namespace trackbench {

Track make_track_from_detection(const Detection& det, int64_t id) {
  Track t;
  t.id = id;
  t.cls = det.cls;
  t.x = det.x;
  t.y = det.y;
  t.yaw = det.yaw;
  t.vx = 0.0;
  t.vy = 0.0;
  t.state = TrackState::TENTATIVE;
  t.age = 0;
  t.cov_trace = 0.0;
  return t;
}

void mark_hit(Track& track, int /*promote_hits*/) {
  // M0 stub: confirm immediately on any hit.
  track.state = TrackState::CONFIRMED;
}

void mark_miss(Track& track, int /*coast_frames*/) {
  // M0 stub: enter coasting; kill logic lands later.
  if (track.state == TrackState::CONFIRMED) {
    track.state = TrackState::COASTING;
  }
}

bool is_outputtable(const Track& track) {
  return track.state == TrackState::CONFIRMED ||
         track.state == TrackState::COASTING;
}

}  // namespace trackbench
