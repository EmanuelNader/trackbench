#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include <Eigen/Dense>

namespace trackbench {

constexpr int kStateDim = 5;  // [x, y, vx, vy, yaw]
constexpr int kMeasDim = 3;   // [x, y, yaw]

/// Scalar precision of the filter state/covariance. Defaults to double;
/// override with -DTRACKBENCH_PRECISION=float (CMake) to compile the EKF in
/// single precision. Detection, TrackerConfig, and Track metadata stay double
/// (input/JSON contract); a float state converts to double losslessly on write.
#ifndef TRACKBENCH_REAL
#define TRACKBENCH_REAL double
#endif
using Real = TRACKBENCH_REAL;

using StateVector = Eigen::Matrix<Real, kStateDim, 1>;
using StateMatrix = Eigen::Matrix<Real, kStateDim, kStateDim>;
using MeasVector = Eigen::Matrix<Real, kMeasDim, 1>;
using MeasMatrix = Eigen::Matrix<Real, kMeasDim, kMeasDim>;

/// Detection in ego frame at the current timestamp (JSONL detections.jsonl).
struct Detection {
  std::string cls;
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  double l = 0.0;
  double w = 0.0;
  double h = 0.0;
  double yaw = 0.0;
  double score = 0.0;
};

/// Lifecycle state for a track.
enum class TrackState {
  TENTATIVE,
  CONFIRMED,
  COASTING,
  DEAD,
};

/// Output track in ego frame (JSONL tracks.jsonl fields) plus filter state.
struct Track {
  int64_t id = 0;
  std::string cls;
  Real x = 0.0;
  Real y = 0.0;
  Real yaw = 0.0;
  Real vx = 0.0;
  Real vy = 0.0;
  /// BEV box size from last associated detection (0 ⇒ class default in IoU).
  double l = 0.0;
  double w = 0.0;
  /// Passive 3D metadata from the birth detection, constant for the track's
  /// life (used by the AMOTA eval; never updated from later associations).
  double z = 0.0;
  double h = 0.0;
  double score = 0.0;
  double yaw_rate = 0.0;
  TrackState state = TrackState::TENTATIVE;
  int age = 0;
  Real cov_trace = 0.0;

  /// EKF covariance for [x, y, vx, vy, yaw].
  StateMatrix P = StateMatrix::Identity();
  /// Consecutive association hits (birth counts as 1).
  int hits = 0;
  /// Consecutive misses while active.
  int misses = 0;
};

/// One frame of detections (one JSONL line).
struct FrameDetections {
  int64_t frame = 0;
  double t = 0.0;
  std::vector<Detection> detections;
};

/// One frame of tracks (one JSONL line).
struct FrameTracks {
  int64_t frame = 0;
  double t = 0.0;
  std::vector<Track> tracks;
};

/// Tracker config (config/default.json).
/// Determinism: seed is part of config; do not iterate unordered_map in
/// output order; prefer stable_sort for any ranking that affects results.
struct TrackerConfig {
  int promote_hits = 3;
  int coast_frames = 5;
  double gate_m = 2.0;
  /// Squared Mahalanobis gate (2-DoF chi-square ~99% ≈ 9.21).
  double gate_mahalanobis = 9.21;
  int seed = 0;
  double process_var_pos = 1.0;
  double process_var_vel = 1.0;
  double process_var_yaw = 0.1;
  double meas_var_pos = 0.5;
  double meas_var_yaw = 0.1;
  /// Soft velocity-consistency penalty (dense ID-switch fix).
  /// When speed >= vel_gate_min_speed and hits >= 2, add
  ///   vel_cost_weight * (lat / vel_gate_lateral_m)^2
  /// to the Mahalanobis cost. No hard reject (hard gates raised FN/IDS).
  double vel_gate_min_speed = 1.0;   // m/s
  double vel_gate_lateral_m = 1.0;   // lateral scale for soft penalty
  double vel_cost_weight = 4.0;      // weight on squared lateral penalty
  /// Soft BEV IoU term: add iou_weight * (1 - bev_iou) inside the gate.
  double iou_weight = 2.0;
  /// Only birth new tracks from detections at/above this score.
  double min_birth_score = 0.7;
  std::string motion_model = "cv";
  std::string assoc_mode = "hungarian";  // "hungarian" | "greedy"
  double process_var_yawrate = 0.1;
};

inline const char* track_state_string(TrackState s) {
  switch (s) {
    case TrackState::TENTATIVE:
      return "tentative";
    case TrackState::CONFIRMED:
      return "confirmed";
    case TrackState::COASTING:
      return "coasting";
    case TrackState::DEAD:
      return "dead";
  }
  return "dead";
}

/// Wrap angle to [-pi, pi].
inline double normalize_angle(double a) {
  constexpr double kPi = 3.14159265358979323846;
  while (a > kPi) {
    a -= 2.0 * kPi;
  }
  while (a < -kPi) {
    a += 2.0 * kPi;
  }
  return a;
}

}  // namespace trackbench
