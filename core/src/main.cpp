#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#include "trackbench/io.hpp"
#include "trackbench/tracker.hpp"

namespace {

void print_usage(const char* argv0) {
  std::cerr
      << "Usage: " << argv0
      << " --dets path --config path --out path --timing path\n"
      << "\n"
      << "Run the deterministic EKF multi-object tracker on detections.jsonl.\n"
      << "\n"
      << "Options:\n"
      << "  --dets PATH     Input detections JSONL\n"
      << "  --config PATH   Tracker config JSON\n"
      << "  --out PATH      Output tracks JSONL\n"
      << "  --timing PATH   Output timing JSON (per-frame wall ms)\n"
      << "  --help          Show this help\n";
}

bool eq(const char* a, const char* b) { return std::strcmp(a, b) == 0; }

}  // namespace

int main(int argc, char** argv) {
  std::string dets_path;
  std::string config_path;
  std::string out_path;
  std::string timing_path;

  for (int i = 1; i < argc; ++i) {
    if (eq(argv[i], "--help") || eq(argv[i], "-h")) {
      print_usage(argv[0]);
      return 0;
    }
    auto need = [&](const char* flag) -> std::string {
      if (i + 1 >= argc) {
        std::cerr << "Missing value for " << flag << "\n";
        print_usage(argv[0]);
        std::exit(2);
      }
      return argv[++i];
    };
    if (eq(argv[i], "--dets")) {
      dets_path = need("--dets");
    } else if (eq(argv[i], "--config")) {
      config_path = need("--config");
    } else if (eq(argv[i], "--out")) {
      out_path = need("--out");
    } else if (eq(argv[i], "--timing")) {
      timing_path = need("--timing");
    } else {
      std::cerr << "Unknown argument: " << argv[i] << "\n";
      print_usage(argv[0]);
      return 2;
    }
  }

  if (dets_path.empty() || config_path.empty() || out_path.empty() ||
      timing_path.empty()) {
    print_usage(argv[0]);
    return 2;
  }

  try {
    const trackbench::TrackerConfig config =
        trackbench::load_config(config_path);
    trackbench::Tracker tracker(config);

    std::vector<trackbench::FrameDetections> frames;
    try {
      frames = trackbench::read_detections_jsonl(dets_path);
    } catch (const std::exception&) {
      frames.clear();
    }

    std::vector<trackbench::FrameTracks> outs;
    std::vector<double> ms_per_frame;
    outs.reserve(frames.size());
    ms_per_frame.reserve(frames.size());

    const auto t0 = std::chrono::steady_clock::now();
    for (const auto& fd : frames) {
      const auto f0 = std::chrono::steady_clock::now();
      outs.push_back(tracker.step(fd));
      const auto f1 = std::chrono::steady_clock::now();
      const double ms =
          std::chrono::duration<double, std::milli>(f1 - f0).count();
      ms_per_frame.push_back(ms);
    }
    const auto t1 = std::chrono::steady_clock::now();
    const double total_ms =
        std::chrono::duration<double, std::milli>(t1 - t0).count();

    trackbench::write_tracks_jsonl(out_path, outs);
    trackbench::write_timing_json(timing_path, total_ms, ms_per_frame);
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }

  return 0;
}
