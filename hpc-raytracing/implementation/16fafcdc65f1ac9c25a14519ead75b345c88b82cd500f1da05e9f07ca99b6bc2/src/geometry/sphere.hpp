#pragma once

#include <cmath>

#include "geometry/hittable.hpp"
#include "math/vec3.hpp"

class sphere : public hittable
{
public:
    sphere(const point3 &center, double radius, shared_ptr<material> mat)
        : center(center), radius(std::fmax(0, radius)), mat(std::move(mat))
    {
    }

    bool hit(const ray &r, interval ray_t, hit_record &rec) const override;
    bool hit_distance(const ray &r, interval ray_t, double &distance) const;
    void complete_hit(const ray &r, double distance, hit_record &rec) const;

    aabb bounds() const override
    {
        point3 minimum = center - vec3(radius, radius, radius);
        point3 maximum = center + vec3(radius, radius, radius);
        for(int axis = 0; axis < 3; ++axis)
        {
            minimum[axis] = std::nextafter(minimum[axis], -infinity);
            maximum[axis] = std::nextafter(maximum[axis], infinity);
        }
        return aabb(minimum, maximum);
    }

private:
    point3 center;
    double radius;
    shared_ptr<material> mat;
};
