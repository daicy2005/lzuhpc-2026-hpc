#include "worksteal/workload.hpp"
#include <algorithm>
#include <array>
#include <exception>
#include <iomanip>
#include <numeric>
#include <random>
#include <sstream>
#include <thread>
namespace ws {
std::string hash_words(const std::vector<std::uint64_t> &v) {
  std::uint64_t h = 14695981039346656037ULL;
  for (auto x : v) {
    for (int b = 0; b < 8; ++b) {
      h ^= (x >> (b * 8)) & 255;
      h *= 1099511628211ULL;
    }
  }
  std::ostringstream s;
  s << std::hex << std::setw(16) << std::setfill('0') << h;
  return s.str();
}
Workload::Workload(const Json &j) {
  keys(j, {"name", "elements", "iterations", "seed", "bytes_per_element",
           "passes"});
  auto name = j.at("name").get<std::string>();
  memory = name == "memory_reuse";
  skew = name == "compute_skewed";
  if (!memory && !skew && name != "compute_uniform")
    throw std::invalid_argument("unknown workload");
  auto nn = j.value("elements", 262144LL), kk = j.value("iterations", 64LL),
       bb = j.value("bytes_per_element", 8192LL), pp = j.value("passes", 4LL);
  if (nn < 0 || nn > 16777216 || kk <= 0 || kk > 1000000 || bb < 8 || bb % 8 ||
      pp <= 0 || pp > 1024)
    throw std::invalid_argument("invalid workload bounds");
  n = static_cast<std::size_t>(nn);
  k = static_cast<std::uint64_t>(kk);
  seed = j.value("seed", 42ULL);
  words = static_cast<std::size_t>(bb / 8);
  passes = static_cast<std::size_t>(pp);
  if (memory && n && (words > std::size_t(2) * 1024 * 1024 * 1024 / 8 / n))
    throw std::invalid_argument("memory budget exceeds 2 GiB");
  inputs.resize(n);
  costs.resize(n);
  output.resize(n);
  executors.resize(n);
  touch_checksums.resize(n);
  for (std::size_t i = 0; i < n; ++i) {
    inputs[i] = mix(seed ^ (i * 0x9e3779b97f4a7c15ULL));
    costs[i] = k * (skew && i < n / 8 ? 9 : 1);
  }
  if (memory) {
    data.resize(n * words);
    for (std::size_t i = 0; i < data.size(); ++i)
      data[i] = mix(seed + i);
  }
}
std::uint64_t Workload::value(std::size_t i) const {
  auto x = inputs[i];
  if (memory) {
    for (std::size_t r = 0; r < passes; ++r)
      for (std::size_t j = 0; j < words; ++j)
        x = (x + data[i * words + j] + r) ^ (x >> 7);
  } else
    for (std::uint64_t j = 0; j < costs[i]; ++j)
      x = mix(x + j + (x << 1));
  return x;
}
void Workload::execute(const Task &t, std::size_t worker) {
  auto i = t.begin;
#if WS_COMPUTE_LANES > 1
  if (!memory) {
    // Independent elements expose instruction-level parallelism. Never change
    // an element's recurrence or number of mix operations; mixed-cost blocks
    // use the unchanged scalar reference path below.
    constexpr std::size_t lanes = WS_COMPUTE_LANES;
    for (; t.end - i >= lanes; i += lanes) {
      const auto iterations = costs[i];
      bool equal = true;
      for (std::size_t lane = 1; lane < lanes; ++lane)
        equal = equal && costs[i + lane] == iterations;
      if (!equal) {
        for (std::size_t lane = 0; lane < lanes; ++lane) {
          output[i + lane] = value(i + lane);
          executors[i + lane] = worker;
        }
        continue;
      }
      std::array<std::uint64_t, lanes> values;
      for (std::size_t lane = 0; lane < lanes; ++lane)
        values[lane] = inputs[i + lane];
      for (std::uint64_t j = 0; j < iterations; ++j)
        for (auto &x : values)
          x = mix(x + j + (x << 1));
      for (std::size_t lane = 0; lane < lanes; ++lane) {
        output[i + lane] = values[lane];
        executors[i + lane] = worker;
      }
    }
  }
#endif
  for (; i < t.end; ++i) {
    output[i] = value(i);
    executors[i] = worker;
  }
}
void Workload::pretouch(const Task &t) {
  if (memory)
    for (auto i = t.begin; i < t.end; ++i) {
      std::uint64_t x = 0;
      for (std::size_t j = 0; j < words; ++j)
        x += data[i * words + j];
      touch_checksums[i] = x;
    }
}
void Workload::clear_output() {
  std::fill(output.begin(), output.end(), 0);
  std::fill(executors.begin(), executors.end(), std::size_t(-1));
}
Json Workload::pretouch_hash() const {
  return memory ? Json(hash_words(touch_checksums)) : Json(nullptr);
}
Json Workload::verify(std::size_t reference_workers) const {
  if (reference_workers == 0 || reference_workers > 128)
    throw std::invalid_argument("reference_workers must be in [1,128]");
  const std::size_t tile = memory ? 1 : 256;
  const auto tiles = n / tile + (n % tile != 0);
  const auto active = std::min(reference_workers, tiles);
  struct alignas(64) Partial {
    std::size_t bad = 0, compared = 0;
    std::exception_ptr error;
  };
  // Each worker owns one slot, reads immutable inputs/output, then publishes
  // through join. Declare slots before jthreads so a failed thread creation
  // joins all started workers before their referenced storage is destroyed.
  std::vector<Partial> partial(std::max(std::size_t(1), active));
  auto compare = [&](std::size_t worker) {
    try {
      for (auto block = worker; block < tiles; block += active) {
        const auto begin = block * tile;
        const auto end = std::min(n, begin + tile);
        for (auto i = begin; i < end; ++i) {
          if (output[i] != value(i))
            ++partial[worker].bad;
          ++partial[worker].compared;
        }
      }
    } catch (...) {
      partial[worker].error = std::current_exception();
    }
  };
  if (active <= 1) {
    // Also preserves the original contiguous scalar reference loop at p=1.
    for (std::size_t i = 0; i < n; ++i) {
      if (output[i] != value(i))
        ++partial[0].bad;
      ++partial[0].compared;
    }
  } else {
    std::vector<std::jthread> threads;
    threads.reserve(active);
    for (std::size_t worker = 0; worker < active; ++worker)
      threads.emplace_back(compare, worker);
    for (auto &thread : threads)
      thread.join();
  }
  std::size_t bad = 0, compared = 0;
  for (const auto &slot : partial) {
    if (slot.error)
      std::rethrow_exception(slot.error);
    bad += slot.bad;
    compared += slot.compared;
  }
  return {{"pass", bad == 0 && compared == n},
          {"compared_elements", compared},
          {"mismatches", bad},
          {"reference_workers_used", active},
          {"reference_tile_elements", tile},
          {"output_hash_fnv1a64", hash_words(output)}};
}
std::uint64_t Workload::cost(const Task &t) const {
  if (memory)
    return (t.end - t.begin) * words * passes;
  return std::accumulate(costs.begin() + static_cast<std::ptrdiff_t>(t.begin),
                         costs.begin() + static_cast<std::ptrdiff_t>(t.end),
                         std::uint64_t(0));
}
Json Workload::execution_summary(const std::vector<Task> &tasks,
                                 std::size_t workers) const {
  std::vector<std::uint64_t> work(workers, 0), elements(workers, 0), owners;
  std::uint64_t mismatch = 0;
  for (const auto &t : tasks) {
    auto owner = executors[t.begin];
    owners.push_back(owner);
    for (auto i = t.begin; i < t.end; ++i) {
      auto w = executors[i];
      if (w >= workers)
        throw std::logic_error("element not executed");
      work[w] += memory ? words * passes : costs[i];
      ++elements[w];
      if (w != t.home)
        ++mismatch;
    }
  }
  return {{"worker_cost_units", work},
          {"worker_elements", elements},
          {"task_executor", owners},
          {"element_home_mismatches", mismatch},
          {"cost_unit", memory ? "uint64_read_visits" : "mix_iterations"}};
}
Json Workload::identity(
    const std::vector<Task> &tasks,
    const std::vector<std::vector<std::size_t>> &lists) const {
  std::vector<std::uint64_t> task_words, queue_words,
      initial_costs(lists.size());
  std::uint64_t max_cost = 0, total_cost = 0;
  for (auto &t : tasks) {
    task_words.insert(task_words.end(), {t.id, t.begin, t.end, t.home});
    auto c = cost(t);
    max_cost = std::max(max_cost, c);
    total_cost += c;
  }
  for (std::size_t w = 0; w < lists.size(); ++w) {
    queue_words.push_back(w);
    queue_words.push_back(lists[w].size());
    for (auto id : lists[w]) {
      queue_words.push_back(id);
      initial_costs[w] += cost(tasks[id]);
    }
  }
  return {
      {"input_hash_fnv1a64", hash_words(inputs)},
      {"cost_hash_fnv1a64", hash_words(costs)},
      {"task_hash_fnv1a64", hash_words(task_words)},
      {"queue_hash_fnv1a64", hash_words(queue_words)},
      {"data_hash_fnv1a64", memory ? Json(hash_words(data)) : Json(nullptr)},
      {"initial_cost_units", initial_costs},
      {"total_cost_units", total_cost},
      {"max_task_cost_units", max_cost},
      {"task_count", tasks.size()},
      {"per_element_bytes", memory ? words * 8 : 8},
      {"total_data_bytes", data.size() * 8}};
}
std::vector<std::vector<std::size_t>>
place_tasks(const std::vector<Task> &tasks, const Workload &w,
            const Placement &pol, std::size_t p, const std::string &layout,
            std::uint64_t seed) {
  std::vector<std::vector<std::size_t>> lists(p);
  std::vector<std::size_t> ids(tasks.size());
  std::iota(ids.begin(), ids.end(), 0);
  if (layout == "concentrated" || layout == "spread")
    std::stable_sort(ids.begin(), ids.end(), [&](auto a, auto b) {
      return w.cost(tasks[a]) > w.cost(tasks[b]);
    });
  if (layout == "shuffled") {
    std::mt19937_64 rng(seed);
    std::shuffle(ids.begin(), ids.end(), rng);
  }
  if (layout != "policy" && layout != "concentrated" && layout != "spread" &&
      layout != "shuffled")
    throw std::invalid_argument("unknown layout");
  auto capacity = tasks.empty() ? 1 : 1 + (tasks.size() - 1) / p;
  for (std::size_t i = 0; i < ids.size(); ++i) {
    auto id = ids[i];
    auto owner = layout == "policy"         ? pol.owner(tasks[id], p)
                 : layout == "concentrated" ? std::min(p - 1, i / capacity)
                                            : i % p;
    if (owner >= p)
      throw std::logic_error("invalid placement");
    lists[owner].push_back(id);
  }
  return lists;
}
} // namespace ws
