#include "geometry/hittable_list.hpp"
#include "geometry/sphere.hpp"
#include "render/settings.hpp"

#include <algorithm>
#include <array>
#include <numeric>
#include <typeinfo>

void hittable_list::initialize()
{
    nodes.clear();
    exact_spheres.clear();
    const auto mode = setting_text("RT_ACCEL", "sah");
    if(mode != "linear" && mode != "median" && mode != "sah")
        throw std::invalid_argument("RT_ACCEL must be linear, median or sah");
    sah_builder = mode == "sah";
    if(mode == "linear" || objects.empty())
        return;
    leaf_size = setting_int("RT_LEAF_SIZE", 8);
    order.resize(objects.size());
    std::iota(order.begin(), order.end(), std::size_t{0});
    exact_spheres.reserve(objects.size());
    for(const auto &object : objects)
        exact_spheres.push_back(typeid(*object) == typeid(sphere) ? static_cast<const sphere *>(object.get()) : nullptr);
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
    if(sah_builder)
    {
        // A deterministic binned SAH: evaluate all axes; stable partition preserves
        // original order within equal-cost/equal-centroid groups.
        constexpr int bin_count = 16;
        struct bin { aabb box; std::size_t count = 0; };
        const auto area = [](const aabb &b) {
            const vec3 extent = b.hi - b.lo;
            return 2 * (extent[0] * extent[1] + extent[0] * extent[2] + extent[1] * extent[2]);
        };
        const auto bucket = [&](std::size_t id, int split_axis) {
            const auto bounds = objects[id]->bounds();
            const double center = 0.5 * (bounds.lo[split_axis] + bounds.hi[split_axis]);
            const double fraction = (center - minimum[split_axis]) / span[split_axis];
            return std::clamp(static_cast<int>(fraction * bin_count), 0, bin_count - 1);
        };
        double best_cost = infinity;
        int best_axis = -1, best_split = -1;
        for(int split_axis = 0; split_axis < 3; ++split_axis)
        {
            if(!(span[split_axis] > 0) || !std::isfinite(span[split_axis]))
                continue;
            std::array<bin, bin_count> bins;
            for(std::size_t i = begin; i < end; ++i)
            {
                auto &target = bins[bucket(order[i], split_axis)];
                target.box.include(objects[order[i]]->bounds());
                ++target.count;
            }
            std::array<aabb, bin_count> right_boxes;
            std::array<std::size_t, bin_count> right_counts{};
            aabb right_box;
            std::size_t right_count = 0;
            for(int b = bin_count - 1; b >= 0; --b)
            {
                if(bins[b].count) right_box.include(bins[b].box);
                right_count += bins[b].count;
                right_boxes[b] = right_box;
                right_counts[b] = right_count;
            }
            aabb left_box;
            std::size_t left_count = 0;
            for(int split = 0; split < bin_count - 1; ++split)
            {
                if(bins[split].count) left_box.include(bins[split].box);
                left_count += bins[split].count;
                if(!left_count || !right_counts[split + 1]) continue;
                const double cost = area(left_box) * static_cast<double>(left_count) +
                                    area(right_boxes[split + 1]) * static_cast<double>(right_counts[split + 1]);
                if(cost < best_cost)
                {
                    best_cost = cost;
                    best_axis = split_axis;
                    best_split = split;
                }
            }
        }
        if(best_axis >= 0)
        {
            const auto pivot = std::stable_partition(order.begin() + begin, order.begin() + end,
                [&](std::size_t id) { return bucket(id, best_axis) <= best_split; });
            const auto middle = static_cast<std::size_t>(pivot - order.begin());
            if(middle > begin && middle < end)
            {
                const int left = build_node(begin, middle);
                const int right = build_node(middle, end);
                nodes[index].left = left;
                nodes[index].right = right;
                return index;
            }
        }
        // Coincident centroids use the deterministic median fallback below.
    }
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
            double distance;
            bool accepted;
            if(exact_spheres[id])
                accepted = exact_spheres[id]->hit_distance(r, interval(original.min, limit), distance);
            else
            {
                accepted = objects[id]->hit(r, interval(original.min, limit), candidate);
                distance = accepted ? candidate.t : infinity;
            }
            if(accepted && (distance < closest || (distance == closest && id < best_id)))
            {
                closest = distance;
                best_id = id;
                if(!exact_spheres[id])
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
        const bool found = hit_node(0, r, box_ray, ray_t, closest, best_id, rec);
        if(found && exact_spheres[best_id])
            exact_spheres[best_id]->complete_hit(r, closest, rec);
        return found;
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
