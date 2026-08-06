#include "trackbench/track.hpp"

namespace trackbench {

void refresh_cov_trace(Track& track) { track.cov_trace = track.P.trace(); }

Track make_track_from_detection(const Detection& det, int64_t id,
                                const TrackerConfig& config) {
  Track t;
  t.id = id;
  t.cls = det.cls;
  t.x = det.x;
  t.y = det.y;
  t.yaw = det.yaw;
  t.vx = 0.0;
  t.vy = 0.0;
  t.state = TrackState::TENTATIVE;
  t.age = 1;
  t.hits = 1;
  t.misses = 0;

  t.P.setZero();
  t.P(0, 0) = config.meas_var_pos;
  t.P(1, 1) = config.meas_var_pos;
  t.P(2, 2) = config.process_var_vel;
  t.P(3, 3) = config.process_var_vel;
  t.P(4, 4) = config.meas_var_yaw;
  if (t.hits >= config.promote_hits) {
    t.state = TrackState::CONFIRMED;
  }
  refresh_cov_trace(t);
  return t;
}

void mark_hit(Track& track, int promote_hits) {
  track.misses = 0;
  if (track.state == TrackState::COASTING) {
    track.state = TrackState::CONFIRMED;
    track.hits = 1;
    return;
  }
  if (track.state == TrackState::DEAD) {
    return;
  }
  ++track.hits;
  if (track.state == TrackState::TENTATIVE && track.hits >= promote_hits) {
    track.state = TrackState::CONFIRMED;
  }
}

void mark_miss(Track& track, int coast_frames) {
  track.hits = 0;
  ++track.misses;

  if (track.state == TrackState::TENTATIVE) {
    track.state = TrackState::DEAD;
    return;
  }

  if (track.state == TrackState::CONFIRMED) {
    track.state = TrackState::COASTING;
  }

  if (track.misses >= coast_frames) {
    track.state = TrackState::DEAD;
  }
}

bool is_outputtable(const Track& track) {
  return track.state != TrackState::DEAD;
}

}  // namespace trackbench
