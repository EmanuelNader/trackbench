#pragma once

#include <string>
#include <vector>

#include "trackbench/types.hpp"

namespace trackbench {

/// Read detections.jsonl (one FrameDetections per line). Hand-rolled JSONL.
std::vector<FrameDetections> read_detections_jsonl(const std::string& path);

/// Write tracks.jsonl (one FrameTracks per line).
void write_tracks_jsonl(const std::string& path,
                        const std::vector<FrameTracks>& frames);

/// Write timing.json stub: {"total_ms": 0, "frames": N, "ms_per_frame": []}.
void write_timing_json(const std::string& path, std::size_t num_frames);

/// Load TrackerConfig from JSON object file (subset of keys).
TrackerConfig load_config(const std::string& path);

}  // namespace trackbench
