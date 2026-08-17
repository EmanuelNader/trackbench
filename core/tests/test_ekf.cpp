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

// ── CTRV tests ──────────────────────────────────────────────────────────────

namespace {

Track make_ctrv_track(double x, double y, double yaw, double v,
                      double yaw_rate, const TrackerConfig& cfg) {
  Track t;
  t.x = x;
  t.y = y;
  t.yaw = yaw;
  t.vx = v * std::cos(yaw);
  t.vy = v * std::sin(yaw);
  t.yaw_rate = yaw_rate;
  t.age = 1;
  t.hits = 1;
  t.P.setZero();
  t.P(0, 0) = cfg.meas_var_pos;
  t.P(1, 1) = cfg.meas_var_pos;
  t.P(2, 2) = cfg.meas_var_yaw;
  t.P(3, 3) = cfg.process_var_vel;
  t.P(4, 4) = cfg.process_var_yawrate;
  t.cov_trace = t.P.trace();
  return t;
}

}  // namespace

TEST(CTRV, StraightLineApproximatelyCV) {
  TrackerConfig cv_cfg;
  cv_cfg.motion_model = "cv";

  TrackerConfig ctrv_cfg;
  ctrv_cfg.motion_model = "ctrv";

  Ekf cv_ekf(cv_cfg);
  Ekf ctrv_ekf(ctrv_cfg);

  constexpr double vx0 = 3.0;
  constexpr double vy0 = 0.5;
  const double yaw0 = std::atan2(vy0, vx0);

  Track cv_track = trackbench::make_track_from_detection(
      (Detection{.cls = "car", .x = 0.0, .y = 0.0, .yaw = yaw0}), 1, cv_cfg);
  cv_track.vx = vx0;
  cv_track.vy = vy0;

  Track ctrv_track = make_ctrv_track(0.0, 0.0, yaw0, 0.0, 0.0, ctrv_cfg);
  ctrv_track.vx = vx0;
  ctrv_track.vy = vy0;
  ctrv_track.yaw_rate = 0.0;

  constexpr double dt = 0.1;
  for (int i = 0; i < 10; ++i) {
    cv_ekf.predict(cv_track, dt);
    ctrv_ekf.predict(ctrv_track, dt);
  }

  EXPECT_NEAR(ctrv_track.x, cv_track.x, 1e-9);
  EXPECT_NEAR(ctrv_track.y, cv_track.y, 1e-9);
  EXPECT_NEAR(ctrv_track.vx, cv_track.vx, 1e-9);
  EXPECT_NEAR(ctrv_track.vy, cv_track.vy, 1e-9);
}

TEST(CTRV, ConstantTurnArc) {
  TrackerConfig cfg;
  cfg.motion_model = "ctrv";
  Ekf ekf(cfg);

  const double v = 5.0;
  const double omega = 0.5;
  const double yaw0 = 0.0;
  const double dt = 0.1;

  Track track = make_ctrv_track(0.0, 0.0, yaw0, v, omega, cfg);

  double yaw_expected = yaw0;
  for (int i = 0; i < 10; ++i) {
    ekf.predict(track, dt);
    yaw_expected += omega * dt;

    const double speed = std::hypot(track.vx, track.vy);
    EXPECT_NEAR(speed, v, 1e-6) << "speed drifted at frame " << i;
    EXPECT_NEAR(track.yaw, yaw_expected, 1e-6) << "yaw mismatch at frame " << i;
  }

  // After 10 frames: yaw = 0 + 10 * 0.5 * 0.1 = 0.5 rad
  EXPECT_NEAR(track.yaw, 0.5, 1e-6);

  // Arc: x should be positive (started moving right), y should be positive
  // (turned counter-clockwise from yaw=0).
  EXPECT_GT(track.x, 0.0);
  EXPECT_GT(track.y, 0.0);
}

TEST(CTRV, SmallOmegaGuard) {
  TrackerConfig cfg;
  cfg.motion_model = "ctrv";
  Ekf ekf(cfg);

  const double v = 3.0;
  const double omega = 1e-8;
  const double dt = 0.1;

  Track track = make_ctrv_track(0.0, 0.0, 0.0, v, omega, cfg);

  for (int i = 0; i < 10; ++i) {
    ekf.predict(track, dt);
  }

  EXPECT_TRUE(std::isfinite(track.x));
  EXPECT_TRUE(std::isfinite(track.y));
  EXPECT_TRUE(std::isfinite(track.vx));
  EXPECT_TRUE(std::isfinite(track.vy));
  EXPECT_TRUE(std::isfinite(track.yaw));

  // With ω ≈ 0, CTRV should approximate CV.
  EXPECT_NEAR(track.x, v * dt * 10, 1e-6);
  EXPECT_NEAR(track.y, 0.0, 1e-6);
}

TEST(CTRV, Determinism) {
  TrackerConfig cfg;
  cfg.motion_model = "ctrv";
  Ekf ekf(cfg);

  auto run = [&]() {
    Track track = make_ctrv_track(1.0, 2.0, 0.7, 4.0, 0.3, cfg);
    ekf.predict(track, 0.1);
    return track;
  };

  const Track a = run();
  const Track b = run();

  EXPECT_EQ(a.x, b.x);
  EXPECT_EQ(a.y, b.y);
  EXPECT_EQ(a.yaw, b.yaw);
  EXPECT_EQ(a.vx, b.vx);
  EXPECT_EQ(a.vy, b.vy);
  EXPECT_EQ(a.yaw_rate, b.yaw_rate);
  EXPECT_EQ(a.P, b.P);
  EXPECT_EQ(a.age, b.age);
}
