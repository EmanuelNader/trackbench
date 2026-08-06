#include <gtest/gtest.h>

#include "trackbench/association.hpp"
#include "trackbench/ekf.hpp"
#include "trackbench/types.hpp"

using trackbench::Association;
using trackbench::Detection;
using trackbench::Ekf;
using trackbench::Track;
using trackbench::TrackState;
using trackbench::TrackerConfig;
using trackbench::associate;

TEST(VelocityGate, RejectsLaterallyInconsistentDetection) {
  TrackerConfig cfg;
  cfg.gate_m = 5.0;
  cfg.gate_mahalanobis = 100.0;
  cfg.vel_gate_min_speed = 1.0;
  cfg.vel_gate_lateral_m = 1.0;
  cfg.vel_gate_rear_m = 1.5;
  Ekf ekf(cfg);

  Track tr;
  tr.id = 1;
  tr.cls = "car";
  tr.x = 0.0;
  tr.y = 0.0;
  tr.vx = 10.0;  // moving +x
  tr.vy = 0.0;
  tr.hits = 5;
  tr.state = TrackState::CONFIRMED;

  Detection good;
  good.cls = "car";
  good.x = 1.0;  // ahead along velocity
  good.y = 0.2;

  Detection bad;
  bad.cls = "car";
  bad.x = 0.5;
  bad.y = 2.5;  // laterally far — typical dense swap candidate

  const auto matches_good = associate({tr}, {good}, ekf);
  ASSERT_EQ(matches_good.size(), 1u);

  const auto matches_bad = associate({tr}, {bad}, ekf);
  EXPECT_TRUE(matches_bad.empty());
}

TEST(VelocityGate, RejectsDetectionBehindMotion) {
  TrackerConfig cfg;
  cfg.gate_m = 5.0;
  cfg.gate_mahalanobis = 100.0;
  cfg.vel_gate_min_speed = 1.0;
  cfg.vel_gate_lateral_m = 2.0;
  cfg.vel_gate_rear_m = 1.5;
  Ekf ekf(cfg);

  Track tr;
  tr.id = 1;
  tr.cls = "car";
  tr.x = 0.0;
  tr.y = 0.0;
  tr.vx = 8.0;
  tr.vy = 0.0;
  tr.hits = 4;
  tr.state = TrackState::CONFIRMED;

  Detection behind;
  behind.cls = "car";
  behind.x = -2.0;
  behind.y = 0.0;

  EXPECT_TRUE(associate({tr}, {behind}, ekf).empty());
}
