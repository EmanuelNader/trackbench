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
