#include <gtest/gtest.h>

#include <vector>

#include "trackbench/association.hpp"

TEST(Hungarian, MatchesHandComputed3x3) {
  // Cost matrix:
  //       d0   d1   d2
  // t0:  1.0  2.0  3.0
  // t1:  3.0  1.0  2.0
  // t2:  2.0  3.0  1.0
  // Optimal assignment (unique): (0,0), (1,1), (2,2) with total cost 3.
  const std::vector<std::vector<double>> cost = {
      {1.0, 2.0, 3.0},
      {3.0, 1.0, 2.0},
      {2.0, 3.0, 1.0},
  };

  const std::vector<int> assign = trackbench::hungarian_minimize(cost);
  ASSERT_EQ(assign.size(), 3u);
  EXPECT_EQ(assign[0], 0);
  EXPECT_EQ(assign[1], 1);
  EXPECT_EQ(assign[2], 2);
}

TEST(Hungarian, StableTieBreakPrefersLowerIndices) {
  // All feasible costs equal → prefer (track0→det0), (track1→det1).
  const std::vector<std::vector<double>> cost = {
      {1.0, 1.0},
      {1.0, 1.0},
  };
  const std::vector<int> assign = trackbench::hungarian_minimize(cost);
  ASSERT_EQ(assign.size(), 2u);
  EXPECT_EQ(assign[0], 0);
  EXPECT_EQ(assign[1], 1);
}

TEST(Hungarian, RejectsInfAssignments) {
  const std::vector<std::vector<double>> cost = {
      {1.0, trackbench::kCostInf},
      {trackbench::kCostInf, trackbench::kCostInf},
  };
  const std::vector<int> assign = trackbench::hungarian_minimize(cost);
  ASSERT_EQ(assign.size(), 2u);
  EXPECT_EQ(assign[0], 0);
  EXPECT_EQ(assign[1], -1);
}

// ---- Greedy solver tests ----

TEST(Greedy, MatchesHandComputed3x3) {
  // Same matrix as the Hungarian test. The greedy solver should find the
  // same optimal assignment here because the diagonal is strictly cheapest
  // for each row and no row has two equally-cheap candidates.
  const std::vector<std::vector<double>> cost = {
      {1.0, 2.0, 3.0},
      {3.0, 1.0, 2.0},
      {2.0, 3.0, 1.0},
  };
  const std::vector<int> assign = trackbench::greedy_minimize(cost);
  ASSERT_EQ(assign.size(), 3u);
  EXPECT_EQ(assign[0], 0);
  EXPECT_EQ(assign[1], 1);
  EXPECT_EQ(assign[2], 2);
}

TEST(Greedy, StableTieBreakPrefersLowerIndices) {
  // All feasible costs equal → prefer (track0→det0), (track1→det1).
  const std::vector<std::vector<double>> cost = {
      {1.0, 1.0},
      {1.0, 1.0},
  };
  const std::vector<int> assign = trackbench::greedy_minimize(cost);
  ASSERT_EQ(assign.size(), 2u);
  EXPECT_EQ(assign[0], 0);
  EXPECT_EQ(assign[1], 1);
}

TEST(Greedy, RejectsInfAssignments) {
  const std::vector<std::vector<double>> cost = {
      {1.0, trackbench::kCostInf},
      {trackbench::kCostInf, trackbench::kCostInf},
  };
  const std::vector<int> assign = trackbench::greedy_minimize(cost);
  ASSERT_EQ(assign.size(), 2u);
  EXPECT_EQ(assign[0], 0);
  EXPECT_EQ(assign[1], -1);
}

TEST(Greedy, GreedyDiffersFromHungarianOnAdversarial) {
  // A 3×3 matrix where greedy and Hungarian produce different assignments.
  // Matrix:
  //   d0    d1    d2
  // t0:  1     2     3
  // t1:  1   100   100
  // t2:100     1   100
  //
  // Greedy (cheapest first): (0,0)=1, then (1,0) col0 taken → skip,
  // then (2,1)=1, then (0,1) both taken → ... (1,2)=100. Total = 102.
  // Hungarian (globally optimal): (0,2)=3, (1,0)=1, (2,1)=1. Total = 5.
  const std::vector<std::vector<double>> cost = {
      {1.0, 2.0, 3.0},
      {1.0, 100.0, 100.0},
      {100.0, 1.0, 100.0},
  };
  const std::vector<int> hun = trackbench::hungarian_minimize(cost);
  const std::vector<int> gr = trackbench::greedy_minimize(cost);
  ASSERT_EQ(hun.size(), 3u);
  ASSERT_EQ(gr.size(), 3u);
  double hun_total = 0.0;
  for (int i = 0; i < 3; ++i) {
    if (hun[i] >= 0) {
      hun_total += cost[static_cast<std::size_t>(i)]
                        [static_cast<std::size_t>(hun[i])];
    }
  }
  EXPECT_DOUBLE_EQ(hun_total, 5.0);
  double gr_total = 0.0;
  for (int i = 0; i < 3; ++i) {
    if (gr[i] >= 0) {
      gr_total += cost[static_cast<std::size_t>(i)]
                      [static_cast<std::size_t>(gr[i])];
    }
  }
  EXPECT_DOUBLE_EQ(gr_total, 102.0);
}
