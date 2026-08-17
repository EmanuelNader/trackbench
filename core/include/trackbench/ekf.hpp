#pragma once

#include "trackbench/types.hpp"

namespace trackbench {

/// Constant-velocity EKF in BEV: state [x, y, vx, vy, yaw].
/// Measurement [x, y, yaw]. Process/measurement noise from TrackerConfig.
class Ekf {
 public:
  explicit Ekf(TrackerConfig config);

  /// Predict state forward by dt seconds.
  void predict(Track& track, double dt) const;

  /// Update track with a matched detection measurement [x, y, yaw].
  /// Yaw innovation is wrapped to [-pi, pi].
  void update(Track& track, const Detection& det) const;

  /// Squared Mahalanobis distance in position (x, y) only.
  Real mahalanobis_pos_squared(const Track& track, const Detection& det) const;

  const TrackerConfig& config() const { return config_; }

 private:
  TrackerConfig config_;
  StateMatrix Q_base_ = StateMatrix::Zero();
  StateMatrix Q_ctrv_ = StateMatrix::Zero();
  MeasMatrix R_ = MeasMatrix::Zero();
};

}  // namespace trackbench
