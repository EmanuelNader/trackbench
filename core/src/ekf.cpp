#include "trackbench/ekf.hpp"

#include <cmath>

namespace trackbench {

Ekf::Ekf(TrackerConfig config) : config_(std::move(config)) {
  Q_base_.setZero();
  Q_base_(0, 0) = config_.process_var_pos;
  Q_base_(1, 1) = config_.process_var_pos;
  Q_base_(2, 2) = config_.process_var_vel;
  Q_base_(3, 3) = config_.process_var_vel;
  Q_base_(4, 4) = config_.process_var_yaw;

  Q_ctrv_.setZero();
  Q_ctrv_(0, 0) = config_.process_var_pos;
  Q_ctrv_(1, 1) = config_.process_var_pos;
  Q_ctrv_(2, 2) = config_.process_var_yaw;
  Q_ctrv_(3, 3) = config_.process_var_vel;
  Q_ctrv_(4, 4) = config_.process_var_yawrate;

  R_.setZero();
  R_(0, 0) = config_.meas_var_pos;
  R_(1, 1) = config_.meas_var_pos;
  R_(2, 2) = config_.meas_var_yaw;
}

void Ekf::predict(Track& track, double dt) const {
  if (dt < 0.0) {
    dt = 0.0;
  }

  if (config_.motion_model == "ctrv") {
    // CTRV state: [x, y, yaw, v, ω]
    const double x0 = track.x;
    const double y0 = track.y;
    const double yaw0 = track.yaw;
    const double v = std::hypot(track.vx, track.vy);
    const double omega = track.yaw_rate;
    const double omega_dt = omega * dt;

    StateMatrix F = StateMatrix::Identity();

    double xp, yp, yawp;

    if (std::abs(omega_dt) < 1e-6) {
      // First-order Taylor limit (CV degenerate case).
      xp = x0 + v * std::cos(yaw0) * dt;
      yp = y0 + v * std::sin(yaw0) * dt;
      yawp = yaw0 + omega * dt;

      F(0, 2) = -v * std::sin(yaw0) * dt;
      F(0, 3) = std::cos(yaw0) * dt;
      F(1, 2) = v * std::cos(yaw0) * dt;
      F(1, 3) = std::sin(yaw0) * dt;
      F(2, 4) = dt;
    } else {
      const double s0 = std::sin(yaw0);
      const double c0 = std::cos(yaw0);
      const double s1 = std::sin(yaw0 + omega_dt);
      const double c1 = std::cos(yaw0 + omega_dt);
      const double v_omega = v / omega;

      xp = x0 + v_omega * (s1 - s0);
      yp = y0 + v_omega * (-c1 + c0);
      yawp = yaw0 + omega_dt;

      F(0, 2) = v_omega * (c1 - c0);
      F(0, 3) = (s1 - s0) / omega;
      F(1, 2) = v_omega * (s1 - s0);
      F(1, 3) = -(c1 - c0) / omega;
      F(2, 4) = dt;
    }

    StateVector x;
    x << x0, y0, yaw0, v, omega;
    x = F * x;

    track.x = xp;
    track.y = yp;
    track.yaw = normalize_angle(yawp);
    track.vx = v * std::cos(track.yaw);
    track.vy = v * std::sin(track.yaw);
    track.yaw_rate = omega;

    track.P = F * track.P * F.transpose() + Q_ctrv_;
    track.P = 0.5 * (track.P + track.P.transpose());

    ++track.age;
    track.cov_trace = track.P.trace();
    return;
  }

  // Default CV path (motion_model == "cv") — byte-identical to pre-Phase-7.
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
  Eigen::Matrix<Real, kMeasDim, kStateDim> H =
      Eigen::Matrix<Real, kMeasDim, kStateDim>::Zero();
  H(0, 0) = 1.0;
  H(1, 1) = 1.0;

  StateVector x;

  if (config_.motion_model == "ctrv") {
    // CTRRV state: [x, y, yaw, v, ω].  H measures x(0), y(1), yaw(2).
    H(2, 2) = 1.0;
    const Real v = std::hypot(track.vx, track.vy);
    x << track.x, track.y, track.yaw, v, track.yaw_rate;

    MeasVector z;
    z << det.x, det.y, det.yaw;

    MeasVector y = z - H * x;
    y(2) = normalize_angle(y(2));

    MeasMatrix S = H * track.P * H.transpose() + R_;
    Eigen::Matrix<Real, kStateDim, kMeasDim> K =
        track.P * H.transpose() * S.inverse();

    x = x + K * y;
    const Real yaw_new = normalize_angle(x(2));
    const Real v_new   = x(3);
    track.x     = x(0);
    track.y     = x(1);
    track.yaw   = yaw_new;
    track.vx    = v_new * std::cos(yaw_new);
    track.vy    = v_new * std::sin(yaw_new);
    track.yaw_rate = x(4);

    const StateMatrix I = StateMatrix::Identity();
    track.P = (I - K * H) * track.P;
  } else {
    // CV state: [x, y, vx, vy, yaw].  H measures x(0), y(1), yaw(4).
    H(2, 4) = 1.0;
    x << track.x, track.y, track.vx, track.vy, track.yaw;

    MeasVector z;
    z << det.x, det.y, det.yaw;

    MeasVector y = z - H * x;
    y(2) = normalize_angle(y(2));

    MeasMatrix S = H * track.P * H.transpose() + R_;
    Eigen::Matrix<Real, kStateDim, kMeasDim> K =
        track.P * H.transpose() * S.inverse();

    x = x + K * y;
    track.x   = x(0);
    track.y   = x(1);
    track.vx  = x(2);
    track.vy  = x(3);
    track.yaw = normalize_angle(x(4));

    const StateMatrix I = StateMatrix::Identity();
    track.P = (I - K * H) * track.P;
  }

  track.P = 0.5 * (track.P + track.P.transpose());
  track.cls = det.cls;
  if (det.l > 0.0) {
    track.l = det.l;
  }
  if (det.w > 0.0) {
    track.w = det.w;
  }
  track.cov_trace = track.P.trace();
}

Real Ekf::mahalanobis_pos_squared(const Track& track,
                                  const Detection& det) const {
  Eigen::Matrix<Real, 2, kStateDim> H =
      Eigen::Matrix<Real, 2, kStateDim>::Zero();
  H(0, 0) = 1.0;
  H(1, 1) = 1.0;

  const Eigen::Matrix<Real, 2, 1> innov(det.x - track.x, det.y - track.y);
  Eigen::Matrix<Real, 2, 2> Rpos = Eigen::Matrix<Real, 2, 2>::Zero();
  Rpos(0, 0) = config_.meas_var_pos;
  Rpos(1, 1) = config_.meas_var_pos;
  const Eigen::Matrix<Real, 2, 2> S = H * track.P * H.transpose() + Rpos;
  const Eigen::Matrix<Real, 2, 1> sol = S.ldlt().solve(innov);
  return innov.dot(sol);
}

}  // namespace trackbench
