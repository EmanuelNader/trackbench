#include "trackbench/association.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace trackbench {
namespace {

/// Pad cost to square with kCostInf; run Munkres; return row→col (-1 if Inf).
/// Tie-breaking: always scan in increasing index order and take the first
/// minimum / first zero, which prefers lower track index then lower det index.
std::vector<int> munkres(std::vector<std::vector<double>> cost) {
  const int n_rows = static_cast<int>(cost.size());
  if (n_rows == 0) {
    return {};
  }
  const int n_cols = static_cast<int>(cost[0].size());
  const int n = std::max(n_rows, n_cols);

  // Square pad.
  cost.resize(static_cast<std::size_t>(n),
              std::vector<double>(static_cast<std::size_t>(n), kCostInf));
  for (int i = 0; i < n; ++i) {
    cost[static_cast<std::size_t>(i)].resize(static_cast<std::size_t>(n),
                                             kCostInf);
  }

  // Row reduction.
  for (int i = 0; i < n; ++i) {
    double min_v = cost[static_cast<std::size_t>(i)][0];
    for (int j = 1; j < n; ++j) {
      min_v = std::min(min_v, cost[static_cast<std::size_t>(i)]
                                   [static_cast<std::size_t>(j)]);
    }
    if (min_v < kCostInf * 0.5) {
      for (int j = 0; j < n; ++j) {
        cost[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
            min_v;
      }
    }
  }

  // Column reduction.
  for (int j = 0; j < n; ++j) {
    double min_v = cost[0][static_cast<std::size_t>(j)];
    for (int i = 1; i < n; ++i) {
      min_v = std::min(min_v, cost[static_cast<std::size_t>(i)]
                                   [static_cast<std::size_t>(j)]);
    }
    if (min_v < kCostInf * 0.5) {
      for (int i = 0; i < n; ++i) {
        cost[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
            min_v;
      }
    }
  }

  std::vector<int> row_star(static_cast<std::size_t>(n), -1);
  std::vector<int> col_star(static_cast<std::size_t>(n), -1);
  std::vector<int> row_prime(static_cast<std::size_t>(n), -1);
  std::vector<char> col_covered(static_cast<std::size_t>(n), 0);
  std::vector<char> row_covered(static_cast<std::size_t>(n), 0);

  auto is_zero = [&](int i, int j) {
    return std::fabs(cost[static_cast<std::size_t>(i)]
                          [static_cast<std::size_t>(j)]) < 1e-12;
  };

  // Star independent zeros (prefer lower i, then lower j).
  for (int i = 0; i < n; ++i) {
    for (int j = 0; j < n; ++j) {
      if (is_zero(i, j) && row_star[static_cast<std::size_t>(i)] < 0 &&
          col_star[static_cast<std::size_t>(j)] < 0) {
        row_star[static_cast<std::size_t>(i)] = j;
        col_star[static_cast<std::size_t>(j)] = i;
      }
    }
  }

  auto cover_starred_columns = [&]() {
    std::fill(col_covered.begin(), col_covered.end(), 0);
    for (int j = 0; j < n; ++j) {
      if (col_star[static_cast<std::size_t>(j)] >= 0) {
        col_covered[static_cast<std::size_t>(j)] = 1;
      }
    }
  };

  cover_starred_columns();

  auto covered_column_count = [&]() {
    int c = 0;
    for (int j = 0; j < n; ++j) {
      if (col_covered[static_cast<std::size_t>(j)]) {
        ++c;
      }
    }
    return c;
  };

  while (covered_column_count() < n) {
    // Find an uncovered zero; prime it. Prefer lower i, then lower j.
    int zero_r = -1;
    int zero_c = -1;
    for (int i = 0; i < n && zero_r < 0; ++i) {
      if (row_covered[static_cast<std::size_t>(i)]) {
        continue;
      }
      for (int j = 0; j < n; ++j) {
        if (!col_covered[static_cast<std::size_t>(j)] && is_zero(i, j)) {
          zero_r = i;
          zero_c = j;
          break;
        }
      }
    }

    if (zero_r < 0) {
      // Adjust: smallest uncovered value.
      double min_v = std::numeric_limits<double>::infinity();
      for (int i = 0; i < n; ++i) {
        if (row_covered[static_cast<std::size_t>(i)]) {
          continue;
        }
        for (int j = 0; j < n; ++j) {
          if (col_covered[static_cast<std::size_t>(j)]) {
            continue;
          }
          min_v = std::min(min_v, cost[static_cast<std::size_t>(i)]
                                       [static_cast<std::size_t>(j)]);
        }
      }
      if (!std::isfinite(min_v)) {
        break;
      }
      for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
          if (row_covered[static_cast<std::size_t>(i)]) {
            cost[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] +=
                min_v;
          }
          if (!col_covered[static_cast<std::size_t>(j)]) {
            cost[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
                min_v;
          }
        }
      }
      continue;
    }

    row_prime[static_cast<std::size_t>(zero_r)] = zero_c;
    const int star_col = row_star[static_cast<std::size_t>(zero_r)];
    if (star_col < 0) {
      // Augment along alternating path.
      int r = zero_r;
      int c = zero_c;
      while (true) {
        const int star_row = col_star[static_cast<std::size_t>(c)];
        row_star[static_cast<std::size_t>(r)] = c;
        col_star[static_cast<std::size_t>(c)] = r;
        if (star_row < 0) {
          break;
        }
        r = star_row;
        c = row_prime[static_cast<std::size_t>(r)];
      }
      std::fill(row_prime.begin(), row_prime.end(), -1);
      std::fill(row_covered.begin(), row_covered.end(), 0);
      cover_starred_columns();
    } else {
      row_covered[static_cast<std::size_t>(zero_r)] = 1;
      col_covered[static_cast<std::size_t>(star_col)] = 0;
    }
  }

  std::vector<int> assignment(static_cast<std::size_t>(n_rows), -1);
  for (int i = 0; i < n_rows; ++i) {
    const int j = row_star[static_cast<std::size_t>(i)];
    if (j >= 0 && j < n_cols) {
      assignment[static_cast<std::size_t>(i)] = j;
    }
  }
  return assignment;
}

}  // namespace

std::vector<int> hungarian_minimize(
    const std::vector<std::vector<double>>& cost) {
  if (cost.empty()) {
    return {};
  }
  // Work on a copy; reject Inf assignments after solve using original costs.
  std::vector<int> assignment = munkres(cost);
  for (std::size_t i = 0; i < assignment.size(); ++i) {
    const int j = assignment[i];
    if (j < 0) {
      continue;
    }
    if (j >= static_cast<int>(cost[i].size()) ||
        cost[i][static_cast<std::size_t>(j)] >= kCostInf * 0.5) {
      assignment[i] = -1;
    }
  }
  return assignment;
}

std::vector<Association> associate(const std::vector<Track>& tracks,
                                   const std::vector<Detection>& detections,
                                   const Ekf& ekf) {
  std::vector<Association> matches;
  if (tracks.empty() || detections.empty()) {
    return matches;
  }

  const auto& cfg = ekf.config();
  const std::size_t n_t = tracks.size();
  const std::size_t n_d = detections.size();

  std::vector<std::vector<double>> cost(
      n_t, std::vector<double>(n_d, kCostInf));

  for (std::size_t i = 0; i < n_t; ++i) {
    const Track& tr = tracks[i];
    if (tr.state == TrackState::DEAD) {
      continue;
    }
    for (std::size_t j = 0; j < n_d; ++j) {
      const Detection& det = detections[j];
      if (tr.cls != det.cls) {
        continue;
      }
      const double dx = det.x - tr.x;
      const double dy = det.y - tr.y;
      const double dist = std::sqrt(dx * dx + dy * dy);
      if (dist > cfg.gate_m) {
        continue;
      }
      const double m2 = ekf.mahalanobis_pos_squared(tr, det);
      if (!(m2 <= cfg.gate_mahalanobis)) {
        continue;
      }
      cost[i][j] = m2;
    }
  }

  const std::vector<int> assignment = hungarian_minimize(cost);
  matches.reserve(n_t);
  for (std::size_t i = 0; i < assignment.size(); ++i) {
    const int j = assignment[i];
    if (j >= 0) {
      matches.emplace_back(i, static_cast<std::size_t>(j));
    }
  }

  // Stable order: by track index then detection index (already by track index).
  std::stable_sort(matches.begin(), matches.end(),
                   [](const Association& a, const Association& b) {
                     if (a.first != b.first) {
                       return a.first < b.first;
                     }
                     return a.second < b.second;
                   });
  return matches;
}

}  // namespace trackbench
