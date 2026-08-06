#include <gtest/gtest.h>

#include "trackbench/types.hpp"

TEST(Smoke, Arithmetic) {
  EXPECT_EQ(1 + 1, 2);
}

TEST(Smoke, TrackStateAndTypes) {
  using trackbench::TrackState;

  EXPECT_NE(TrackState::TENTATIVE, TrackState::CONFIRMED);
  EXPECT_NE(TrackState::COASTING, TrackState::DEAD);

  trackbench::Detection det;
  det.cls = "car";
  det.x = 1.0;
  det.y = 2.0;
  det.z = 0.0;
  det.l = 4.0;
  det.w = 2.0;
  det.h = 1.5;
  det.yaw = 0.1;
  det.score = 0.9;
  EXPECT_EQ(det.cls, "car");

  trackbench::Track track;
  track.id = 1;
  track.cls = det.cls;
  track.x = det.x;
  track.y = det.y;
  track.yaw = det.yaw;
  track.vx = 0.0;
  track.vy = 0.0;
  track.state = TrackState::TENTATIVE;
  track.age = 0;
  track.cov_trace = 0.0;
  EXPECT_EQ(track.state, TrackState::TENTATIVE);

  trackbench::FrameDetections fd;
  fd.frame = 0;
  fd.t = 0.0;
  fd.detections.push_back(det);
  EXPECT_EQ(fd.detections.size(), 1u);

  trackbench::FrameTracks ft;
  ft.frame = 0;
  ft.t = 0.0;
  EXPECT_TRUE(ft.tracks.empty());
}
