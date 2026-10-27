#include "worksteal/runtime.hpp"
#include "worksteal/workload.hpp"
#include <iostream>
#include <numeric>

using namespace ws;
void require(bool value, const char *message) {
  if (!value)
    throw std::runtime_error(message);
}
Json policy_config(const std::string &victim, const std::string &timing,
                   const std::string &migration) {
  return {{"partition", {{"name", "fixed_grain"}, {"grain", 3}}},
          {"victim", {{"name", victim}}},
          {"steal_timing", {{"name", timing}}},
          {"migration", {{"name", migration}}},
          {"affinity", {{"name", "unbound"}}},
          {"placement", {{"name", "round_robin"}}}};
}
int main() {
  try {
    std::size_t checks = 0;
    for (auto mode :
         {Executor::static_partition, Executor::central, Executor::worksteal})
      for (auto p : {std::size_t(1), std::size_t(4)})
        for (const auto &timing : {"disabled", "immediate", "bounded_backoff"})
          for (const auto &migration : {"single", "capped_half"}) {
            auto policies = make_policies(
                policy_config("seeded_random", timing, migration));
            Pool pool(p, mode, policies, std::vector<int>(p, -1), true);
            for (std::size_t round = 0; round < 30; ++round) {
              auto n = round % 7 == 0 ? 0 : round % 7 == 1 ? 1 : round * 13;
              std::vector<std::vector<std::size_t>> lists(p);
              for (std::size_t t = 0; t < n; ++t)
                lists[(round % 2) ? t % p : 0].push_back(t);
              auto counts = std::make_unique<std::atomic<unsigned>[]>(n);
              for (std::size_t t = 0; t < n; ++t)
                counts[t] = 0;
              std::vector<std::uint64_t> values(n);
              pool.prepare(lists);
              pool.run([&](std::size_t id, std::size_t) {
                if (id % 3 == 0)
                  std::this_thread::yield();
                require(counts[id].fetch_add(1) == 0, "duplicate");
                values[id] = mix(id + 17);
              });
              for (std::size_t t = 0; t < n; ++t) {
                require(counts[t] == 1, "missing");
                require(values[t] == mix(t + 17), "publication failed");
              }
              ++checks;
            }
            std::vector<std::vector<std::size_t>> lists(p);
            for (std::size_t t = 0; t < 200; ++t)
              lists[0].push_back(t);
            pool.prepare(lists);
            bool caught = false;
            try {
              pool.run([](auto id, auto) {
                if (id == 199)
                  throw std::runtime_error("intentional");
              });
            } catch (const std::runtime_error &) {
              caught = true;
            }
            require(caught, "exception not propagated");
            ++checks;
            lists.assign(p, {});
            lists[0] = {0};
            pool.prepare(lists);
            std::atomic<int> count{0};
            pool.run([&](auto, auto) { ++count; });
            require(count == 1, "recovery failed");
            ++checks;
            // Local phase must stay with assigned worker, including on the
            // central executor.
            lists.assign(p, {});
            for (std::size_t t = 0; t < p; ++t)
              lists[t].push_back(t);
            pool.prepare(lists, true);
            pool.run([&](auto id,
                         auto w) { require(id == w, "local phase migrated"); },
                     true);
            ++checks;
          }
    // Exercise uninstrumented execution and partial completion batches as well
    // as exact-once diagnostics. Reuse the same pool over batch boundaries.
    for (bool diagnostic : {false, true})
      for (auto mode : {Executor::static_partition, Executor::central,
                        Executor::worksteal}) {
        auto policies = make_policies(
            policy_config("round_robin", "immediate", "capped_half"));
        Pool pool(4, mode, policies, {-1, -1, -1, -1}, diagnostic);
        for (std::size_t n : {0, 1, 2, 31, 32, 33, 63, 64, 65, 1023, 1024, 1025}) {
          std::vector<std::vector<std::size_t>> lists(4);
          std::vector<std::uint64_t> output(n);
          auto visits = std::make_unique<std::atomic<unsigned>[]>(n);
          for (std::size_t t = 0; t < n; ++t) {
            lists[0].push_back(t);
            visits[t] = 0;
          }
          pool.prepare(lists);
          pool.run([&](auto id, auto) {
            require(visits[id].fetch_add(1) == 0, "batched duplicate");
            output[id] = mix(id + 191);
            if (id % 17 == 0)
              std::this_thread::yield();
          });
          for (std::size_t id = 0; id < n; ++id)
            require(visits[id] == 1 && output[id] == mix(id + 191),
                    "batched completion publication");
          ++checks;
        }
      }
    // An exception with 17 unflushed completions must release waiters, and a
    // subsequent epoch must not inherit those pending counts or task storage.
    for (bool diagnostic : {false, true}) {
      auto policies = make_policies(
          policy_config("round_robin", "immediate", "single"));
      Pool pool(1, Executor::worksteal, policies, {-1}, diagnostic);
      std::vector<std::size_t> ids(65);
      std::iota(ids.begin(), ids.end(), 0);
      pool.prepare({ids});
      std::size_t visits = 0;
      bool caught = false;
      try {
        pool.run([&](auto, auto) {
          if (++visits == 18)
            throw std::runtime_error("partial completion batch");
        });
      } catch (const std::runtime_error &) {
        caught = true;
      }
      require(caught && visits == 18, "partial batch exception lost");
      ++checks;
      pool.prepare({{0, 1}});
      visits = 0;
      pool.run([&](auto, auto) { ++visits; });
      require(visits == 2, "partial batch poisoned next epoch");
      ++checks;
    }
    for (const auto &name : {"fixed_grain", "balanced_chunks"}) {
      auto policies =
          make_policies(policy_config("round_robin", "immediate", "single"));
      auto j = Json{{"name", name}};
      auto partition = Registry<Partition>::get().make(j);
      for (std::size_t n : {0, 1, 2, 37, 100}) {
        auto tasks = partition->split(n, 4);
        std::size_t end = 0;
        for (const auto &t : tasks) {
          require(t.begin == end && t.end > t.begin, "bad partition");
          end = t.end;
        }
        require(end == n, "coverage");
        ++checks;
      }
    }
    for (auto name : {"compute_uniform", "compute_skewed", "memory_reuse"}) {
      Workload w(Json{{"name", name},
                      {"elements", 17},
                      {"iterations", 3},
                      {"bytes_per_element", 128},
                      {"passes", 2}});
      w.execute({0, 0, 17, 0}, 0);
      require(w.verify().at("pass"), "workload reference");
      ++checks;
    }
    // Independent scalar reference vs interleaved compute tails, skew boundary
    // and task lengths both below/above lane widths.
    for (auto name : {"compute_uniform", "compute_skewed"})
      for (std::size_t n : {0, 1, 3, 4, 5, 7, 8, 9, 31, 32, 33, 127})
        for (std::size_t grain : {1, 3, 4, 7, 8, 17, 128}) {
          Workload w(Json{{"name", name}, {"elements", n}, {"iterations", 37}});
          for (std::size_t b = 0; b < n; b += grain)
            w.execute({b / grain, b, std::min(n, b + grain), 0}, 0);
          require(w.verify().at("pass"), "interleaved scalar reference");
          ++checks;
        }
    // Memory interleaving: tails, nonzero task starts, odd word counts,
    // seed wraparound and both allocation paths against unchanged scalar value.
    for (std::size_t n : {0, 1, 3, 4, 5, 7, 8, 9, 17})
      for (std::size_t grain : {1, 3, 4, 5, 7, 8, 19})
        for (std::size_t bytes : {8, 136, 8192})
          for (bool overwrite : {false, true}) {
            const Json config{{"name", "memory_reuse"}, {"elements", n},
                              {"seed", std::uint64_t(-3)},
                              {"bytes_per_element", bytes}, {"passes", 3}};
            Workload w(config, 1, overwrite, 4);
            for (int epoch = 0; epoch < 2; ++epoch) {
              w.clear_output();
              for (std::size_t b = 0; b < n; b += grain)
                w.execute({b / grain, b, std::min(n, b + grain), 0}, 0);
              require(w.verify().at("pass"), "interleaved memory scalar reference");
              require(w.memory_lanes_used() == (n ? 4 : 0), "memory lane metadata");
            }
            ++checks;
          }
    for (std::size_t lanes : {0, 2, 8}) {
      bool rejected = false;
      try { Workload invalid(Json{{"name", "memory_reuse"}}, 1, false, lanes); }
      catch (const std::invalid_argument &) { rejected = true; }
      require(rejected, "invalid memory lanes accepted");
      ++checks;
    }
    // Full scalar reference comparisons must detect missing/partial output,
    // including striped compute tiles, memory blocks, tails and repeated calls.
    for (auto name : {"compute_uniform", "compute_skewed", "memory_reuse"})
      for (std::size_t n : {0, 1, 255, 256, 257, 513, 1025}) {
        Workload w(Json{{"name", name}, {"elements", n}, {"iterations", 3},
                        {"bytes_per_element", 128}, {"passes", 2}});
        for (int state = 0; state < 3; ++state) {
          w.clear_output();
          if (state > 0)
            w.execute({0, 0, state == 1 ? n / 2 : n, 0}, 0);
          const auto serial = w.verify();
          require(serial.at("compared_elements") == n, "serial reference count");
          require(serial.at("pass").get<bool>() == (n == 0 || state == 2),
                  "reference accepted incomplete output");
          for (std::size_t workers : {1, 2, 4, 8, 16}) {
            const auto parallel = w.verify(workers);
            for (auto field : {"pass", "compared_elements", "mismatches",
                               "output_hash_fnv1a64"})
              require(parallel.at(field) == serial.at(field),
                      "parallel reference disagrees with scalar");
            const std::size_t tile = std::string(name) == "memory_reuse" ? 1 : 256;
            require(parallel.at("reference_workers_used") ==
                        std::min(workers, n / tile + (n % tile != 0)),
                    "reference active worker count");
            ++checks;
          }
        }
      }
    for (std::size_t workers : {0, 129}) {
      Workload w(Json{{"name", "compute_uniform"}, {"elements", 1}});
      bool rejected = false;
      try { w.verify(workers); }
      catch (const std::invalid_argument &) { rejected = true; }
      require(rejected, "invalid reference worker count accepted");
      ++checks;
    }
    // Whole-block initialization partitions, uneven tails, repeated identity
    // reads and empty/compute cases. Independent byte oracle is in cli_checks.
    for (auto name : {"memory_reuse", "compute_uniform"})
      for (std::size_t n : {0, 1, 2, 3, 7, 9, 31, 65}) {
        const Json config{{"name", name}, {"elements", n}, {"iterations", 3},
                          {"bytes_per_element", 136}, {"passes", 2}};
        Workload serial(config);
        serial.execute({0, 0, n, 0}, 0);
        const auto expected = serial.verify();
        const std::vector<Task> tasks = n ? std::vector<Task>{{0, 0, n, 0}}
                                          : std::vector<Task>{};
        const std::vector<std::vector<std::size_t>> lists =
            n ? std::vector<std::vector<std::size_t>>{{0}}
              : std::vector<std::vector<std::size_t>>{{}};
        for (std::size_t count : {1, 2, 4, 8, 128})
         for (bool overwrite : {false, true}) {
          Workload parallel(config, count, overwrite);
          require(std::string(parallel.data_allocation_used()) ==
                      (std::string(name) == "memory_reuse" && n
                           ? (overwrite ? "overwrite" : "zeroed") : "none"),
                  "allocation used metadata");
          require(parallel.initialization_workers_used() ==
                      (std::string(name) == "memory_reuse" ? std::min(count, n) : 0),
                  "initialization active workers");
          require(parallel.identity(tasks, lists) == serial.identity(tasks, lists),
                  "parallel initialization identity");
          parallel.execute({0, 0, n, 0}, 0);
          require(parallel.verify() == expected, "parallel initialization output");
          ++checks;
        }
      }
    for (std::size_t count : {0, 129}) {
      bool rejected = false;
      try { Workload invalid(Json{{"name", "memory_reuse"}}, count); }
      catch (const std::invalid_argument &) { rejected = true; }
      require(rejected, "invalid initialization worker count accepted");
      ++checks;
    }
    bool unknown = false;
    try {
      Registry<Victim>::get().make(Json{{"name", "nonexistent"}});
    } catch (const std::invalid_argument &) {
      unknown = true;
    }
    require(unknown, "unknown accepted");
    ++checks;
    bool duplicate = false;
    try {
      Registry<Victim>::get().add("round_robin", {});
    } catch (const std::invalid_argument &) {
      duplicate = true;
    }
    require(duplicate, "duplicate accepted");
    ++checks;
    // An epoch called concurrently is rejected instead of clobbering the active
    // closure.
    {
      auto policies =
          make_policies(policy_config("round_robin", "immediate", "single"));
      Pool pool(1, Executor::worksteal, policies, {-1}, false);
      pool.prepare({{0}});
      std::atomic<bool> started{false}, release{false};
      std::thread submit([&] {
        pool.run([&](auto, auto) {
          started = true;
          while (!release.load())
            std::this_thread::yield();
        });
      });
      while (!started.load()) {
        std::this_thread::yield();
      }
      bool rejected = false;
      try {
        pool.run([](auto, auto) {});
      } catch (const std::logic_error &) {
        rejected = true;
      }
      release = true;
      submit.join();
      require(rejected, "concurrent epoch accepted");
      ++checks;
    }
    std::cout << Json{{"status", "pass"}, {"checks", checks}}.dump() << '\n';
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
