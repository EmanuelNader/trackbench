#include "trackbench/ekf.hpp"

namespace trackbench {

void Ekf::predict(Track& track, double dt) const {
  // M0 stub: constant-velocity coast in BEV (no covariance update yet).
  track.x += track.vx * dt;
  track.y += track.vy * dt;
  ++track.age;
}

void Ekf::update(Track& track, const Detection& det) const {
  // M0 stub: hard assign measurement; real Kalman gain later.
  track.x = det.x;
  track.y = det.y;
  track.yaw = det.yaw;
  track.cls = det.cls;
}

}  // namespace trackbench
