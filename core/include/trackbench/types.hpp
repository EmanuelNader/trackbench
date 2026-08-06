#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace trackbench {

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

/// Output track in ego frame (JSONL tracks.jsonl fields).
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
  int seed = 0;
};

}  // namespace trackbench
