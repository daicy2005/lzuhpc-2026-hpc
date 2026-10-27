#pragma once

#include "geometry/hittable.hpp"

#include <vector>

class sphere;

class hittable_list : public hittable
{
public:
    std::vector<shared_ptr<hittable>> objects;

    hittable_list() {}
    hittable_list(const shared_ptr<hittable> &object)
    {
        add(object);
    }

    void clear()
    {
        objects.clear();
        nodes.clear();
        exact_spheres.clear();
    }

    void add(const shared_ptr<hittable> &object)
    {
        objects.push_back(object);
        nodes.clear();
        exact_spheres.clear();
    }

    void initialize();

    bool hit(const ray &r, interval ray_t, hit_record &rec) const override;

    aabb bounds() const override;

private:
    struct node
    {
        aabb box;
        std::size_t begin = 0, end = 0;
        int left = -1, right = -1;
    };
    std::vector<node> nodes;
    std::vector<std::size_t> order;
    // Original objects retain ownership; copies of the list share those owners.
    std::vector<const sphere *> exact_spheres;
    int leaf_size = 8;
    bool sah_builder = false;

    int build_node(std::size_t begin, std::size_t end);
    bool hit_node(int index, const ray &r, const aabb::prepared_ray &box_ray, interval original, double &closest,
                  std::size_t &best_id, hit_record &rec) const;
};
