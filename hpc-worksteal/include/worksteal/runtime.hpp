#pragma once
#include "policy.hpp"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <exception>
#include <mutex>
#include <thread>

namespace ws {
enum class Executor { static_partition, central, worksteal };
struct alignas(64) Stats {
  std::uint64_t tasks = 0, attempts = 0, steals = 0, moved = 0, busy = 0,
                empty = 0;
  double first = -1, last = -1, compute = 0;
};
struct Epoch {
  double seconds;
  std::vector<Stats> stats;
};
class Pool {
public:
  using Job = std::function<void(std::size_t, std::size_t)>;
  Pool(std::size_t workers, Executor mode, const Policies &policies,
       const std::vector<int> &cpus, bool diagnostic);
  ~Pool();
  Pool(const Pool &) = delete;
  Pool &operator=(const Pool &) = delete;
  double prepare(const std::vector<std::vector<std::size_t>> &queues,
                 bool local_phase = false);
  Epoch run(Job job, bool local_only = false);
  const std::vector<std::vector<int>> &masks() const { return actual_masks; }

private:
  using Clock = std::chrono::steady_clock;
  struct Queue {
    std::mutex mutex;
    std::deque<std::size_t> tasks;
  };
  void worker(std::size_t me, int cpu);
  bool take(std::size_t me, std::size_t &task, std::uint64_t &rng,
            Stats &stats, std::vector<std::size_t> &scratch);
  void fail(std::exception_ptr e);
  std::size_t p;
  Executor mode;
  const Policies &policies;
  bool diagnostic;
  std::vector<std::unique_ptr<Queue>> queues;
  std::vector<std::thread> threads;
  std::vector<std::vector<int>> actual_masks;
  std::vector<Stats> stats;
  std::mutex state_mutex, submit_mutex;
  std::condition_variable state_cv;
  bool stopping = false, finished = false, local_only = false,
       prepared_local = false;
  std::uint64_t generation = 0;
  std::size_t ready = 0, arrived = 0, total = 0;
  std::atomic<std::size_t> remaining{0};
  std::atomic<bool> failed{false};
  std::exception_ptr error;
  Job job;
  Clock::time_point start;
};
} // namespace ws
