#include <gtest/gtest.h>

#include <cmath>

#include "trackbench/association.hpp"
#include "trackbench/ekf.hpp"
#include "trackbench/types.hpp"

using trackbench::Detection;
using trackbench::Ekf;
using trackbench::Track;
using trackbench::TrackState;
using trackbench::TrackerConfig;
using trackbench::associate;
using trackbench::bev_oriented_iou;
using trackbench::resolve_box_size;

TEST(BevIou, IdenticalBoxesAreOne) {
  const double iou =
      bev_oriented_iou(0.0, 0.0, 4.5, 1.8, 0.3, 0.0, 0.0, 4.5, 1.8, 0.3);
  EXPECT_NEAR(iou, 1.0, 1e-9);
}

TEST(BevIou, SeparatedBoxesAreZero) {
  const double iou =
      bev_oriented_iou(0.0, 0.0, 4.5, 1.8, 0.0, 20.0, 20.0, 4.5, 1.8, 0.0);
  EXPECT_NEAR(iou, 0.0, 1e-12);
}

TEST(BevIou, PartialOverlapBetweenZeroAndOne) {
  // Shift half a length along x: intersection is half the box area.
  const double iou =
      bev_oriented_iou(0.0, 0.0, 4.0, 2.0, 0.0, 2.0, 0.0, 4.0, 2.0, 0.0);
  // inter = 2*2 = 4; union = 8+8-4 = 12; iou = 4/12 = 1/3
  EXPECT_NEAR(iou, 1.0 / 3.0, 1e-9);
}

TEST(BevIou, ResolveBoxSizeDefaults) {
  double l = 0.0;
  double w = 0.0;
  resolve_box_size("car", l, w);
  EXPECT_DOUBLE_EQ(l, 4.5);
  EXPECT_DOUBLE_EQ(w, 1.8);

  l = 0.0;
  w = 0.0;
  resolve_box_size("pedestrian", l, w);
  EXPECT_DOUBLE_EQ(l, 0.8);
  EXPECT_DOUBLE_EQ(w, 0.6);

  l = 5.0;
  w = 2.0;
  resolve_box_size("car", l, w);
  EXPECT_DOUBLE_EQ(l, 5.0);
  EXPECT_DOUBLE_EQ(w, 2.0);
}

TEST(BevIou, AssociationPrefersHighIouNeighbor) {
  TrackerConfig cfg;
  cfg.gate_m = 5.0;
  cfg.gate_mahalanobis = 100.0;
  cfg.vel_cost_weight = 0.0;
  cfg.iou_weight = 2.0;
  Ekf ekf(cfg);

  Track tr;
  tr.id = 1;
  tr.cls = "car";
  tr.x = 0.0;
  tr.y = 0.0;
  tr.yaw = 0.0;
  tr.vx = 0.0;
  tr.vy = 0.0;
  tr.l = 5.0;
  tr.w = 1.6;
  tr.hits = 5;
  tr.state = TrackState::CONFIRMED;

  // Similar Euclidean distance (~1.5 m); high-IoU is along length, low-IoU
  // is mostly lateral (near-zero box overlap for w=1.6).
  Detection high_iou;
  high_iou.cls = "car";
  high_iou.x = 1.5;
  high_iou.y = 0.05;
  high_iou.l = 5.0;
  high_iou.w = 1.6;
  high_iou.yaw = 0.0;

  Detection low_iou;
  low_iou.cls = "car";
  low_iou.x = 0.1;
  low_iou.y = 1.5;
  low_iou.l = 5.0;
  low_iou.w = 1.6;
  low_iou.yaw = 0.0;

  const double d_high =
      std::hypot(high_iou.x - tr.x, high_iou.y - tr.y);
  const double d_low = std::hypot(low_iou.x - tr.x, low_iou.y - tr.y);
  EXPECT_NEAR(d_high, d_low, 0.05);

  const double iou_high =
      bev_oriented_iou(tr.x, tr.y, tr.l, tr.w, tr.yaw, high_iou.x, high_iou.y,
                       high_iou.l, high_iou.w, high_iou.yaw);
  const double iou_low =
      bev_oriented_iou(tr.x, tr.y, tr.l, tr.w, tr.yaw, low_iou.x, low_iou.y,
                       low_iou.l, low_iou.w, low_iou.yaw);
  EXPECT_GT(iou_high, 0.4);
  EXPECT_LT(iou_low, 0.05);

  // List low-IoU first so without the IoU term Hungarian could prefer it
  // on a pure-distance tie; with iou_weight the high-IoU det must win.
  const auto matches = associate({tr}, {low_iou, high_iou}, ekf);
  ASSERT_EQ(matches.size(), 1u);
  EXPECT_EQ(matches[0].second, 1u);
}
