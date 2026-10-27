#pragma once

#ifdef RT_DIAGNOSTIC
#include <cstdint>
// Diagnostic builds are explicitly restricted to one rendering thread.
inline std::uint64_t diagnostic_rays = 0;
inline std::uint64_t diagnostic_spheres = 0;
inline std::uint64_t diagnostic_boxes = 0;
inline std::uint64_t diagnostic_records = 0;
#endif
