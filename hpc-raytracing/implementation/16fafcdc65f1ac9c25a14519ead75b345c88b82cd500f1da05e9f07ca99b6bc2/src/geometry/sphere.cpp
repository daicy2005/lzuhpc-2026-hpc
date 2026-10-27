#include "geometry/sphere.hpp"

bool sphere::hit(const ray &r, interval ray_t, hit_record &rec) const
{
    double distance;
    if(!hit_distance(r, ray_t, distance))
        return false;
    complete_hit(r, distance, rec);
    return true;
}

bool sphere::hit_distance(const ray &r, interval ray_t, double &distance) const
{
#ifdef RT_DIAGNOSTIC
    ++diagnostic_spheres;
#endif
    vec3 oc = center - r.origin();
    auto a = r.direction().length_squared();
    auto h = dot(r.direction(), oc);
    auto c = oc.length_squared() - radius * radius;

    auto discriminant = h * h - a * c;
    if(discriminant < 0)
        return false;

    auto sqrtd = std::sqrt(discriminant);

    // Find the nearest root that lies in the acceptable range.
    auto root = (h - sqrtd) / a;
    if(!ray_t.surrounds(root))
    {
        root = (h + sqrtd) / a;
        if(!ray_t.surrounds(root))
            return false;
    }

    distance = root;
    return true;
}

void sphere::complete_hit(const ray &r, double distance, hit_record &rec) const
{
#ifdef RT_DIAGNOSTIC
    ++diagnostic_records;
#endif
    rec.t = distance;
    rec.p = r.at(rec.t);
    vec3 outward_normal = (rec.p - center) / radius;
    rec.set_face_normal(r, outward_normal);
    rec.mat = mat;

}
