#include "trackbench/association.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <string>
#include <utility>
#include <vector>

#include "trackbench/timing.hpp"

namespace trackbench {
namespace {

/// Linearization factor for 2-D grid-cell keys: key = cx * kGridKeyScale + cy.
/// Distinct (cx, cy) map to distinct int64 keys as long as |cy| < scale,
/// which holds for any realistic coordinate range.
constexpr int64_t kGridKeyScale = int64_t{1} << 32;

int64_t grid_cell_key(int64_t cx, int64_t cy) {
  return cx * kGridKeyScale + cy;
}

std::array<Vec2, 4> oriented_box_corners(double cx, double cy, double l,
                                         double w, double yaw) {
  const double hl = 0.5 * l;
  const double hw = 0.5 * w;
  const double c = std::cos(yaw);
  const double s = std::sin(yaw);
  // Local corners CCW (y-up): BR → TR → TL → BL.
  const std::array<Vec2, 4> local = {
      {{hl, -hw}, {hl, hw}, {-hl, hw}, {-hl, -hw}}};
  std::array<Vec2, 4> world{};
  for (std::size_t i = 0; i < 4; ++i) {
    world[i].x = cx + c * local[i].x - s * local[i].y;
    world[i].y = cy + s * local[i].x + c * local[i].y;
  }
  return world;
}

double polygon_area(const std::vector<Vec2>& poly) {
  if (poly.size() < 3) {
    return 0.0;
  }
  double a = 0.0;
  for (std::size_t i = 0; i < poly.size(); ++i) {
    const Vec2& p = poly[i];
    const Vec2& q = poly[(i + 1) % poly.size()];
    a += p.x * q.y - q.x * p.y;
  }
  return 0.5 * std::fabs(a);
}

/// Cross product (b-a) × (c-a).
double cross(const Vec2& a, const Vec2& b, const Vec2& c) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

Vec2 line_intersect(const Vec2& a, const Vec2& b, const Vec2& c, const Vec2& d) {
  // Intersection of infinite lines ab and cd.
  const double a1 = b.y - a.y;
  const double b1 = a.x - b.x;
  const double c1 = a1 * a.x + b1 * a.y;
  const double a2 = d.y - c.y;
  const double b2 = c.x - d.x;
  const double c2 = a2 * c.x + b2 * c.y;
  const double det = a1 * b2 - a2 * b1;
  if (std::fabs(det) < 1e-15) {
    return a;
  }
  return {(b2 * c1 - b1 * c2) / det, (a1 * c2 - a2 * c1) / det};
}

/// Clip subject polygon by one half-plane to the left of directed edge p→q,
/// writing the result into `out` (reusing its storage).
void clip_edge_into(const std::vector<Vec2>& subject, const Vec2& p,
                    const Vec2& q, std::vector<Vec2>& out) {
  out.clear();
  if (subject.empty()) {
    return;
  }
  if (out.capacity() < subject.size() + 2) {
    out.reserve(subject.size() + 2);
  }
  for (std::size_t i = 0; i < subject.size(); ++i) {
    const Vec2& cur = subject[i];
    const Vec2& prev = subject[(i + subject.size() - 1) % subject.size()];
    const double cur_in = cross(p, q, cur);
    const double prev_in = cross(p, q, prev);
    const bool cur_inside = cur_in >= -1e-12;
    const bool prev_inside = prev_in >= -1e-12;
    if (cur_inside) {
      if (!prev_inside) {
        out.push_back(line_intersect(prev, cur, p, q));
      }
      out.push_back(cur);
    } else if (prev_inside) {
      out.push_back(line_intersect(prev, cur, p, q));
    }
  }
}

/// Convex intersection of boxes a and b, reusing `buf_a`/`buf_b` as ping-pong
/// clip buffers. Returns a reference to the buffer holding the result.
const std::vector<Vec2>& convex_intersection(const std::array<Vec2, 4>& a,
                                             const std::array<Vec2, 4>& b,
                                             std::vector<Vec2>& buf_a,
                                             std::vector<Vec2>& buf_b) {
  buf_a.assign(a.begin(), a.end());
  std::vector<Vec2>* cur = &buf_a;
  std::vector<Vec2>* nxt = &buf_b;
  for (std::size_t i = 0; i < 4 && !cur->empty(); ++i) {
    clip_edge_into(*cur, b[i], b[(i + 1) % 4], *nxt);
    std::swap(cur, nxt);
  }
  return *cur;
}

/// Munkres / Hungarian minimization on `scratch.cost` (n_t × n_d), mutating
/// the square-padded `scratch.work` copy in place. Reuses all working arrays
/// across calls. On return `scratch.assignment` holds row → column (-1 when
/// the star was outside the real column count); Inf rejection happens in the
/// caller using the untouched original `scratch.cost`.
void munkres_scratch(AssociateScratch& scratch) {
  const auto& cost = scratch.cost;
  const int n_rows = static_cast<int>(cost.size());
  if (n_rows == 0) {
    scratch.assignment.clear();
    return;
  }
  const int n_cols = static_cast<int>(cost[0].size());
  const int n = std::max(n_rows, n_cols);

  // Square pad (reuses `work` storage; every live cell is rewritten so the
  // contents are identical to a freshly allocated padded copy).
  auto& work = scratch.work;
  work.resize(static_cast<std::size_t>(n));
  for (int i = 0; i < n; ++i) {
    auto& row = work[static_cast<std::size_t>(i)];
    row.resize(static_cast<std::size_t>(n));
    for (int j = 0; j < n; ++j) {
      row[static_cast<std::size_t>(j)] =
          (i < n_rows && j < n_cols)
              ? cost[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)]
              : kCostInf;
    }
  }

  // Row reduction.
  for (int i = 0; i < n; ++i) {
    double min_v = work[static_cast<std::size_t>(i)][0];
    for (int j = 1; j < n; ++j) {
      min_v = std::min(min_v, work[static_cast<std::size_t>(i)]
                                   [static_cast<std::size_t>(j)]);
    }
    if (min_v < kCostInf * 0.5) {
      for (int j = 0; j < n; ++j) {
        work[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
            min_v;
      }
    }
  }

  // Column reduction.
  for (int j = 0; j < n; ++j) {
    double min_v = work[0][static_cast<std::size_t>(j)];
    for (int i = 1; i < n; ++i) {
      min_v = std::min(min_v, work[static_cast<std::size_t>(i)]
                                   [static_cast<std::size_t>(j)]);
    }
    if (min_v < kCostInf * 0.5) {
      for (int i = 0; i < n; ++i) {
        work[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
            min_v;
      }
    }
  }

  auto& row_star = scratch.row_star;
  auto& col_star = scratch.col_star;
  auto& row_prime = scratch.row_prime;
  auto& col_covered = scratch.col_covered;
  auto& row_covered = scratch.row_covered;
  row_star.assign(static_cast<std::size_t>(n), -1);
  col_star.assign(static_cast<std::size_t>(n), -1);
  row_prime.assign(static_cast<std::size_t>(n), -1);
  col_covered.assign(static_cast<std::size_t>(n), 0);
  row_covered.assign(static_cast<std::size_t>(n), 0);

  auto is_zero = [&](int i, int j) {
    return std::fabs(work[static_cast<std::size_t>(i)]
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
          min_v = std::min(min_v, work[static_cast<std::size_t>(i)]
                                        [static_cast<std::size_t>(j)]);
        }
      }
      if (!std::isfinite(min_v)) {
        break;
      }
      for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
          if (row_covered[static_cast<std::size_t>(i)]) {
            work[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] +=
                min_v;
          }
          if (!col_covered[static_cast<std::size_t>(j)]) {
            work[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
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

  scratch.assignment.assign(static_cast<std::size_t>(n_rows), -1);
  for (int i = 0; i < n_rows; ++i) {
    const int j = row_star[static_cast<std::size_t>(i)];
    if (j >= 0 && j < n_cols) {
      scratch.assignment[static_cast<std::size_t>(i)] = j;
    }
  }
}

double bev_oriented_iou_scratch(double x1, double y1, double l1, double w1,
                                double yaw1, double x2, double y2, double l2,
                                double w2, double yaw2,
                                std::vector<Vec2>& buf_a,
                                std::vector<Vec2>& buf_b) {
  if (!(l1 > 0.0 && w1 > 0.0 && l2 > 0.0 && w2 > 0.0)) {
    return 0.0;
  }
  const double area1 = l1 * w1;
  const double area2 = l2 * w2;
  if (!(area1 > 0.0 && area2 > 0.0)) {
    return 0.0;
  }

  const auto c1 = oriented_box_corners(x1, y1, l1, w1, yaw1);
  const auto c2 = oriented_box_corners(x2, y2, l2, w2, yaw2);
  const double inter =
      polygon_area(convex_intersection(c1, c2, buf_a, buf_b));
  const double uni = area1 + area2 - inter;
  if (!(uni > 1e-12) || !(inter >= 0.0)) {
    return 0.0;
  }
  double iou = inter / uni;
  if (iou < 0.0) {
    iou = 0.0;
  } else if (iou > 1.0) {
    iou = 1.0;
  }
  return iou;
}

}  // namespace

void resolve_box_size(const std::string& cls, double& l, double& w) {
  double def_l = 4.5;
  double def_w = 1.8;
  if (cls == "pedestrian") {
    def_l = 0.8;
    def_w = 0.6;
  } else if (cls == "bicycle" || cls == "motorcycle") {
    def_l = 1.8;
    def_w = 0.6;
  }
  if (!(l > 0.0)) {
    l = def_l;
  }
  if (!(w > 0.0)) {
    w = def_w;
  }
}

double bev_oriented_iou(double x1, double y1, double l1, double w1, double yaw1,
                        double x2, double y2, double l2, double w2,
                        double yaw2) {
  std::vector<Vec2> buf_a;
  std::vector<Vec2> buf_b;
  return bev_oriented_iou_scratch(x1, y1, l1, w1, yaw1, x2, y2, l2, w2, yaw2,
                                  buf_a, buf_b);
}

std::vector<int> hungarian_minimize(
    const std::vector<std::vector<double>>& cost) {
  if (cost.empty()) {
    return {};
  }
  // Work on a scratch copy; reject Inf assignments after solve using original
  // costs.
  AssociateScratch scratch;
  scratch.cost = cost;
  munkres_scratch(scratch);
  auto& assignment = scratch.assignment;
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
  return std::move(assignment);
}

void associate_to(const std::vector<Track>& tracks,
                  const std::vector<Detection>& detections, const Ekf& ekf,
                  AssociateScratch& scratch,
                                   timing::StageNs* timings) {
  auto& matches = scratch.matches;
  matches.clear();
  if (tracks.empty() || detections.empty()) {
    return;
  }

  const auto& cfg = ekf.config();
  const std::size_t n_t = tracks.size();
  const std::size_t n_d = detections.size();

  auto& cost = scratch.cost;
  cost.resize(n_t);
  for (std::size_t i = 0; i < n_t; ++i) {
    cost[i].resize(n_d);
    std::fill(cost[i].begin(), cost[i].end(), kCostInf);
  }

  // Time the gated cost-matrix build and the Hungarian solve into *timings
  // when provided. ScopedTimer is a no-op when TRACKBENCH_STAGE_TIMING is off;
  // the local fallback array keeps a null timings pointer well-defined.
  timing::StageNs dummy_timings{};
  timing::StageNs& timings_ref = timings ? *timings : dummy_timings;

  {
    timing::ScopedTimer timer_cost(timings_ref,
                                   timing::StageTimings::COST_MATRIX_CONSTRUCT);

    // Spatial prefilter (conservative, uniform grid over detection
    // positions). For each track only the grid cells whose extent can
    // intersect the track's Euclidean gate disk (radius cfg.gate_m) are
    // visited, so every pair that can receive a finite cost is still
    // evaluated while far pairs skip the per-pair gate. dist <= cfg.gate_m
    // implies |det - track| <= cfg.gate_m per axis, and the 1e-6 m pad on the
    // search radius is a strict superset of the exact gate predicate (covers
    // floating-point boundary error), so the candidate set can only over-
    // include. The per-pair gate below is unchanged and re-checks every
    // candidate, making the resulting cost matrix (and the assignment)
    // bit-identical to the full O(n_t x n_d) build.
    auto& grid = scratch.grid;
    for (auto& kv : grid) {
      kv.second.clear();
    }
    grid.reserve(n_d);
    const double R_grid = cfg.gate_m + 1e-6;
    const double cell = 2.0 * R_grid;
    for (std::size_t j = 0; j < n_d; ++j) {
      const Detection& det = detections[j];
      const int64_t cx = static_cast<int64_t>(std::floor(det.x / cell));
      const int64_t cy = static_cast<int64_t>(std::floor(det.y / cell));
      grid[grid_cell_key(cx, cy)].push_back(j);
    }

    for (std::size_t i = 0; i < n_t; ++i) {
      const Track& tr = tracks[i];
      if (tr.state == TrackState::DEAD) {
        continue;
      }
      const int64_t cx_min =
          static_cast<int64_t>(std::floor((tr.x - R_grid) / cell));
      const int64_t cx_max =
          static_cast<int64_t>(std::floor((tr.x + R_grid) / cell));
      const int64_t cy_min =
          static_cast<int64_t>(std::floor((tr.y - R_grid) / cell));
      const int64_t cy_max =
          static_cast<int64_t>(std::floor((tr.y + R_grid) / cell));
      for (int64_t cx = cx_min; cx <= cx_max; ++cx) {
        for (int64_t cy = cy_min; cy <= cy_max; ++cy) {
          auto it = grid.find(grid_cell_key(cx, cy));
          if (it == grid.end()) {
            continue;
          }
          for (const std::size_t j : it->second) {
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

            // Soft velocity penalty (M6): prefer associations aligned with
            // motion without hard-rejecting (hard gates increased IDS/FN on
            // mini).
            double cost_ij = m2;
            const double speed = std::hypot(tr.vx, tr.vy);
            if (tr.hits >= 2 && speed >= cfg.vel_gate_min_speed &&
                cfg.vel_gate_lateral_m > 0.0 && cfg.vel_cost_weight > 0.0) {
              const double ux = tr.vx / speed;
              const double uy = tr.vy / speed;
              const double lat = std::fabs(-uy * dx + ux * dy);
              const double lat_n = lat / cfg.vel_gate_lateral_m;
              cost_ij += cfg.vel_cost_weight * lat_n * lat_n;
            }

            // Soft BEV IoU term: prefer high-overlap boxes in dense parallel
            // traffic.
            if (cfg.iou_weight > 0.0) {
              double tl = tr.l;
              double tw = tr.w;
              double dl = det.l;
              double dw = det.w;
              resolve_box_size(tr.cls, tl, tw);
              resolve_box_size(det.cls, dl, dw);
              const double iou = bev_oriented_iou_scratch(
                  tr.x, tr.y, tl, tw, tr.yaw, det.x, det.y, dl, dw, det.yaw,
                  scratch.clip_a, scratch.clip_b);
              cost_ij += cfg.iou_weight * (1.0 - iou);
            }

            cost[i][j] = cost_ij;
          }
        }
      }
    }
  }

  {
    timing::ScopedTimer timer_solve(timings_ref,
                                    timing::StageTimings::ASSOCIATION_SOLVE);
    munkres_scratch(scratch);
  }

  // Reject Inf assignments against the untouched original cost matrix.
  auto& assignment = scratch.assignment;
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
}

std::vector<Association> associate(const std::vector<Track>& tracks,
                                   const std::vector<Detection>& detections,
                                   const Ekf& ekf,
                  timing::StageNs* timings) {
  AssociateScratch scratch;
  associate_to(tracks, detections, ekf, scratch, timings);
  return std::move(scratch.matches);
}

}  // namespace trackbench
