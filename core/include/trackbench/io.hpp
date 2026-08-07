#pragma once

#include <string>
#include <vector>

#include "trackbench/types.hpp"

namespace trackbench {

/// Read detections.jsonl (one FrameDetections per line). Hand-rolled JSONL.
std::vector<FrameDetections> read_detections_jsonl(const std::string& path);

/// Write tracks.jsonl (one FrameTracks per line). Deterministic formatting.
void write_tracks_jsonl(const std::string& path,
                        const std::vector<FrameTracks>& frames);

/// Write timing.json: {"total_ms":..., "frames":N, "ms_per_frame":[...]}.
void write_timing_json(const std::string& path, double total_ms,
                       const std::vector<double>& ms_per_frame);

/// Load TrackerConfig from JSON object file (subset of keys).
TrackerConfig load_config(const std::string& path);

/// Format a double for deterministic JSON output.
std::string format_json_double(double v);

}  // namespace trackbench
