#include "worksteal/runtime.hpp"
#include "worksteal/workload.hpp"
#include <fstream>
#include <iostream>
namespace {
using namespace ws;
Json read(const std::string &path) {
  std::ifstream f(path);
  if (!f)
    throw std::invalid_argument("cannot read config: " + path);
  Json j;
  f >> j;
  return j;
}
Json run(Json config, bool validate = false) {
  using Clock = std::chrono::steady_clock;
  auto e2e = Clock::now();
  // Phase markers stay outside Pool::run's epoch timer. Marker bookkeeping
  // remains in end-to-end time and is not attributed to any phase.
  Json phases = Json::object();
  auto phase_start = e2e;
  auto mark_phase = [&](const char *name) {
    auto end = Clock::now();
    auto seconds = std::chrono::duration<double>(end - phase_start).count();
    phases[name] = phases.value(name, 0.0) + seconds;
    phase_start = Clock::now();
  };
  keys(config, {"schema_version", "executor", "workers", "workload", "policies",
                "layout", "layout_seed", "measurement", "steal_enabled"});
  if (config.value("schema_version", 1) != 1)
    throw std::invalid_argument("unknown schema");
  auto workers = config.value("workers", 1);
  if (workers <= 0 || workers > 128)
    throw std::invalid_argument("workers out of range");
  auto p = static_cast<std::size_t>(workers);
  auto executor = config.at("executor").get<std::string>();
  auto mode = Executor::worksteal;
  if (executor == "static")
    mode = Executor::static_partition;
  else if (executor == "central")
    mode = Executor::central;
  else if (executor != "worksteal" && executor != "serial")
    throw std::invalid_argument("unknown executor");
  if (executor == "serial" && p != 1)
    throw std::invalid_argument("serial requires one worker");
  auto policies = make_policies(config.at("policies"));
  auto cpus = policies.affinity->plan(p, allowed_cpus());
  if (config.contains("steal_enabled") &&
      config.at("steal_enabled").get<bool>() != policies.timing->enabled())
    throw std::invalid_argument("steal_enabled contradicts timing policy");
  config["steal_enabled"] = policies.timing->enabled();
  auto measurement = config.value("measurement", Json::object());
  keys(measurement, {"mode", "epochs", "throw_task", "pause_seed",
                     "controlled_worker", "home_worker", "reference_workers"});
  auto reference_count = measurement.value("reference_workers", Json(1));
  if (!reference_count.is_number_integer() || reference_count < 1 ||
      reference_count > 128)
    throw std::invalid_argument("reference_workers must be an integer in [1,128]");
  auto reference_workers = reference_count.get<std::size_t>();
  auto metrics = measurement.value("mode", std::string("timing"));
  if (metrics != "timing" && metrics != "diagnostic")
    throw std::invalid_argument("invalid metrics mode");
  bool diagnostic = metrics == "diagnostic";
  auto epochs = measurement.value("epochs", 1);
  if (epochs < 1 || epochs > 100)
    throw std::invalid_argument("invalid epochs");
  if (!diagnostic && (measurement.contains("throw_task") ||
                      measurement.contains("pause_seed")))
    throw std::invalid_argument("fault injection requires diagnostic mode");
  auto main_mask = allowed_cpus();
  mark_phase("configuration_and_policies");
  Workload workload(config.at("workload"));
  mark_phase("workload_initialization");
  auto tasks = policies.partition->split(workload.size(), p);
  auto home = measurement.value("home_worker", -1);
  if (home >= workers || home < -1)
    throw std::invalid_argument("invalid home worker");
  if (home >= 0)
    for (auto &t : tasks)
      t.home = static_cast<std::size_t>(home);
  auto lists = place_tasks(tasks, workload, *policies.placement, p,
                           config.value("layout", std::string("policy")),
                           config.value("layout_seed", 42ULL));
  std::size_t next = 0, index = 0;
  for (auto &t : tasks) {
    if (t.id != index++ || t.begin != next || t.end <= t.begin ||
        t.end > workload.size())
      throw std::invalid_argument("partition must cover in order");
    next = t.end;
  }
  if (next != workload.size())
    throw std::invalid_argument("incomplete partition");
  auto controlled = measurement.value("controlled_worker", -1);
  if (controlled >= workers || controlled < -1)
    throw std::invalid_argument("invalid controlled worker");
  if (controlled >= 0) {
    for (auto &list : lists)
      list.clear();
    for (const auto &t : tasks)
      lists[static_cast<std::size_t>(controlled)].push_back(t.id);
  }
  if (validate)
    return {{"status", "valid"}, {"resolved_config", config}};
  mark_phase("partition_and_placement");
  auto identity = workload.identity(tasks, lists);
  mark_phase("identity_hashes");
  std::unique_ptr<Pool> pool;
  std::vector<std::vector<int>> masks;
  if (executor != "serial") {
    pool = std::make_unique<Pool>(p, mode, policies, cpus, diagnostic);
    masks = pool->masks();
  } else {
    masks = {bind_and_query(cpus[0])};
  }
  auto setup = std::chrono::duration<double>(Clock::now() - e2e).count();
  mark_phase("pool_creation");
  Json epoch_results = Json::array();
  double dispatch = 0;
  bool all_correct = true;
  auto counts = std::make_unique<std::atomic<unsigned>[]>(tasks.size());
  for (int epoch = 0; epoch < epochs; ++epoch) {
    workload.clear_output();
    for (std::size_t t = 0; t < tasks.size(); ++t)
      counts[t] = 0;
    mark_phase("output_and_counts_preparation");
    // Same-process home pre-read; no computed final output is reused.
    if (config.at("workload").at("name") == "memory_reuse") {
      std::vector<std::vector<std::size_t>> homes(p);
      for (const auto &t : tasks)
        homes[t.home % p].push_back(t.id);
      if (pool) {
        dispatch += pool->prepare(homes, true);
        pool->run([&](auto id, auto) { workload.pretouch(tasks[id]); }, true);
      } else
        for (const auto &t : tasks)
          workload.pretouch(t);
    }
    mark_phase("home_preread");
    Epoch result{};
    auto fn = [&](std::size_t id, std::size_t worker) {
      if (diagnostic) {
        if (counts[id].fetch_add(1) != 0)
          throw std::runtime_error("duplicate task");
        if (measurement.value("throw_task", -1LL) == static_cast<long long>(id))
          throw std::runtime_error("injected task exception");
        if (measurement.contains("pause_seed") &&
            (mix(id + measurement.at("pause_seed").get<std::uint64_t>()) % 7 ==
             0))
          std::this_thread::yield();
      }
      workload.execute(tasks[id], worker);
    };
    if (pool) {
      dispatch += pool->prepare(lists, controlled >= 0);
      result = pool->run(fn, controlled >= 0);
    } else {
      auto t0 = Clock::now();
      workload.execute(Task{0, 0, workload.size(), 0}, 0);
      result.seconds = std::chrono::duration<double>(Clock::now() - t0).count();
    }
    mark_phase("dispatch_and_execution_wall");
    auto correctness = workload.verify(reference_workers);
    mark_phase("full_reference_verification");
    bool coverage = true;
    if (diagnostic)
      for (std::size_t t = 0; t < tasks.size(); ++t)
        if (counts[t] != 1)
          coverage = false;
    if (executor == "serial")
      coverage = true;
    correctness["exact_once"] =
        diagnostic && executor != "serial" ? Json(coverage) : Json(nullptr);
    all_correct = all_correct && correctness.at("pass").get<bool>() && coverage;
    Json stats_json = nullptr;
    if (diagnostic) {
      stats_json = Json::array();
      for (const auto &s : result.stats)
        stats_json.push_back({{"tasks", s.tasks},
                              {"attempts", s.attempts},
                              {"steals", s.steals},
                              {"moved", s.moved},
                              {"busy", s.busy},
                              {"empty", s.empty},
                              {"first_start_seconds", s.first},
                              {"last_finish_seconds", s.last},
                              {"compute_seconds", s.compute}});
    }
    epoch_results.push_back(
        {{"epoch", epoch},
         {"epoch_seconds", result.seconds},
         {"correctness", correctness},
         {"identity", identity},
         {"worker_stats", stats_json},
         {"execution",
          diagnostic ? workload.execution_summary(tasks, p) : Json(nullptr)},
         {"pretouch_hash_fnv1a64", workload.pretouch_hash()},
         {"local_only", controlled >= 0}});
    mark_phase("result_summary");
  }
  pool.reset();
  mark_phase("pool_shutdown");
  auto e2e_seconds = std::chrono::duration<double>(Clock::now() - e2e).count();
  return {{"schema_version", 1},
          {"status", all_correct ? "completed" : "incorrect"},
          {"resolved_config", config},
          {"metrics_mode", metrics},
          {"affinity",
           {{"requested", cpus},
            {"actual_workers", masks},
            {"main_mask_before", main_mask},
            {"control_wait", "condition_variable"}}},
          {"timing",
           {{"setup_seconds", setup},
            {"dispatch_seconds", dispatch},
            {"epoch_seconds", epoch_results[0]["epoch_seconds"]},
            {"end_to_end_seconds", e2e_seconds}}},
          {"phase_seconds", phases},
          {"correctness", {{"pass", all_correct}}},
          {"epochs", epoch_results}};
}
} // namespace
int main(int argc, char **argv) {
  try {
    std::string config_path, output_path;
    bool validate = false;
    for (int i = 1; i < argc; ++i) {
      std::string a = argv[i];
      if (a == "--list-policies") {
        std::cout << ws::list_policies().dump(2) << '\n';
        return 0;
      } else if (a == "--validate-config")
        validate = true;
      else if ((a == "--config" || a == "--output") && i + 1 < argc) {
        if (a == "--config")
          config_path = argv[++i];
        else
          output_path = argv[++i];
      } else
        throw std::invalid_argument("usage: worksteal --config PATH [--output "
                                    "PATH] [--validate-config]");
    }
    auto config = read(config_path);
    auto result = run(config, validate);
    auto text = result.dump(2);
    if (!output_path.empty()) {
      std::ofstream f(output_path);
      if (!f)
        throw std::runtime_error("cannot open output");
      f << text << '\n';
    }
    std::cout << text << '\n';
    return validate                                          ? 0
           : result.at("correctness").at("pass").get<bool>() ? 0
                                                             : 4;
  } catch (const std::invalid_argument &e) {
    std::cerr << e.what() << '\n';
    return 2;
  } catch (const nlohmann::json::exception &e) {
    std::cerr << e.what() << '\n';
    return 2;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 3;
  }
}
