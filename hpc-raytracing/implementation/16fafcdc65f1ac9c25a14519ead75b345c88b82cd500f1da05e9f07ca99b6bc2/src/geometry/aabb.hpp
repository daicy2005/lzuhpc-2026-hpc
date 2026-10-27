#pragma once

#include <algorithm>
#include <cmath>
#include <limits>

#include "geometry/ray.hpp"
#include "math/interval.hpp"
#include "render/diagnostics.hpp"

class aabb
{
public:
    struct prepared_ray
    {
        point3 origin;
        vec3 direction, inverse;
        bool parallel[3];

        explicit prepared_ray(const ray &r) : origin(r.origin()), direction(r.direction())
        {
            for(int axis = 0; axis < 3; ++axis)
            {
                parallel[axis] = direction[axis] == 0;
                inverse[axis] = parallel[axis] ? 0 : 1.0 / direction[axis];
            }
        }
    };
    point3 lo{infinity, infinity, infinity};
    point3 hi{-infinity, -infinity, -infinity};

    aabb() = default;
    aabb(point3 minimum, point3 maximum) : lo(minimum), hi(maximum) {}

    void include(const aabb &other)
    {
        for(int axis = 0; axis < 3; ++axis)
        {
            lo[axis] = std::min(lo[axis], other.lo[axis]);
            hi[axis] = std::max(hi[axis], other.hi[axis]);
        }
    }

    bool hit(const ray &r, interval range, double &entry) const
    {
        return hit(prepared_ray(r), range, entry);
    }

    bool hit(const prepared_ray &r, interval range, double &entry) const
    {
#ifdef RT_DIAGNOSTIC
        ++diagnostic_boxes;
#endif
        for(int axis = 0; axis < 3; ++axis)
        {
            const double origin = r.origin[axis];
            if(r.parallel[axis])
            {
                if(origin < lo[axis] || origin > hi[axis])
                    return false;
                continue;
            }
            const bool finite_inverse = std::isfinite(r.inverse[axis]);
            double near = finite_inverse ? (lo[axis] - origin) * r.inverse[axis]
                                         : (lo[axis] - origin) / r.direction[axis];
            double far = finite_inverse ? (hi[axis] - origin) * r.inverse[axis]
                                        : (hi[axis] - origin) / r.direction[axis];
            if(near > far)
                std::swap(near, far);
            // Pad subtraction/reciprocal/multiplication roundoff conservatively.
            // Non-finite endpoint arithmetic disables culling on this axis.
            const double padding = 8 * std::numeric_limits<double>::epsilon() *
                                   std::max(std::abs(near), std::abs(far));
            if(std::isfinite(padding))
            {
                near -= padding;
                far += padding;
            }
            else
            {
                near = -infinity;
                far = infinity;
            }
            range.min = std::max(range.min, near);
            range.max = std::min(range.max, far);
            if(range.max < range.min)
                return false;
        }
        entry = range.min;
        return true;
    }
};
