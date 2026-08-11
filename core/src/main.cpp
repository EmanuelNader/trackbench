#include <chrono>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "trackbench/io.hpp"
#include "trackbench/tracker.hpp"

namespace {

#ifdef TRACKBENCH_STAGE_TIMING
constexpr trackbench::timing::StageTimings kStageColumns[] = {
    trackbench::timing::StageTimings::DT,
    trackbench::timing::StageTimings::PREDICT,
    trackbench::timing::StageTimings::BUILD_ACTIVE,
    trackbench::timing::StageTimings::COST_MATRIX_CONSTRUCT,
    trackbench::timing::StageTimings::ASSOCIATION_SOLVE,
    trackbench::timing::StageTimings::UPDATE,
    trackbench::timing::StageTimings::BIRTH,
    trackbench::timing::StageTimings::COAST_KILL,
    trackbench::timing::StageTimings::COMPACT,
    trackbench::timing::StageTimings::SORT_EMIT,
    trackbench::timing::StageTimings::TOTAL,
};
#endif

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
      << "  --timing-csv PATH   Output per-frame stage timings CSV (requires TRACKBENCH_STAGE_TIMING build)\n"
      << "  --help          Show this help\n";
}

bool eq(const char* a, const char* b) { return std::strcmp(a, b) == 0; }

}  // namespace

int main(int argc, char** argv) {
  std::string dets_path;
  std::string config_path;
  std::string out_path;
  std::string timing_path;
  std::string timing_csv_path;

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
    } else if (eq(argv[i], "--timing-csv")) {
      timing_csv_path = need("--timing-csv");
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

#ifndef TRACKBENCH_STAGE_TIMING
  if (!timing_csv_path.empty()) {
    std::cerr
        << "--timing-csv requires rebuild with -DTRACKBENCH_STAGE_TIMING=ON; no CSV emitted\n";
    return 0;
  }
#endif

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

#ifdef TRACKBENCH_STAGE_TIMING
    if (!timing_csv_path.empty()) {
      std::ofstream csv(timing_csv_path);
      if (!csv.is_open()) {
        throw std::runtime_error("cannot open --timing-csv file: " +
                                 timing_csv_path);
      }
      csv << "frame,scene_id,n_active,n_dets,dt_ns,predict_ns,"
             "build_active_ns,cost_matrix_construct_ns,association_solve_ns,"
             "update_ns,birth_ns,coast_kill_ns,compact_ns,sort_emit_ns,"
             "total_ns\n";
      const auto& ft = tracker.frame_timings();
      for (size_t i = 0; i < ft.size() && i < frames.size(); ++i) {
        csv << i << ',' << frames[i].frame << ','
            << outs[i].tracks.size() << ',' << frames[i].detections.size();
        const auto& fti = ft[i];
        for (const auto st : kStageColumns) {
          csv << ',' << fti[static_cast<size_t>(st)];
        }
        csv << '\n';
      }
      csv.close();
      if (!csv) {
        throw std::runtime_error("failed to flush --timing-csv file: " +
                                 timing_csv_path);
      }
    }
#endif
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }

  return 0;
}
