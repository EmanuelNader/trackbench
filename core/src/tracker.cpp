#include "trackbench/tracker.hpp"

#include <algorithm>
#include <utility>
#include <vector>

#include "trackbench/association.hpp"
#include "trackbench/timing.hpp"
#include "trackbench/track.hpp"

namespace trackbench {

Tracker::Tracker(TrackerConfig config)
    : config_(std::move(config)), ekf_(config_) {
  // Reserve per-frame scratch buffers once (grow lazily past this hint).
  constexpr std::size_t kInitialCapacity = 64;
  active_.reserve(kInitialCapacity);
  active_idx_.reserve(kInitialCapacity);
  track_matched_.reserve(kInitialCapacity);
  det_matched_.reserve(kInitialCapacity);
  associate_scratch_.cost.reserve(kInitialCapacity);
  associate_scratch_.work.reserve(kInitialCapacity);
  associate_scratch_.row_star.reserve(kInitialCapacity);
  associate_scratch_.col_star.reserve(kInitialCapacity);
  associate_scratch_.row_prime.reserve(kInitialCapacity);
  associate_scratch_.col_covered.reserve(kInitialCapacity);
  associate_scratch_.row_covered.reserve(kInitialCapacity);
  associate_scratch_.assignment.reserve(kInitialCapacity);
  associate_scratch_.matches.reserve(kInitialCapacity);
  associate_scratch_.clip_a.reserve(8);
  associate_scratch_.clip_b.reserve(8);
  associate_scratch_.grid.reserve(kInitialCapacity);
}

FrameTracks Tracker::step(const FrameDetections& frame) {
#ifdef TRACKBENCH_STAGE_TIMING
  timing::StageNs stage_ns{};
#endif

  FrameTracks out;
  {
#ifdef TRACKBENCH_STAGE_TIMING
    timing::ScopedTimer timer_total(stage_ns, timing::StageTimings::TOTAL);
#endif

    double dt = 0.0;
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_dt(stage_ns, timing::StageTimings::DT);
#endif
      if (has_last_t_) {
        dt = frame.t - last_t_;
        if (dt < 0.0) {
          dt = 0.0;
        }
      }
      last_t_ = frame.t;
      has_last_t_ = true;
    }

    // Keep tracks ordered by id for deterministic association row order.
    std::stable_sort(tracks_.begin(), tracks_.end(),
                     [](const Track& a, const Track& b) { return a.id < b.id; });

    // 1. Predict all active tracks.
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_predict(stage_ns, timing::StageTimings::PREDICT);
#endif
      for (Track& tr : tracks_) {
        if (tr.state != TrackState::DEAD) {
          ekf_.predict(tr, dt);
        }
      }
    }

    // Build index list of active tracks (same order as tracks_).
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_build_active(stage_ns, timing::StageTimings::BUILD_ACTIVE);
#endif
      active_idx_.clear();
      active_.clear();
      active_idx_.reserve(tracks_.size());
      active_.reserve(tracks_.size());
      for (std::size_t i = 0; i < tracks_.size(); ++i) {
        if (tracks_[i].state != TrackState::DEAD) {
          active_idx_.push_back(i);
          active_.push_back(tracks_[i]);
        }
      }
    }

    // 2-3. Associate (cost-matrix build + Hungarian solve timed inside).
#ifdef TRACKBENCH_STAGE_TIMING
    associate_to(active_, frame.detections, ekf_, associate_scratch_, &stage_ns);
#else
    associate_to(active_, frame.detections, ekf_, associate_scratch_, nullptr);
#endif
    const std::vector<Association>& matches = associate_scratch_.matches;

    track_matched_.assign(active_.size(), 0);
    det_matched_.assign(frame.detections.size(), 0);

    // 4. Matched -> EKF update + hit.
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_update(stage_ns, timing::StageTimings::UPDATE);
#endif
      for (const Association& m : matches) {
        const std::size_t ai = m.first;
        const std::size_t di = m.second;
        track_matched_[ai] = 1;
        det_matched_[di] = 1;
        Track& tr = tracks_[active_idx_[ai]];
        ekf_.update(tr, frame.detections[di]);
        mark_hit(tr, config_.promote_hits);
      }
    }

    // 5. Unmatched detections -> new tentative tracks (in detection order).
    // Birth only from high-confidence dets to limit dense-traffic ID churn.
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_birth(stage_ns, timing::StageTimings::BIRTH);
#endif
      for (std::size_t j = 0; j < frame.detections.size(); ++j) {
        if (det_matched_[j]) {
          continue;
        }
        if (frame.detections[j].score < config_.min_birth_score) {
          continue;
        }
        tracks_.push_back(make_track_from_detection(frame.detections[j], next_id_,
                                                    config_));
        ++next_id_;
      }
    }

    // 6. Unmatched tracks -> coast / kill.
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_coast_kill(stage_ns, timing::StageTimings::COAST_KILL);
#endif
      for (std::size_t ai = 0; ai < active_.size(); ++ai) {
        if (track_matched_[ai]) {
          continue;
        }
        mark_miss(tracks_[active_idx_[ai]], config_.coast_frames);
      }
    }

    // Compact dead tracks (ids never reused).
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_compact(stage_ns, timing::StageTimings::COMPACT);
#endif
      tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(),
                                   [](const Track& t) {
                                     return t.state == TrackState::DEAD;
                                   }),
                    tracks_.end());
    }

    // Output non-DEAD tracks sorted by id.
    {
#ifdef TRACKBENCH_STAGE_TIMING
      timing::ScopedTimer timer_sort_emit(stage_ns, timing::StageTimings::SORT_EMIT);
#endif
      std::stable_sort(tracks_.begin(), tracks_.end(),
                       [](const Track& a, const Track& b) { return a.id < b.id; });

      out.frame = frame.frame;
      out.t = frame.t;
      out.tracks.reserve(tracks_.size());
      for (const Track& tr : tracks_) {
        if (is_outputtable(tr)) {
          out.tracks.push_back(tr);
        }
      }
    }
  }

#ifdef TRACKBENCH_STAGE_TIMING
  // Cap the retained window to keep memory bounded on long runs; only the
  // most recent frames are kept (the CSV writer reads the tail).
  static constexpr std::size_t kMaxFrameTimings = 4096;
  if (frame_timings_.size() == kMaxFrameTimings) {
    frame_timings_.erase(frame_timings_.begin());
  }
  frame_timings_.push_back(stage_ns);
#endif
  return out;
}

}  // namespace trackbench
