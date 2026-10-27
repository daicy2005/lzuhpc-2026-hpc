#pragma once
#include "policy.hpp"
#include <atomic>
#include <memory>
#include <span>
namespace ws {
class Workload {
public:
  explicit Workload(const Json &config, std::size_t initialization_workers = 1,
                    bool overwrite_data = false, std::size_t memory_lanes = 1);
  std::size_t size() const { return n; }
  std::size_t initialization_workers_used() const { return initialization_active; }
  const char *data_allocation_used() const {
    return data ? (overwrite_allocation ? "overwrite" : "zeroed") : "none";
  }
  std::size_t memory_lanes_used() const { return memory && n ? memory_lanes : 0; }
  void execute(const Task &task, std::size_t worker);
  void pretouch(const Task &task);
  Json verify(std::size_t reference_workers = 1) const;
  Json identity(const std::vector<Task> &tasks,
                const std::vector<std::vector<std::size_t>> &lists) const;
  Json execution_summary(const std::vector<Task> &tasks,
                         std::size_t workers) const;
  std::uint64_t cost(const Task &task) const;
  void clear_output();
  Json pretouch_hash() const;

private:
  std::uint64_t value(std::size_t i) const;
  std::size_t n, words, passes;
  std::uint64_t seed, k;
  bool memory, skew;
  std::size_t initialization_active = 0;
  bool overwrite_allocation;
  std::size_t memory_lanes;
  std::size_t data_size = 0;
  std::unique_ptr<std::uint64_t[]> data;
  std::vector<std::uint64_t> inputs, costs, output;
  std::vector<std::size_t> executors;
  std::vector<std::uint64_t> touch_checksums;
};
std::vector<std::vector<std::size_t>>
place_tasks(const std::vector<Task> &tasks, const Workload &workload,
            const Placement &policy, std::size_t p, const std::string &layout,
            std::uint64_t seed);
std::string hash_words(std::span<const std::uint64_t> words);
} // namespace ws
