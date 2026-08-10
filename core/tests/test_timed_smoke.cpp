#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>

#include "trackbench/timing.hpp"
#include "trackbench/tracker.hpp"
#include "trackbench/types.hpp"

#ifdef TRACKBENCH_STAGE_TIMING

namespace {

constexpr std::size_t kNumStages =
    static_cast<std::size_t>(trackbench::timing::StageTimings::COUNT);
constexpr std::size_t kTotalIdx =
    static_cast<std::size_t>(trackbench::timing::StageTimings::TOTAL);

/// 5 "car" detections drifting +0.05 m/step (0.5 m/s). On odd frames the last
/// detection is dropped so one track coasts (exercises COAST_KILL without
/// ever dying, since coast_frames = 5 > consecutive misses = 1).
trackbench::FrameDetections MakeFrame(int64_t frame) {
  trackbench::FrameDetections f;
  f.frame = frame;
  f.t = 0.1 * frame;
  const int count = (frame % 2 == 1) ? 4 : 5;
  f.detections.reserve(count);
  for (int i = 0; i < count; ++i) {
    trackbench::Detection d;
    d.cls = "car";
    d.x = 2.0 + i + 0.05 * frame;
    d.y = -1.0 + i * 0.5;
    d.z = 0.0;
    d.l = 4.5;
    d.w = 1.9;
    d.h = 1.5;
    d.yaw = 0.0;
    d.score = 0.9;
    f.detections.push_back(d);
  }
  return f;
}

}  // namespace

TEST(TimedSmoke, StageTimingsPartitionTotal) {
  constexpr int kNumSteps = 30;

  trackbench::Tracker tracker;
  for (int i = 0; i < kNumSteps; ++i) {
    tracker.step(MakeFrame(i));
  }

  const auto& timings = tracker.frame_timings();
  ASSERT_EQ(timings.size(), static_cast<std::size_t>(kNumSteps));

  // Every stage timer must have fired and recorded > 0 in at least one frame.
  // A single frame can legitimately read 0 ns for sub-tick stages (e.g. DT,
  // whose cost is one clock read on a ~41 ns mach timebase tick), so a
  // stage that fires will still exceed 0 at least once across the run.
  std::array<uint64_t, kNumStages> max_ns{};
  for (const auto& f : timings) {
    for (std::size_t i = 0; i < kTotalIdx; ++i) {
      max_ns[i] = std::max(max_ns[i], f[i]);
    }
  }
  for (std::size_t i = 0; i < kTotalIdx; ++i) {
    EXPECT_GT(max_ns[i], 0);
  }

  // The LAST frame's stage times should approximately partition TOTAL.
  const auto& last = timings.back();
  const uint64_t total = last[kTotalIdx];
  EXPECT_GT(total, 0);

  uint64_t sum = 0;
  for (std::size_t i = 0; i < kTotalIdx; ++i) {
    sum += last[i];
  }
  EXPECT_LT(std::abs(static_cast<double>(sum) - static_cast<double>(total)) /
                static_cast<double>(total),
            0.05);
}

#endif  // TRACKBENCH_STAGE_TIMING
