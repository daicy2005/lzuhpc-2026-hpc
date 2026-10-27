#include "worksteal/runtime.hpp"
#include <algorithm>

namespace ws {
Pool::Pool(std::size_t workers, Executor m, const Policies &pol,
           const std::vector<int> &cpus, bool diag)
    : p(workers), mode(m), policies(pol), diagnostic(diag), actual_masks(p),
      stats(p) {
  if (!p || cpus.size() != p)
    throw std::invalid_argument("invalid pool size");
  for (std::size_t w = 0; w < p; ++w)
    queues.push_back(std::make_unique<Queue>());
  try {
    for (std::size_t w = 0; w < p; ++w)
      threads.emplace_back([this, w, cpu = cpus[w]] { worker(w, cpu); });
  } catch (...) {
    {
      std::lock_guard lock(state_mutex);
      stopping = true;
      state_cv.notify_all();
    }
    for (auto &t : threads)
      t.join();
    throw;
  }
  std::unique_lock lock(state_mutex);
  state_cv.wait(lock, [&] { return ready == p; });
  if (error) {
    stopping = true;
    state_cv.notify_all();
    lock.unlock();
    for (auto &t : threads)
      t.join();
    std::rethrow_exception(error);
  }
}
Pool::~Pool() {
  {
    std::lock_guard lock(state_mutex);
    stopping = true;
    state_cv.notify_all();
  }
  for (auto &t : threads)
    if (t.joinable())
      t.join();
}
double Pool::prepare(const std::vector<std::vector<std::size_t>> &lists,
                     bool local_phase) {
  std::lock_guard submission(submit_mutex);
  auto t = Clock::now();
  if (lists.size() != p)
    throw std::invalid_argument("queue count mismatch");
  total = 0;
  prepared_local = local_phase;
  for (auto &q : queues)
    q->tasks.clear();
  if (mode == Executor::central && !local_phase) {
    for (const auto &list : lists)
      for (auto id : list)
        queues[0]->tasks.push_back(id);
    std::sort(queues[0]->tasks.begin(), queues[0]->tasks.end());
    total = queues[0]->tasks.size();
  } else
    for (std::size_t w = 0; w < p; ++w) {
      queues[w]->tasks.assign(lists[w].begin(), lists[w].end());
      total += lists[w].size();
    }
  return std::chrono::duration<double>(Clock::now() - t).count();
}
Epoch Pool::run(Job work, bool local_phase) {
  std::unique_lock submission(submit_mutex, std::try_to_lock);
  if (!submission.owns_lock())
    throw std::logic_error("concurrent epoch submission");
  if (prepared_local != local_phase)
    throw std::logic_error("prepare/run phase mismatch");
  std::unique_lock lock(state_mutex);
  job = std::move(work);
  local_only = local_phase;
  remaining.store(total);
  failed.store(false);
  error = nullptr;
  finished = (total == 0);
  arrived = 0;
  stats.assign(p, Stats{});
  start = Clock::now();
  ++generation;
  state_cv.notify_all();
  state_cv.wait(lock, [&] { return finished; });
  auto end = Clock::now();
  state_cv.wait(lock, [&] { return arrived == p; });
  if (error)
    std::rethrow_exception(error);
  return {std::chrono::duration<double>(end - start).count(), stats};
}
void Pool::fail(std::exception_ptr e) {
  std::lock_guard lock(state_mutex);
  if (!error)
    error = e;
  failed.store(true);
  finished = true;
  state_cv.notify_all();
}
bool Pool::take(std::size_t me, std::size_t &task, std::uint64_t &rng,
                Stats &st, std::vector<std::size_t> &scratch) {
  auto own = (mode == Executor::central && !local_only ? 0 : me);
  {
    std::lock_guard lock(queues[own]->mutex);
    if (!queues[own]->tasks.empty()) {
      if (mode == Executor::central && !local_only) {
        task = queues[own]->tasks.front();
        queues[own]->tasks.pop_front();
      } else {
        task = queues[own]->tasks.back();
        queues[own]->tasks.pop_back();
      }
      return true;
    }
  }
  if (local_only || mode != Executor::worksteal ||
      !policies.timing->enabled() || p == 1)
    return false;
  auto v = policies.victim->next(me, p, rng);
  if (v >= p || v == me)
    throw std::logic_error("invalid victim policy result");
  // No policy callback under queue locks. Snapshot, decide, then revalidate.
  std::size_t available = 0;
  {
    std::unique_lock lock(queues[v]->mutex, std::try_to_lock);
    if (!lock.owns_lock()) {
      if (diagnostic)
        ++st.busy;
      return false;
    }
    available = queues[v]->tasks.size();
  }
  auto limit = policies.migration->count(available);
  std::vector<std::size_t> batch;
#if WS_STEAL_SCRATCH
  auto &transferred = scratch;
  transferred.clear();
#else
  (void)scratch;
  auto &transferred = batch;
#endif
  if (diagnostic)
    ++st.attempts;
  {
    std::unique_lock lock(queues[v]->mutex, std::try_to_lock);
    if (!lock.owns_lock()) {
      if (diagnostic)
        ++st.busy;
      return false;
    }
    auto n = std::min(limit, queues[v]->tasks.size());
    if (!n) {
      if (diagnostic)
        ++st.empty;
      return false;
    }
#if WS_STEAL_SCRATCH
    // The first stolen task is returned directly. Only extra descriptors need
    // storage; retained worker-local capacity is reused in later steals/epochs.
    if (n > 1)
      transferred.reserve(n - 1);
    task = queues[v]->tasks.front();
    queues[v]->tasks.pop_front();
    for (std::size_t i = 1; i < n; ++i) {
      transferred.push_back(queues[v]->tasks.front());
      queues[v]->tasks.pop_front();
    }
#else
    for (std::size_t i = 0; i < n; ++i) {
      transferred.push_back(queues[v]->tasks.front());
      queues[v]->tasks.pop_front();
    }
#endif
  }
#if WS_STEAL_SCRATCH
  const auto moved = 1 + transferred.size();
  if (!transferred.empty()) {
    std::lock_guard lock(queues[me]->mutex);
    for (std::size_t i = transferred.size(); i-- > 0;)
      queues[me]->tasks.push_back(transferred[i]);
  }
#else
  const auto moved = transferred.size();
  task = transferred.front();
  if (transferred.size() > 1) {
    std::lock_guard lock(queues[me]->mutex);
    for (std::size_t i = transferred.size(); i-- > 1;)
      queues[me]->tasks.push_back(transferred[i]);
  }
#endif
  if (diagnostic) {
    ++st.steals;
    st.moved += moved;
  }
  return true;
}
void Pool::worker(std::size_t me, int cpu) {
  try {
    actual_masks[me] = bind_and_query(cpu);
  } catch (...) {
    std::lock_guard lock(state_mutex);
    if (!error)
      error = std::current_exception();
  }
  std::unique_lock lock(state_mutex);
  ++ready;
  state_cv.notify_all();
  std::uint64_t seen = 0;
  std::vector<std::size_t> scratch;
  while (true) {
    state_cv.wait(lock, [&] { return stopping || generation != seen; });
    if (stopping)
      return;
    seen = generation;
    lock.unlock();
    std::uint64_t rng = 0;
    std::size_t misses = 0;
    std::size_t pending = 0;
    auto publish = [&] {
      if (!pending)
        return;
      // Each RMW releases every task written since this worker's prior flush.
      // The seq_cst RMW chain and state_mutex publish all output to run().
      // Flush before any idle/wait so held completions cannot prevent exit.
      const auto completed = pending;
      pending = 0;
      if (remaining.fetch_sub(completed) == completed) {
        std::lock_guard done(state_mutex);
        finished = true;
        state_cv.notify_all();
      }
    };
    auto &st = stats[me];
    try {
      while (remaining.load() != 0 && !failed.load()) {
        std::size_t task = 0;
        if (take(me, task, rng, st, scratch)) {
          auto begin = diagnostic ? Clock::now() : Clock::time_point{};
          if (diagnostic && st.first < 0)
            st.first = std::chrono::duration<double>(begin - start).count();
          job(task, me);
          if (diagnostic) {
            auto now = Clock::now();
            ++st.tasks;
            st.last = std::chrono::duration<double>(now - start).count();
            st.compute += std::chrono::duration<double>(now - begin).count();
          }
          misses = 0;
          if (++pending >= WS_COMPLETION_BATCH)
            publish();
        } else {
          publish();
          if (remaining.load() == 0 || failed.load())
            break;
          auto idle =
              (mode == Executor::worksteal ? policies.timing->idle(++misses)
                                           : Idle::wait);
          if (local_only || mode == Executor::central ||
              mode == Executor::static_partition || p == 1)
            idle = Idle::wait;
          if (idle == Idle::yield)
            std::this_thread::yield();
          else {
            std::unique_lock wait(state_mutex);
            if (idle == Idle::wait)
              state_cv.wait(wait, [&] { return finished || stopping; });
            else
              state_cv.wait_for(wait, std::chrono::microseconds(50),
                                [&] { return finished || stopping; });
          }
        }
      }
      publish();
    } catch (...) {
      fail(std::current_exception());
    }
    lock.lock();
    ++arrived;
    state_cv.notify_all();
  }
}
} // namespace ws
