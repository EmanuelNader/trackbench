#pragma once

#include <array>
#include <chrono>
#include <cstdint>

namespace trackbench {
namespace timing {

enum class StageTimings : uint8_t {
  DT = 0,
  PREDICT,
  BUILD_ACTIVE,
  COST_MATRIX_CONSTRUCT,
  ASSOCIATION_SOLVE,
  UPDATE,
  BIRTH,
  COAST_KILL,
  COMPACT,
  SORT_EMIT,
  TOTAL,
  COUNT
};

/// Per-frame stage timing accumulator, indexed by StageTimings (ns).
using StageNs = std::array<uint64_t, static_cast<size_t>(StageTimings::COUNT)>;

#ifdef TRACKBENCH_STAGE_TIMING

class ScopedTimer {
 public:
  explicit ScopedTimer(StageNs& timings, StageTimings stage)
      : timings_(timings), stage_(stage), start_(std::chrono::steady_clock::now()) {}

  ~ScopedTimer() {
    auto end = std::chrono::steady_clock::now();
    auto elapsed_ns =
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - start_).count();
    timings_[static_cast<size_t>(stage_)] += static_cast<uint64_t>(elapsed_ns);
  }

  ScopedTimer(const ScopedTimer&) = delete;
  ScopedTimer& operator=(const ScopedTimer&) = delete;
  ScopedTimer(ScopedTimer&&) = delete;
  ScopedTimer& operator=(ScopedTimer&&) = delete;

 private:
  StageNs& timings_;
  StageTimings stage_;
  std::chrono::steady_clock::time_point start_;
};

#else

struct ScopedTimer {
  explicit ScopedTimer(StageNs&, StageTimings) {}
  ~ScopedTimer() = default;
  ScopedTimer(const ScopedTimer&) = delete;
  ScopedTimer& operator=(const ScopedTimer&) = delete;
  ScopedTimer(ScopedTimer&&) = delete;
  ScopedTimer& operator=(ScopedTimer&&) = delete;
};

#endif

}  // namespace timing
}  // namespace trackbench
