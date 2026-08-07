#include <gtest/gtest.h>

#include "trackbench/association.hpp"
#include "trackbench/ekf.hpp"
#include "trackbench/types.hpp"

using trackbench::Detection;
using trackbench::Ekf;
using trackbench::Track;
using trackbench::TrackState;
using trackbench::TrackerConfig;
using trackbench::associate;

TEST(VelocityGate, PrefersLongitudinalOverLateralNeighbor) {
  TrackerConfig cfg;
  cfg.gate_m = 5.0;
  cfg.gate_mahalanobis = 100.0;
  cfg.vel_gate_min_speed = 1.0;
  cfg.vel_gate_lateral_m = 1.0;
  cfg.vel_cost_weight = 4.0;
  cfg.iou_weight = 0.0;
  Ekf ekf(cfg);

  Track tr;
  tr.id = 1;
  tr.cls = "car";
  tr.x = 0.0;
  tr.y = 0.0;
  tr.vx = 10.0;
  tr.vy = 0.0;
  tr.hits = 5;
  tr.state = TrackState::CONFIRMED;

  // Two candidate dets at similar Euclidean distance; one is ahead, one lateral.
  Detection ahead;
  ahead.cls = "car";
  ahead.x = 1.2;
  ahead.y = 0.1;

  Detection lateral;
  lateral.cls = "car";
  lateral.x = 0.3;
  lateral.y = 1.2;

  // Order dets so without velocity cost, Hungarian might pick either;
  // with soft lateral penalty, ahead must win.
  const auto matches = associate({tr}, {lateral, ahead}, ekf);
  ASSERT_EQ(matches.size(), 1u);
  EXPECT_EQ(matches[0].second, 1u);  // ahead
}

TEST(VelocityGate, StillAssociatesWhenOnlyLateralCandidate) {
  TrackerConfig cfg;
  cfg.gate_m = 5.0;
  cfg.gate_mahalanobis = 100.0;
  cfg.vel_gate_min_speed = 1.0;
  cfg.vel_gate_lateral_m = 1.0;
  cfg.vel_cost_weight = 4.0;
  cfg.iou_weight = 0.0;
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

  Detection only;
  only.cls = "car";
  only.x = 0.5;
  only.y = 1.5;

  // Soft penalty must not hard-block the only candidate inside the gate.
  const auto matches = associate({tr}, {only}, ekf);
  ASSERT_EQ(matches.size(), 1u);
}
