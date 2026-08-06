#include "trackbench/io.hpp"

#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace trackbench {
namespace {

std::string trim(std::string s) {
  while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
    s.erase(s.begin());
  }
  while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
    s.pop_back();
  }
  return s;
}

/// Extract a JSON number after `"key":` (first occurrence). Returns false if missing.
bool extract_number(const std::string& line, const char* key, double& out) {
  const std::string needle = std::string("\"") + key + "\"";
  const auto pos = line.find(needle);
  if (pos == std::string::npos) {
    return false;
  }
  auto i = pos + needle.size();
  while (i < line.size() && std::isspace(static_cast<unsigned char>(line[i]))) {
    ++i;
  }
  if (i >= line.size() || line[i] != ':') {
    return false;
  }
  ++i;
  while (i < line.size() && std::isspace(static_cast<unsigned char>(line[i]))) {
    ++i;
  }
  try {
    std::size_t consumed = 0;
    out = std::stod(line.substr(i), &consumed);
    return consumed > 0;
  } catch (...) {
    return false;
  }
}

bool extract_int64(const std::string& line, const char* key, int64_t& out) {
  double v = 0.0;
  if (!extract_number(line, key, v)) {
    return false;
  }
  out = static_cast<int64_t>(v);
  return true;
}

bool extract_int(const std::string& line, const char* key, int& out) {
  double v = 0.0;
  if (!extract_number(line, key, v)) {
    return false;
  }
  out = static_cast<int>(v);
  return true;
}

}  // namespace

std::vector<FrameDetections> read_detections_jsonl(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("failed to open detections: " + path);
  }
  std::vector<FrameDetections> frames;
  std::string line;
  while (std::getline(in, line)) {
    line = trim(line);
    if (line.empty()) {
      continue;
    }
    FrameDetections fd;
    // Minimal parse: frame + t. Detection array ignored for M0 passthrough.
    if (!extract_int64(line, "frame", fd.frame)) {
      fd.frame = static_cast<int64_t>(frames.size());
    }
    if (!extract_number(line, "t", fd.t)) {
      fd.t = 0.0;
    }
    frames.push_back(std::move(fd));
  }
  return frames;
}

void write_tracks_jsonl(const std::string& path,
                        const std::vector<FrameTracks>& frames) {
  std::ofstream out(path);
  if (!out) {
    throw std::runtime_error("failed to open tracks output: " + path);
  }
  // Deterministic: write frames in input order; tracks array empty for M0.
  for (const auto& f : frames) {
    out << "{\"frame\":" << f.frame << ",\"t\":" << f.t << ",\"tracks\":[]}\n";
  }
}

void write_timing_json(const std::string& path, std::size_t num_frames) {
  std::ofstream out(path);
  if (!out) {
    throw std::runtime_error("failed to open timing output: " + path);
  }
  out << "{\"total_ms\":0,\"frames\":" << num_frames << ",\"ms_per_frame\":[]}\n";
}

TrackerConfig load_config(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("failed to open config: " + path);
  }
  std::ostringstream ss;
  ss << in.rdbuf();
  const std::string body = ss.str();

  TrackerConfig cfg;
  // Optional keys; defaults remain if absent.
  extract_int(body, "promote_hits", cfg.promote_hits);
  extract_int(body, "coast_frames", cfg.coast_frames);
  extract_number(body, "gate_m", cfg.gate_m);
  extract_int(body, "seed", cfg.seed);
  return cfg;
}

}  // namespace trackbench
