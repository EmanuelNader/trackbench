#include <gtest/gtest.h>

#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "trackbench/io.hpp"
#include "trackbench/tracker.hpp"

#ifndef TRACKBENCH_FIXTURE_DIR
#error "TRACKBENCH_FIXTURE_DIR must be defined"
#endif

#ifndef TRACKBENCH_CONFIG_PATH
#error "TRACKBENCH_CONFIG_PATH must be defined"
#endif

namespace {

std::string read_file(const std::string& path) {
  std::ifstream in(path);
  EXPECT_TRUE(in.good()) << "missing file: " << path;
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

std::vector<std::string> split_lines(const std::string& s) {
  std::vector<std::string> lines;
  std::istringstream in(s);
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }
    lines.push_back(line);
  }
  return lines;
}

}  // namespace

TEST(Golden, SyntheticScene001ByteIdentical) {
  const std::string dets_path =
      std::string(TRACKBENCH_FIXTURE_DIR) + "/detections.jsonl";
  const std::string expected_path =
      std::string(TRACKBENCH_FIXTURE_DIR) + "/tracks_expected.jsonl";
  const std::string config_path = TRACKBENCH_CONFIG_PATH;

  const auto cfg = trackbench::load_config(config_path);
  trackbench::Tracker tracker(cfg);
  const auto frames = trackbench::read_detections_jsonl(dets_path);

  std::vector<trackbench::FrameTracks> outs;
  outs.reserve(frames.size());
  for (const auto& fd : frames) {
    outs.push_back(tracker.step(fd));
  }

  const std::string tmp_path = "/tmp/trackbench_golden_got.jsonl";
  trackbench::write_tracks_jsonl(tmp_path, outs);

  const std::string got = read_file(tmp_path);
  const std::string expected = read_file(expected_path);

  // Prefer exact byte match; fall back message with line diff.
  if (got != expected) {
    const auto got_lines = split_lines(got);
    const auto exp_lines = split_lines(expected);
    EXPECT_EQ(got_lines.size(), exp_lines.size());
    const std::size_t n = std::min(got_lines.size(), exp_lines.size());
    for (std::size_t i = 0; i < n; ++i) {
      EXPECT_EQ(got_lines[i], exp_lines[i]) << "line " << (i + 1);
    }
  }
  EXPECT_EQ(got, expected);
}

TEST(Golden, DeterministicAcrossTwoRuns) {
  const std::string dets_path =
      std::string(TRACKBENCH_FIXTURE_DIR) + "/detections.jsonl";
  const auto cfg = trackbench::load_config(TRACKBENCH_CONFIG_PATH);
  const auto frames = trackbench::read_detections_jsonl(dets_path);

  auto run_once = [&]() {
    trackbench::Tracker tracker(cfg);
    std::vector<trackbench::FrameTracks> outs;
    for (const auto& fd : frames) {
      outs.push_back(tracker.step(fd));
    }
    const std::string path = "/tmp/trackbench_golden_det.jsonl";
    trackbench::write_tracks_jsonl(path, outs);
    return read_file(path);
  };

  EXPECT_EQ(run_once(), run_once());
}
