#include "trackbench/ekf.hpp"

namespace trackbench {

Ekf::Ekf(TrackerConfig config) : config_(std::move(config)) {
  Q_base_.setZero();
  Q_base_(0, 0) = config_.process_var_pos;
  Q_base_(1, 1) = config_.process_var_pos;
  Q_base_(2, 2) = config_.process_var_vel;
  Q_base_(3, 3) = config_.process_var_vel;
  Q_base_(4, 4) = config_.process_var_yaw;

  R_.setZero();
  R_(0, 0) = config_.meas_var_pos;
  R_(1, 1) = config_.meas_var_pos;
  R_(2, 2) = config_.meas_var_yaw;
}

void Ekf::predict(Track& track, double dt) const {
  if (dt < 0.0) {
    dt = 0.0;
  }

  StateMatrix F = StateMatrix::Identity();
  F(0, 2) = dt;
  F(1, 3) = dt;

  StateVector x;
  x << track.x, track.y, track.vx, track.vy, track.yaw;
  x = F * x;

  track.x = x(0);
  track.y = x(1);
  track.vx = x(2);
  track.vy = x(3);
  track.yaw = normalize_angle(x(4));

  // Inject process noise once per predict step (global params; no dt scaling).
  track.P = F * track.P * F.transpose() + Q_base_;
  track.P = 0.5 * (track.P + track.P.transpose());

  ++track.age;
  track.cov_trace = track.P.trace();
}

void Ekf::update(Track& track, const Detection& det) const {
  Eigen::Matrix<double, kMeasDim, kStateDim> H =
      Eigen::Matrix<double, kMeasDim, kStateDim>::Zero();
  H(0, 0) = 1.0;
  H(1, 1) = 1.0;
  H(2, 4) = 1.0;

  StateVector x;
  x << track.x, track.y, track.vx, track.vy, track.yaw;

  MeasVector z;
  z << det.x, det.y, det.yaw;

  MeasVector y = z - H * x;
  y(2) = normalize_angle(y(2));

  MeasMatrix S = H * track.P * H.transpose() + R_;
  Eigen::Matrix<double, kStateDim, kMeasDim> K =
      track.P * H.transpose() * S.inverse();

  x = x + K * y;
  track.x = x(0);
  track.y = x(1);
  track.vx = x(2);
  track.vy = x(3);
  track.yaw = normalize_angle(x(4));

  const StateMatrix I = StateMatrix::Identity();
  track.P = (I - K * H) * track.P;
  track.P = 0.5 * (track.P + track.P.transpose());

  track.cls = det.cls;
  track.cov_trace = track.P.trace();
}

double Ekf::mahalanobis_pos_squared(const Track& track,
                                    const Detection& det) const {
  Eigen::Matrix<double, 2, kStateDim> H =
      Eigen::Matrix<double, 2, kStateDim>::Zero();
  H(0, 0) = 1.0;
  H(1, 1) = 1.0;

  const Eigen::Vector2d innov(det.x - track.x, det.y - track.y);
  Eigen::Matrix2d Rpos = Eigen::Matrix2d::Zero();
  Rpos(0, 0) = config_.meas_var_pos;
  Rpos(1, 1) = config_.meas_var_pos;
  const Eigen::Matrix2d S = H * track.P * H.transpose() + Rpos;
  const Eigen::Vector2d sol = S.ldlt().solve(innov);
  return innov.dot(sol);
}

}  // namespace trackbench
