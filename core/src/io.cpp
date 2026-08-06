#include "trackbench/io.hpp"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

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

bool extract_string(const std::string& obj, const char* key, std::string& out) {
  const std::string needle = std::string("\"") + key + "\"";
  auto pos = obj.find(needle);
  if (pos == std::string::npos) {
    return false;
  }
  auto i = pos + needle.size();
  while (i < obj.size() && std::isspace(static_cast<unsigned char>(obj[i]))) {
    ++i;
  }
  if (i >= obj.size() || obj[i] != ':') {
    return false;
  }
  ++i;
  while (i < obj.size() && std::isspace(static_cast<unsigned char>(obj[i]))) {
    ++i;
  }
  if (i >= obj.size() || obj[i] != '"') {
    return false;
  }
  ++i;
  std::string value;
  while (i < obj.size() && obj[i] != '"') {
    if (obj[i] == '\\' && i + 1 < obj.size()) {
      value.push_back(obj[i + 1]);
      i += 2;
      continue;
    }
    value.push_back(obj[i]);
    ++i;
  }
  out = std::move(value);
  return true;
}

Detection parse_detection_object(const std::string& obj) {
  Detection d;
  extract_string(obj, "cls", d.cls);
  extract_number(obj, "x", d.x);
  extract_number(obj, "y", d.y);
  extract_number(obj, "z", d.z);
  extract_number(obj, "l", d.l);
  extract_number(obj, "w", d.w);
  extract_number(obj, "h", d.h);
  extract_number(obj, "yaw", d.yaw);
  extract_number(obj, "score", d.score);
  return d;
}

/// Parse JSON array of detection objects from a frame line.
std::vector<Detection> parse_dets_array(const std::string& line) {
  std::vector<Detection> dets;
  const std::string key = "\"dets\"";
  auto pos = line.find(key);
  if (pos == std::string::npos) {
    // Fall back to "detections"
    pos = line.find("\"detections\"");
    if (pos == std::string::npos) {
      return dets;
    }
  }
  auto i = line.find('[', pos);
  if (i == std::string::npos) {
    return dets;
  }
  ++i;
  while (i < line.size()) {
    while (i < line.size() &&
           (std::isspace(static_cast<unsigned char>(line[i])) || line[i] == ',')) {
      ++i;
    }
    if (i >= line.size() || line[i] == ']') {
      break;
    }
    if (line[i] != '{') {
      ++i;
      continue;
    }
    const auto start = i;
    int depth = 0;
    for (; i < line.size(); ++i) {
      if (line[i] == '{') {
        ++depth;
      } else if (line[i] == '}') {
        --depth;
        if (depth == 0) {
          ++i;
          break;
        }
      }
    }
    dets.push_back(parse_detection_object(line.substr(start, i - start)));
  }
  return dets;
}

}  // namespace

std::string format_json_double(double v) {
  if (!std::isfinite(v)) {
    return "0";
  }
  char buf[64];
  // Enough digits for round-trip; deterministic across glibc platforms.
  std::snprintf(buf, sizeof(buf), "%.12g", v);
  return std::string(buf);
}

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
    if (!extract_int64(line, "frame", fd.frame)) {
      fd.frame = static_cast<int64_t>(frames.size());
    }
    if (!extract_number(line, "t", fd.t)) {
      fd.t = 0.0;
    }
    fd.detections = parse_dets_array(line);
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
  for (const auto& f : frames) {
    out << "{\"frame\":" << f.frame << ",\"t\":" << format_json_double(f.t)
        << ",\"tracks\":[";
    for (std::size_t i = 0; i < f.tracks.size(); ++i) {
      const Track& tr = f.tracks[i];
      if (i > 0) {
        out << ',';
      }
      out << "{\"id\":" << tr.id << ",\"cls\":\"" << tr.cls << "\""
          << ",\"x\":" << format_json_double(tr.x)
          << ",\"y\":" << format_json_double(tr.y)
          << ",\"yaw\":" << format_json_double(tr.yaw)
          << ",\"vx\":" << format_json_double(tr.vx)
          << ",\"vy\":" << format_json_double(tr.vy)
          << ",\"state\":\"" << track_state_string(tr.state) << "\""
          << ",\"age\":" << tr.age
          << ",\"cov_trace\":" << format_json_double(tr.cov_trace) << '}';
    }
    out << "]}\n";
  }
}

void write_timing_json(const std::string& path, double total_ms,
                       const std::vector<double>& ms_per_frame) {
  std::ofstream out(path);
  if (!out) {
    throw std::runtime_error("failed to open timing output: " + path);
  }
  out << "{\"total_ms\":" << format_json_double(total_ms) << ",\"frames\":"
      << ms_per_frame.size() << ",\"ms_per_frame\":[";
  for (std::size_t i = 0; i < ms_per_frame.size(); ++i) {
    if (i > 0) {
      out << ',';
    }
    out << format_json_double(ms_per_frame[i]);
  }
  out << "]}\n";
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
  extract_int(body, "promote_hits", cfg.promote_hits);
  extract_int(body, "coast_frames", cfg.coast_frames);
  extract_number(body, "gate_m", cfg.gate_m);
  extract_number(body, "gate_mahalanobis", cfg.gate_mahalanobis);
  extract_int(body, "seed", cfg.seed);
  extract_number(body, "process_var_pos", cfg.process_var_pos);
  extract_number(body, "process_var_vel", cfg.process_var_vel);
  extract_number(body, "process_var_yaw", cfg.process_var_yaw);
  extract_number(body, "meas_var_pos", cfg.meas_var_pos);
  extract_number(body, "meas_var_yaw", cfg.meas_var_yaw);
  return cfg;
}

}  // namespace trackbench
