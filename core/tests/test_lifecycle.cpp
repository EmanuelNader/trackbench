#include <gtest/gtest.h>

#include "trackbench/tracker.hpp"
#include "trackbench/types.hpp"

using trackbench::Detection;
using trackbench::FrameDetections;
using trackbench::TrackState;
using trackbench::Tracker;
using trackbench::TrackerConfig;

namespace {

Detection car_at(double x, double y) {
  Detection d;
  d.cls = "car";
  d.x = x;
  d.y = y;
  d.yaw = 0.0;
  d.score = 1.0;
  return d;
}

FrameDetections frame(int64_t f, double t, std::vector<Detection> dets) {
  FrameDetections fd;
  fd.frame = f;
  fd.t = t;
  fd.detections = std::move(dets);
  return fd;
}

}  // namespace

TEST(Lifecycle, PromoteAtExactlyNHitsDieAtExactlyMMisses) {
  TrackerConfig cfg;
  cfg.promote_hits = 3;
  cfg.coast_frames = 5;
  cfg.gate_m = 5.0;
  cfg.gate_mahalanobis = 100.0;
  Tracker tracker(cfg);

  // Hits 1..3 at same location (stationary).
  for (int i = 0; i < 3; ++i) {
    const auto out =
        tracker.step(frame(i, 0.5 * i, {car_at(0.0, 0.0)}));
    ASSERT_EQ(out.tracks.size(), 1u);
    if (i < 2) {
      EXPECT_EQ(out.tracks[0].state, TrackState::TENTATIVE) << "frame " << i;
    } else {
      EXPECT_EQ(out.tracks[0].state, TrackState::CONFIRMED) << "frame " << i;
    }
    EXPECT_EQ(out.tracks[0].id, 1);
  }

  // Misses 1..4 → still coasting / present; miss 5 → dead (gone).
  for (int m = 1; m <= 4; ++m) {
    const auto out = tracker.step(frame(2 + m, 0.5 * (2 + m), {}));
    ASSERT_EQ(out.tracks.size(), 1u) << "miss " << m;
    EXPECT_EQ(out.tracks[0].state, TrackState::COASTING) << "miss " << m;
  }

  const auto dead = tracker.step(frame(7, 3.5, {}));
  EXPECT_TRUE(dead.tracks.empty());
}
