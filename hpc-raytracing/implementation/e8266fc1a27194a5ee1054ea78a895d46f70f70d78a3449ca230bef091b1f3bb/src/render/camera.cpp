#include <cmath>
#include <iostream>
#include <algorithm>
#include <omp.h>
#include <sched.h>
#ifdef RT_PHASE_DIAGNOSTIC
#include <time.h>
#endif

#include "material/material.hpp"
#include "math/color.hpp"
#include "render/camera.hpp"
#include "render/settings.hpp"

void camera::render(const hittable &world, std::ostream &out)
{
    out << "P3\n" << image_width << ' ' << image_height << "\n255\n";

    const auto scheduler = setting_text("RT_SCHEDULE", "tile");
    if(scheduler != "serial" && scheduler != "static" && scheduler != "dynamic" && scheduler != "tile")
        throw std::invalid_argument("RT_SCHEDULE must be serial, static, dynamic or tile");
    const int requested = setting_int("RT_THREADS", scheduler == "serial" ? 1 : omp_get_max_threads());
#ifdef RT_DIAGNOSTIC
    if(requested != 1)
        throw std::invalid_argument("diagnostic build requires one thread");
#endif
    if(scheduler == "serial" && requested != 1)
        throw std::invalid_argument("serial requires RT_THREADS=1");
    const int tile_width = setting_int("RT_TILE_WIDTH", 16);
    const int tile_height = setting_int("RT_TILE_HEIGHT", 8);
    const int chunk = setting_int("RT_CHUNK", 1);
    std::vector<color> pixels(static_cast<std::size_t>(image_width) * image_height);
    auto render_pixel = [&](int i, int j) {
            begin_pixel_random(static_cast<std::uint64_t>(j) * static_cast<std::uint64_t>(image_width) +
                               static_cast<std::uint64_t>(i));
            color pixel_color(0, 0, 0);
            for(int sample = 0; sample < samples_per_pixel; sample++)
            {
                ray r = get_ray(i, j);
                pixel_color += ray_color(r, max_depth, world);
            }
            pixels[static_cast<std::size_t>(j) * image_width + i] = pixel_samples_scale * pixel_color;
    };
    const bool tiled = scheduler == "tile";
    const int columns = tiled ? (image_width + tile_width - 1) / tile_width : 1;
    const int rows = tiled ? (image_height + tile_height - 1) / tile_height : image_height;
    omp_set_dynamic(0);
    omp_set_schedule(scheduler == "static" || scheduler == "serial" ? omp_sched_static : omp_sched_dynamic, chunk);
    int observed = 0;
    std::vector<int> actual_cpus(requested, -1), pinned(requested, 0);
#ifdef RT_PHASE_DIAGNOSTIC
    std::vector<double> thread_cpu(requested), thread_busy(requested);
    std::vector<std::uint64_t> thread_units(requested), thread_pixels(requested);
    const double compute_start = omp_get_wtime();
#endif
#pragma omp parallel num_threads(requested)
    {
        const int thread = omp_get_thread_num();
        actual_cpus[thread] = sched_getcpu();
        cpu_set_t mask;
        CPU_ZERO(&mask);
        if(sched_getaffinity(0, sizeof(mask), &mask) == 0)
            pinned[thread] = CPU_COUNT(&mask) == 1;
#pragma omp single
        observed = omp_get_num_threads();
#ifdef RT_PHASE_DIAGNOSTIC
        timespec cpu_start{}, cpu_end{};
        if(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_start) != 0)
            std::abort();
        const double busy_start = omp_get_wtime();
#pragma omp for schedule(runtime) nowait
#else
#pragma omp for schedule(runtime)
#endif
        for(int unit = 0; unit < rows * columns; ++unit)
        {
            const int x0 = tiled ? (unit % columns) * tile_width : 0;
            const int y0 = tiled ? (unit / columns) * tile_height : unit;
            const int x1 = tiled ? std::min(image_width, x0 + tile_width) : image_width;
            const int y1 = tiled ? std::min(image_height, y0 + tile_height) : y0 + 1;
#ifdef RT_PHASE_DIAGNOSTIC
            ++thread_units[thread];
            thread_pixels[thread] += static_cast<std::uint64_t>(x1 - x0) * (y1 - y0);
#endif
            for(int j = y0; j < y1; ++j)
                for(int i = x0; i < x1; ++i)
                    render_pixel(i, j);
        }
#ifdef RT_PHASE_DIAGNOSTIC
        thread_busy[thread] = omp_get_wtime() - busy_start;
        if(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_end) != 0)
            std::abort();
        thread_cpu[thread] = static_cast<double>(cpu_end.tv_sec - cpu_start.tv_sec) +
                             1e-9 * static_cast<double>(cpu_end.tv_nsec - cpu_start.tv_nsec);
#endif
    }
#ifdef RT_PHASE_DIAGNOSTIC
    const double compute_seconds = omp_get_wtime() - compute_start;
#endif
    std::clog << "RT_CONFIG threads=" << observed << " scheduler=" << scheduler
              << " acceleration=" << setting_text("RT_ACCEL", "sah")
              << " leaf=" << setting_int("RT_LEAF_SIZE", 8)
              << " chunk=" << chunk << " tile_width=" << tile_width << " tile_height=" << tile_height << '\n';
    std::clog << "RT_AFFINITY cpus=";
    for(int thread = 0; thread < observed; ++thread)
        std::clog << (thread ? "," : "") << actual_cpus[thread];
    std::clog << " pinned=";
    for(int thread = 0; thread < observed; ++thread)
        std::clog << (thread ? "," : "") << pinned[thread];
    std::clog << '\n';
#ifdef RT_PHASE_DIAGNOSTIC
    const double output_start = omp_get_wtime();
#endif
    for(int j = 0; j < image_height; ++j)
    {
        for(int i = 0; i < image_width; i++)
        {
            write_color(out, pixels[static_cast<std::size_t>(j) * image_width + i]);
        }
    }

#ifdef RT_PHASE_DIAGNOSTIC
    const double output_seconds = omp_get_wtime() - output_start;
    std::clog << "RT_PHASE compute_seconds=" << compute_seconds << " output_seconds=" << output_seconds << '\n';
    for(int thread = 0; thread < observed; ++thread)
        std::clog << "RT_THREAD id=" << thread << " cpu_seconds=" << thread_cpu[thread]
                  << " busy_seconds=" << thread_busy[thread] << " units=" << thread_units[thread]
                  << " pixels=" << thread_pixels[thread] << '\n';
#endif

#ifdef RT_DIAGNOSTIC
    std::clog << "RT_COUNTERS rays=" << diagnostic_rays << " spheres=" << diagnostic_spheres
              << " boxes=" << diagnostic_boxes << '\n';
    std::clog << "RT_HIT_RECORDS completed=" << diagnostic_records << '\n';
#endif
    std::clog << "\rDone.                 \n";
}

void camera::initialize()
{
    line.resize(image_width);
    image_height = int(image_width / aspect_ratio);
    image_height = (image_height < 1) ? 1 : image_height;

    center = lookfrom;
    pixel_samples_scale = 1.0 / samples_per_pixel;

    auto theta = degrees_to_radians(vfov);
    auto h = std::tan(theta / 2);
    auto viewport_height = 2 * h * focus_dist;
    auto viewport_width = viewport_height * (double(image_width) / image_height);

    w = unit_vector(lookfrom - lookat);
    u = unit_vector(cross(vup, w));
    v = cross(w, u);

    vec3 viewport_u = viewport_width * u;
    vec3 viewport_v = viewport_height * -v; // Image rows run downward.

    pixel_delta_u = viewport_u / image_width;
    pixel_delta_v = viewport_v / image_height;

    auto viewport_upper_left = center - (focus_dist * w) - viewport_u / 2 - viewport_v / 2;
    pixel00_loc = viewport_upper_left + 0.5 * (pixel_delta_u + pixel_delta_v);

    auto defocus_radius = focus_dist * std::tan(degrees_to_radians(defocus_angle / 2));
    defocus_disk_u = u * defocus_radius;
    defocus_disk_v = v * defocus_radius;
}

ray camera::get_ray(int i, int j) const
{
    // Jitter the pixel target and sample the lens for depth of field.
    auto offset = sample_square();
    auto pixel_sample = pixel00_loc + ((i + offset.x()) * pixel_delta_u) + ((j + offset.y()) * pixel_delta_v);

    auto ray_origin = (defocus_angle <= 0) ? center : defocus_disk_sample();
    auto ray_direction = pixel_sample - ray_origin;

    return ray(ray_origin, ray_direction);
}

vec3 camera::sample_square() const
{
    // Braced initialization fixes the order of random draws (x, then y).
    return vec3{random_double() - 0.5, random_double() - 0.5, 0};
}

point3 camera::defocus_disk_sample() const
{
    auto p = random_in_unit_disk();
    return center + (p[0] * defocus_disk_u) + (p[1] * defocus_disk_v);
}

color camera::ray_color(const ray &r, int depth, const hittable &world) const
{
#ifdef RT_DIAGNOSTIC
    ++diagnostic_rays;
#endif
    if(depth <= 0)
        return color(0, 0, 0);
    hit_record rec;

    if(world.hit(r, interval(0.001, infinity), rec))
    {
        ray scattered;
        color attenuation;
        if(rec.mat->scatter(r, rec, attenuation, scattered))
            return attenuation * ray_color(scattered, depth - 1, world);
        return color(0, 0, 0);
    }

    vec3 unit_direction = unit_vector(r.direction());
    auto a = 0.5 * (unit_direction.y() + 1.0);
    return (1.0 - a) * color(1.0, 1.0, 1.0) + a * color(0.5, 0.7, 1.0);
}
