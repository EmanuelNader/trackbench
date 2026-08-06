#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include <Eigen/Dense>

namespace trackbench {

constexpr int kStateDim = 5;  // [x, y, vx, vy, yaw]
constexpr int kMeasDim = 3;   // [x, y, yaw]

using StateVector = Eigen::Matrix<double, kStateDim, 1>;
using StateMatrix = Eigen::Matrix<double, kStateDim, kStateDim>;
using MeasVector = Eigen::Matrix<double, kMeasDim, 1>;
using MeasMatrix = Eigen::Matrix<double, kMeasDim, kMeasDim>;

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
  double x = 0.0;
  double y = 0.0;
  double yaw = 0.0;
  double vx = 0.0;
  double vy = 0.0;
  TrackState state = TrackState::TENTATIVE;
  int age = 0;
  double cov_trace = 0.0;

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
