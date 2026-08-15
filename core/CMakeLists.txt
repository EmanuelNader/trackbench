cmake_minimum_required(VERSION 3.16)
project(trackbench_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Default ON so Debug/CI builds get GoogleTest without extra flags.
option(TRACKBENCH_BUILD_TESTS "Build GoogleTest unit tests" ON)
option(TRACKBENCH_STAGE_TIMING "Enable per-stage timing instrumentation" OFF)

# Scalar precision of the EKF state/covariance. 'double' (default) is the
# baseline golden-precision build; 'float' compiles the filter in single
# precision. Plumbed to the trackbench library as PUBLIC TRACKBENCH_REAL=<type>
# (+ TRACKBENCH_PRECISION_FLOAT when float) so the test binary and
# trackbench_run inherit it.
set(TRACKBENCH_PRECISION "double" CACHE STRING "tracker scalar precision: double|float")
if(NOT TRACKBENCH_PRECISION STREQUAL "double" AND NOT TRACKBENCH_PRECISION STREQUAL "float")
  message(FATAL_ERROR "TRACKBENCH_PRECISION must be 'double' or 'float', got '${TRACKBENCH_PRECISION}'")
endif()

include(FetchContent)

# Eigen3 (header-only). Prefer system package; else FetchContent headers only.
find_package(Eigen3 3.3 QUIET NO_MODULE)
if(NOT Eigen3_FOUND)
  FetchContent_Declare(
    eigen
    GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
    GIT_TAG        3.4.0
    GIT_SHALLOW    TRUE
  )
  FetchContent_GetProperties(eigen)
  if(NOT eigen_POPULATED)
    FetchContent_Populate(eigen)
  endif()
  add_library(Eigen3::Eigen INTERFACE IMPORTED)
  target_include_directories(Eigen3::Eigen INTERFACE ${eigen_SOURCE_DIR})
endif()

add_library(trackbench STATIC
  src/ekf.cpp
  src/association.cpp
  src/track.cpp
  src/tracker.cpp
  src/io.cpp
)
target_include_directories(trackbench
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
if(TRACKBENCH_STAGE_TIMING)
  target_compile_definitions(trackbench PUBLIC TRACKBENCH_STAGE_TIMING)
endif()
target_compile_definitions(trackbench PUBLIC TRACKBENCH_REAL=${TRACKBENCH_PRECISION})
if(TRACKBENCH_PRECISION STREQUAL "float")
  target_compile_definitions(trackbench PUBLIC TRACKBENCH_PRECISION_FLOAT)
endif()
target_link_libraries(trackbench
  PUBLIC
    Eigen3::Eigen
)

add_executable(trackbench_run src/main.cpp)
target_link_libraries(trackbench_run PRIVATE trackbench)

if(TRACKBENCH_BUILD_TESTS)
  enable_testing()

  set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.14.0
    GIT_SHALLOW    TRUE
  )
  # Avoid overriding parent compiler/linker settings on Windows.
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  set(TRACKBENCH_FIXTURE_DIR
      "${CMAKE_SOURCE_DIR}/../data/fixtures/synthetic_scene_001")
  set(TRACKBENCH_CONFIG_PATH "${CMAKE_SOURCE_DIR}/config/default.json")

  add_executable(trackbench_tests
    tests/test_smoke.cpp
    tests/test_timed_smoke.cpp
    tests/test_ekf.cpp
    tests/test_hungarian.cpp
    tests/test_lifecycle.cpp
    tests/test_crossing.cpp
    tests/test_velocity_gate.cpp
    tests/test_bev_iou.cpp
    tests/test_golden.cpp
  )
  target_link_libraries(trackbench_tests
    PRIVATE
      trackbench
      GTest::gtest_main
  )
  target_compile_definitions(trackbench_tests
    PRIVATE
      TRACKBENCH_FIXTURE_DIR="${TRACKBENCH_FIXTURE_DIR}"
      TRACKBENCH_CONFIG_PATH="${TRACKBENCH_CONFIG_PATH}"
  )
  if(TRACKBENCH_STAGE_TIMING)
    target_compile_definitions(trackbench_tests PRIVATE TRACKBENCH_STAGE_TIMING)
  endif()
  # The double golden fixture is byte-compare only meaningful at double
  # precision; under float the synthetic bytes differ by design. Exclude the
  # Golden.* cases for the float build so `ctest -E golden` (single test
  # binary) does not fail on the expected byte divergence.
  if(TRACKBENCH_PRECISION STREQUAL "float")
    add_test(NAME trackbench_unit COMMAND trackbench_tests --gtest_filter=-Golden.*)
  else()
    add_test(NAME trackbench_unit COMMAND trackbench_tests)
  endif()
endif()
