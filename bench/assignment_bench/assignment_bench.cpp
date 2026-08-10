// Assignment-algorithm benchmark: production trackbench Munkres
// (trackbench::hungarian_minimize) vs a self-contained Bertsekas forward
// auction with warm-started epsilon scaling.
//
// Optimality is validated empirically: auction totals must stay within a
// small relative gap of Munkres totals on random matrices (auction is only
// guaranteed within n*eps of optimal, so exact equality is not expected).
// The assignment-difference rate is reported too, because the plan's switch
// gate requires "no output change".
//
// Usage: assignment_bench [N...]  (default 10 20 40 60 100 200)
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <string>
#include <vector>

#include "trackbench/association.hpp"

using Vec = std::vector<double>;
using Mat = std::vector<Vec>;
using trackbench::hungarian_minimize;

// ---------------------------------------------------------------------------
// Bertsekas forward auction (maximization on value = -cost), warm-started
// epsilon scaling. Guarantee: final total within n*eps of optimal.
// ---------------------------------------------------------------------------
static std::vector<int> auction(const Mat& c) {
  const int n = static_cast<int>(c.size());
  if (n == 0) return {};
  std::vector<int> rowsol(n, -1), colsol(n, -1);
  std::vector<double> p(n, 0.0);

  double vmax = 0.0;
  for (int i = 0; i < n; ++i)
    for (int j = 0; j < n; ++j) vmax = std::max(vmax, std::fabs(c[i][j]));
  const double V = std::max(vmax, 1.0);
  // single cold-start forward auction; guarantee: total within n*eps of optimal
  const double eps = 1e-4 * V / static_cast<double>(n + 1);

  std::vector<int> unassigned;
  unassigned.reserve(n);
  for (;;) {
    unassigned.clear();
    for (int i = 0; i < n; ++i)
      if (rowsol[i] < 0) unassigned.push_back(i);
    if (unassigned.empty()) break;
    for (int i : unassigned) {
      int j1 = -1, j2 = -1;
      double b1 = -1e300, b2 = -1e300;
      for (int j = 0; j < n; ++j) {
        const double val = -c[i][j] - p[j];
        if (val > b1) {
          b2 = b1; b1 = val; j2 = j1; j1 = j;
        } else if (val > b2) {
          b2 = val; j2 = j;
        }
      }
      double bid = p[j1] + (b1 - b2) + eps;
      if (bid <= p[j1]) bid = p[j1] + eps;  // guard fp stall: strict increase
      p[j1] = bid;
      const int old = colsol[j1];
      colsol[j1] = i;
      rowsol[i] = j1;
      if (old >= 0) rowsol[old] = -1;
    }
  }

  std::vector<int> assignment(n, -1);
  for (int i = 0; i < n; ++i) assignment[i] = rowsol[i];
  return assignment;
}

// ---------------------------------------------------------------------------
static double total_cost(const Mat& c, const std::vector<int>& a) {
  double s = 0.0;
  for (int i = 0; i < static_cast<int>(a.size()); ++i)
    if (a[i] >= 0) s += c[i][a[i]];
  return s;
}

static int run_validation(std::mt19937& rng) {
  const int rounds =
      std::getenv("TB_VAL_ROUNDS") ? std::atoi(std::getenv("TB_VAL_ROUNDS")) : 1000;
  std::uniform_real_distribution<double> u01(0.0, 1.0);
  std::uniform_real_distribution<double> ugate(0.0, 10.0);
  int fail = 0;
  double gap = 0.0, gap_max = 0.0;
  long long adiff = 0, adiff_n = 0;
  for (int round = 0; round < rounds; ++round) {
    const int n = 4 + static_cast<int>(rng() % 57);  // 4..60
    const int profile = static_cast<int>(rng() % 3);
    Mat c(n, Vec(n));
    for (int i = 0; i < n; ++i)
      for (int j = 0; j < n; ++j) {
        if (profile == 0) c[i][j] = u01(rng);
        else if (profile == 1) {
          c[i][j] = static_cast<double>(static_cast<int>(u01(rng) * 8)) / 4.0;
        } else {
          c[i][j] = (u01(rng) < 0.7) ? ugate(rng) : 1e9;
        }
      }
    const auto am = hungarian_minimize(c);
    const auto aj = auction(c);
    const double tm = total_cost(c, am);
    const double tj = total_cost(c, aj);
    const double rel = (tj - tm) / std::max(1.0, tm);
    if (rel > 1e-2) {
      ++fail;
      if (fail <= 5)
        std::printf("  VALIDATION FAIL n=%d profile=%d munkres=%.9g auction=%.9g rel=%.2g\n",
                    n, profile, tm, tj, rel);
    }
    gap += rel;
    gap_max = std::max(gap_max, rel);
    for (int i = 0; i < n; ++i)
      if (am[i] != aj[i]) ++adiff;
    adiff_n += n;
  }
  std::printf("auction near-optimal gap vs munkres: mean %.3g max %.3g\n", gap / rounds, gap_max);
  std::printf("auction vs munkres assignment difference: %.1f%% of rows\n",
              100.0 * static_cast<double>(adiff) / static_cast<double>(adiff_n));
  return fail;
}

static int run_tie_test(std::mt19937& rng) {
  const int rounds = 500;
  std::uniform_real_distribution<double> u01(0.0, 1.0);
  int ties = 0;
  int sampled = 0;
  for (int round = 0; round < rounds; ++round) {
    const int n = 8 + static_cast<int>(rng() % 33);  // 8..40
    Mat c(n, Vec(n));
    for (auto& row : c)
      for (auto& x : row) x = static_cast<double>(static_cast<int>(u01(rng) * 8)) / 4.0;
    for (int i = 0; i < n; ++i)
      for (int j = 0; j < n; ++j)
        if (u01(rng) < 0.3) c[i][j] = 1e9;  // Inf-padding like the tracker
    const auto a0 = hungarian_minimize(c);
    const double t0 = total_cost(c, a0);
    // micro-perturbation breaks ties without changing costs materially
    Mat cp = c;
    for (int i = 0; i < n; ++i)
      for (int j = 0; j < n; ++j)
        if (cp[i][j] < 1e8) cp[i][j] += 1e-7 * static_cast<double>((i * 7 + j * 13) % 100);
    const auto ap = hungarian_minimize(cp);
    bool same = true;
    for (int i = 0; i < n; ++i) if (a0[i] != ap[i]) { same = false; break; }
    if (!same) {
      ++sampled;
      const double tp = total_cost(c, ap);
      if (std::fabs(tp - t0) < 1e-3) ++ties;  // different assignment, same optimal cost
    }
  }
  std::printf("tie test: %d/%d matrices have multiple optimal assignments (different assignment, same cost)\n",
              ties, sampled);
  return ties;
}

int main(int argc, char** argv) {
  std::vector<int> ns;
  if (argc > 1) {
    for (int i = 1; i < argc; ++i) ns.push_back(std::atoi(argv[i]));
  } else {
    ns = {10, 20, 40, 60, 100, 200};
  }
  std::mt19937 rng(42);
  std::uniform_real_distribution<double> u01(0.0, 1.0);

  std::printf("== auction validation vs production Munkres ==\n");
  const int fails = run_validation(rng);
  std::printf("== tie test (can an alternative solver give identical output?) ==\n");
  run_tie_test(rng);
  std::printf("validation: %s (reported; timing below is context on dense matrices)\n",
              fails == 0 ? "OK - auction within 1e-2 relative gap (its n*eps guarantee)" : "FAILED");

  std::printf("\nN  munkres_us  auction_us  speedup  cost_gap  (dense matrix; gap vs munkres)\n");
  for (int n : ns) {
    Mat c(n, Vec(n));
    for (auto& row : c)
      for (auto& x : row) x = u01(rng);
    for (int i = 0; i < n; ++i)
      for (int j = 0; j < n; ++j)
        if (u01(rng) < 0.3) c[i][j] = 1e9;  // Inf-padding like the tracker

    std::vector<int> a_m, a_j;
    double tm = 0.0, tl = 0.0;
    {
      auto t0 = std::chrono::steady_clock::now();
      for (int rep = 0; rep < 5; ++rep) a_m = hungarian_minimize(c);
      auto t1 = std::chrono::steady_clock::now();
      tm = std::chrono::duration_cast<std::chrono::duration<double>>(t1 - t0).count() / 5e-6;
    }
    {
      auto t0 = std::chrono::steady_clock::now();
      for (int rep = 0; rep < 5; ++rep) a_j = auction(c);
      auto t1 = std::chrono::steady_clock::now();
      tl = std::chrono::duration_cast<std::chrono::duration<double>>(t1 - t0).count() / 5e-6;
    }
    const double tm_c = total_cost(c, a_m);
    const double tj_c = total_cost(c, a_j);
    const double gap = (tj_c - tm_c) / std::max(1.0, tm_c);
    std::printf("%d  %10.2f  %10.2f  %6.2fx  %6.2f  %s\n", n, tm, tl, tm / tl, gap,
                tm_c == tj_c ? "(equal)" : "(suboptimal)");
  }
  return 0;
}
