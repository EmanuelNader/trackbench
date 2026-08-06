#include <gtest/gtest.h>

#include <cmath>
#include <map>

#include "trackbench/tracker.hpp"
#include "trackbench/types.hpp"

using trackbench::Detection;
using trackbench::FrameDetections;
using trackbench::TrackState;
using trackbench::Tracker;
using trackbench::TrackerConfig;

TEST(Crossing, IdenticalClassDoNotSwapIds) {
  TrackerConfig cfg;
  cfg.promote_hits = 3;
  cfg.coast_frames = 5;
  cfg.gate_m = 2.0;
  cfg.gate_mahalanobis = 9.21;
  Tracker tracker(cfg);

  // Two cars on parallel lanes (Δy = 3m > gate_m), crossing in x.
  // A: x from -10 → +10, y = 4
  // B: x from +10 → -10, y = 0
  constexpr double y_a = 4.0;
  constexpr double y_b = 0.0;
  constexpr double dt = 0.5;
  constexpr int n_frames = 21;

  int64_t id_left_lane = -1;
  int64_t id_right_lane = -1;

  for (int k = 0; k < n_frames; ++k) {
    const double t = dt * k;
    const double x_a = -10.0 + 1.0 * k;  // +2 m/s
    const double x_b = 10.0 - 1.0 * k;   // -2 m/s

    Detection a;
    a.cls = "car";
    a.x = x_a;
    a.y = y_a;
    a.yaw = 0.0;
    a.score = 0.9;

    Detection b;
    b.cls = "car";
    b.x = x_b;
    b.y = y_b;
    b.yaw = 3.141592653589793;
    b.score = 0.9;

    // Alternate detection order mid-scene to stress association.
    FrameDetections fd;
    fd.frame = k;
    fd.t = t;
    if (k % 2 == 0) {
      fd.detections = {a, b};
    } else {
      fd.detections = {b, a};
    }

    const auto out = tracker.step(fd);
    ASSERT_EQ(out.tracks.size(), 2u) << "frame " << k;

    // Map tracks by nearest true y.
    const trackbench::Track* near_a = nullptr;
    const trackbench::Track* near_b = nullptr;
    for (const auto& tr : out.tracks) {
      if (std::abs(tr.y - y_a) < std::abs(tr.y - y_b)) {
        near_a = &tr;
      } else {
        near_b = &tr;
      }
    }
    ASSERT_NE(near_a, nullptr);
    ASSERT_NE(near_b, nullptr);
    ASSERT_NE(near_a->id, near_b->id);

    if (k == cfg.promote_hits - 1) {
      id_left_lane = near_a->id;
      id_right_lane = near_b->id;
      EXPECT_EQ(near_a->state, TrackState::CONFIRMED);
      EXPECT_EQ(near_b->state, TrackState::CONFIRMED);
    }
    if (k >= cfg.promote_hits - 1) {
      EXPECT_EQ(near_a->id, id_left_lane) << "ID swap on lane A at frame " << k;
      EXPECT_EQ(near_b->id, id_right_lane) << "ID swap on lane B at frame " << k;
    }
  }
}
