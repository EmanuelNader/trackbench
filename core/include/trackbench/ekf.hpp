#pragma once

#include "trackbench/types.hpp"

namespace trackbench {

/// Constant-velocity EKF in BEV: state [x, y, vx, vy, yaw].
/// Stubs for M0; real predict/update land in later milestones.
class Ekf {
 public:
  /// Predict state forward by dt seconds.
  void predict(Track& track, double dt) const;

  /// Update track with a matched detection measurement [x, y, yaw].
  void update(Track& track, const Detection& det) const;
};

}  // namespace trackbench
