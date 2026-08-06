#include <cmath>
#include <gtest/gtest.h>

#include "trackbench/ekf.hpp"
#include "trackbench/track.hpp"
#include "trackbench/types.hpp"

using trackbench::Detection;
using trackbench::Ekf;
using trackbench::Track;
using trackbench::TrackerConfig;

TEST(Ekf, ConvergesOnStraightLine) {
  TrackerConfig cfg;
  cfg.process_var_pos = 0.1;
  cfg.process_var_vel = 0.1;
  cfg.process_var_yaw = 0.01;
  cfg.meas_var_pos = 0.25;
  cfg.meas_var_yaw = 0.05;

  Ekf ekf(cfg);

  Detection birth;
  birth.cls = "car";
  birth.x = 0.0;
  birth.y = 0.0;
  birth.yaw = 0.0;
  Track track = trackbench::make_track_from_detection(birth, 1, cfg);

  // True motion: vx=2 m/s, vy=0, dt=0.5 → Δx=1 each step.
  constexpr double dt = 0.5;
  constexpr double vx_true = 2.0;
  double true_x = 0.0;

  double last_err = 1e9;
  for (int k = 1; k <= 20; ++k) {
    ekf.predict(track, dt);
    true_x += vx_true * dt;

    Detection z;
    z.cls = "car";
    z.x = true_x + 0.05;  // small bias/noise
    z.y = 0.02;
    z.yaw = 0.0;
    ekf.update(track, z);

    const double err = std::hypot(track.x - true_x, track.y - 0.0);
    if (k > 5) {
      EXPECT_LT(err, 0.5) << "step " << k;
      EXPECT_LT(err, last_err + 0.05) << "should not diverge at step " << k;
    }
    last_err = err;
  }

  EXPECT_NEAR(track.vx, vx_true, 0.5);
  EXPECT_LT(std::abs(track.y), 0.3);
}

TEST(Ekf, YawInnovationWraps) {
  TrackerConfig cfg;
  Ekf ekf(cfg);
  Detection birth;
  birth.cls = "car";
  birth.x = 0.0;
  birth.y = 0.0;
  birth.yaw = 3.0;  // near +pi
  Track track = trackbench::make_track_from_detection(birth, 1, cfg);

  Detection z;
  z.cls = "car";
  z.x = 0.0;
  z.y = 0.0;
  z.yaw = -3.0;  // near -pi; raw error ~6, wrapped small
  ekf.update(track, z);

  // Updated yaw should stay near ±pi, not jump toward 0 via unwrapped error.
  EXPECT_GT(std::abs(track.yaw), 2.0);
}
