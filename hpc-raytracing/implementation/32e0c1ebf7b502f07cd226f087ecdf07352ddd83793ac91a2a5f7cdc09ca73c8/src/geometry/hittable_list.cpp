#include "geometry/hittable_list.hpp"
#include "render/settings.hpp"

#include <algorithm>
#include <numeric>

void hittable_list::initialize()
{
    nodes.clear();
    const auto mode = setting_text("RT_ACCEL", "median");
    if(mode != "linear" && mode != "median")
        throw std::invalid_argument("RT_ACCEL must be linear or median");
    if(mode == "linear" || objects.empty())
        return;
    leaf_size = setting_int("RT_LEAF_SIZE", 8);
    order.resize(objects.size());
    std::iota(order.begin(), order.end(), std::size_t{0});
    nodes.reserve(2 * objects.size());
    build_node(0, order.size());
}

aabb hittable_list::bounds() const
{
    aabb box;
    for(const auto &object : objects)
        box.include(object->bounds());
    return box;
}

int hittable_list::build_node(std::size_t begin, std::size_t end)
{
    const int index = static_cast<int>(nodes.size());
    nodes.emplace_back();
    aabb box;
    point3 minimum(infinity, infinity, infinity), maximum(-infinity, -infinity, -infinity);
    for(std::size_t i = begin; i < end; ++i)
    {
        const aabb object_box = objects[order[i]]->bounds();
        box.include(object_box);
        const point3 center = 0.5 * (object_box.lo + object_box.hi);
        for(int axis = 0; axis < 3; ++axis)
        {
            minimum[axis] = std::min(minimum[axis], center[axis]);
            maximum[axis] = std::max(maximum[axis], center[axis]);
        }
    }
    nodes[index].box = box;
    nodes[index].begin = begin;
    nodes[index].end = end;
    if(end - begin <= static_cast<std::size_t>(leaf_size))
        return index;
    const vec3 span = maximum - minimum;
    int axis = span[1] > span[0] ? 1 : 0;
    if(span[2] > span[axis])
        axis = 2;
    std::stable_sort(order.begin() + begin, order.begin() + end, [&](std::size_t a, std::size_t b)
    {
        const aabb first = objects[a]->bounds(), second = objects[b]->bounds();
        const double ca = first.lo[axis] + first.hi[axis];
        const double cb = second.lo[axis] + second.hi[axis];
        return ca == cb ? a < b : ca < cb;
    });
    const auto middle = begin + (end - begin) / 2;
    const int left = build_node(begin, middle);
    const int right = build_node(middle, end);
    nodes[index].left = left;
    nodes[index].right = right;
    return index;
}

bool hittable_list::hit_node(int index, const ray &r, const aabb::prepared_ray &box_ray, interval original, double &closest,
                             std::size_t &best_id, hit_record &rec) const
{
    const auto &current = nodes[index];
    // The parent has already checked this node. The root is checked by hit().
    bool found = false;
    if(current.left < 0)
    {
        hit_record candidate;
        for(std::size_t position = current.begin; position < current.end; ++position)
        {
            const auto id = order[position];
            // Permit an exact equal-distance candidate only when it had original priority.
            const double limit = best_id < objects.size() && id < best_id
                ? std::nextafter(closest, infinity) : closest;
            if(objects[id]->hit(r, interval(original.min, limit), candidate) &&
               (candidate.t < closest || (candidate.t == closest && id < best_id)))
            {
                closest = candidate.t;
                best_id = id;
                rec = candidate;
                found = true;
            }
        }
        return found;
    }
    double left_entry = infinity, right_entry = infinity;
    const bool left_hit = nodes[current.left].box.hit(box_ray, interval(original.min, closest), left_entry);
    const bool right_hit = nodes[current.right].box.hit(box_ray, interval(original.min, closest), right_entry);
    if(right_entry < left_entry)
    {
        if(right_hit) found |= hit_node(current.right, r, box_ray, original, closest, best_id, rec);
        if(left_hit && left_entry <= closest) found |= hit_node(current.left, r, box_ray, original, closest, best_id, rec);
    }
    else
    {
        if(left_hit) found |= hit_node(current.left, r, box_ray, original, closest, best_id, rec);
        if(right_hit && right_entry <= closest) found |= hit_node(current.right, r, box_ray, original, closest, best_id, rec);
    }
    return found;
}

bool hittable_list::hit(const ray &r, interval ray_t, hit_record &rec) const
{
    if(!nodes.empty())
    {
        double closest = ray_t.max;
        double entry;
        const aabb::prepared_ray box_ray(r);
        if(!nodes[0].box.hit(box_ray, ray_t, entry))
            return false;
        std::size_t best_id = objects.size();
        return hit_node(0, r, box_ray, ray_t, closest, best_id, rec);
    }
    hit_record temp_rec;
    bool hit_anything = false;
    auto closest_so_far = ray_t.max;

    for(const auto &object : objects)
    {
        if(object->hit(r, interval(ray_t.min, closest_so_far), temp_rec))
        {
            hit_anything = true;
            closest_so_far = temp_rec.t;
            rec = temp_rec;
        }
    }

    return hit_anything;
}
