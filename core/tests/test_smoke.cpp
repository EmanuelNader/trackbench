#include <gtest/gtest.h>

#include "trackbench/types.hpp"

TEST(Smoke, TrackStateAndTypes) {
  using trackbench::TrackState;

  EXPECT_NE(TrackState::TENTATIVE, TrackState::CONFIRMED);
  EXPECT_NE(TrackState::COASTING, TrackState::DEAD);

  trackbench::Detection det;
  det.cls = "car";
  det.x = 1.0;
  det.y = 2.0;
  det.yaw = 0.1;
  det.score = 0.9;
  EXPECT_EQ(det.cls, "car");

  trackbench::TrackerConfig cfg;
  EXPECT_EQ(cfg.promote_hits, 3);
  EXPECT_DOUBLE_EQ(cfg.gate_mahalanobis, 9.21);
}
