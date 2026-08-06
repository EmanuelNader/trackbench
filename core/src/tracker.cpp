#include "trackbench/tracker.hpp"

#include <algorithm>
#include <utility>
#include <vector>

#include "trackbench/association.hpp"
#include "trackbench/track.hpp"

namespace trackbench {

Tracker::Tracker(TrackerConfig config)
    : config_(std::move(config)), ekf_(config_) {}

FrameTracks Tracker::step(const FrameDetections& frame) {
  double dt = 0.0;
  if (has_last_t_) {
    dt = frame.t - last_t_;
    if (dt < 0.0) {
      dt = 0.0;
    }
  }
  last_t_ = frame.t;
  has_last_t_ = true;

  // Keep tracks ordered by id for deterministic association row order.
  std::stable_sort(tracks_.begin(), tracks_.end(),
                   [](const Track& a, const Track& b) { return a.id < b.id; });

  // 1. Predict all active tracks.
  for (Track& tr : tracks_) {
    if (tr.state != TrackState::DEAD) {
      ekf_.predict(tr, dt);
    }
  }

  // Build index list of active tracks (same order as tracks_).
  std::vector<std::size_t> active_idx;
  std::vector<Track> active;
  active_idx.reserve(tracks_.size());
  active.reserve(tracks_.size());
  for (std::size_t i = 0; i < tracks_.size(); ++i) {
    if (tracks_[i].state != TrackState::DEAD) {
      active_idx.push_back(i);
      active.push_back(tracks_[i]);
    }
  }

  // 2–3. Associate.
  const std::vector<Association> matches =
      associate(active, frame.detections, ekf_);

  std::vector<char> track_matched(active.size(), 0);
  std::vector<char> det_matched(frame.detections.size(), 0);

  // 4. Matched → EKF update + hit.
  for (const Association& m : matches) {
    const std::size_t ai = m.first;
    const std::size_t di = m.second;
    track_matched[ai] = 1;
    det_matched[di] = 1;
    Track& tr = tracks_[active_idx[ai]];
    ekf_.update(tr, frame.detections[di]);
    mark_hit(tr, config_.promote_hits);
  }

  // 5. Unmatched detections → new tentative tracks (in detection order).
  // Birth only from high-confidence dets to limit dense-traffic ID churn.
  for (std::size_t j = 0; j < frame.detections.size(); ++j) {
    if (det_matched[j]) {
      continue;
    }
    if (frame.detections[j].score < config_.min_birth_score) {
      continue;
    }
    tracks_.push_back(make_track_from_detection(frame.detections[j], next_id_,
                                                config_));
    ++next_id_;
  }

  // 6. Unmatched tracks → coast / kill.
  for (std::size_t ai = 0; ai < active.size(); ++ai) {
    if (track_matched[ai]) {
      continue;
    }
    mark_miss(tracks_[active_idx[ai]], config_.coast_frames);
  }

  // Compact dead tracks (ids never reused).
  tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(),
                               [](const Track& t) {
                                 return t.state == TrackState::DEAD;
                               }),
                tracks_.end());

  // Output non-DEAD tracks sorted by id.
  std::stable_sort(tracks_.begin(), tracks_.end(),
                   [](const Track& a, const Track& b) { return a.id < b.id; });

  FrameTracks out;
  out.frame = frame.frame;
  out.t = frame.t;
  out.tracks.reserve(tracks_.size());
  for (const Track& tr : tracks_) {
    if (is_outputtable(tr)) {
      out.tracks.push_back(tr);
    }
  }
  return out;
}

}  // namespace trackbench
