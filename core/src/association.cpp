#include "trackbench/association.hpp"

namespace trackbench {

std::vector<Association> associate(
    const std::vector<Track>& /*tracks*/,
    const std::vector<Detection>& /*detections*/,
    double /*gate_m*/) {
  // M0 stub: no associations. Later: Mahalanobis gate + Hungarian/greedy
  // with stable_sort on costs for determinism.
  return {};
}

}  // namespace trackbench
