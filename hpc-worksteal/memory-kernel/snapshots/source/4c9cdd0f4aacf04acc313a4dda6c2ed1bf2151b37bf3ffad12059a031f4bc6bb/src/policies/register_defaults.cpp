#include "worksteal/policy.hpp"
#include <algorithm>
#include <numeric>
#include <sched.h>
#include <set>
#include <system_error>

namespace ws {
void keys(const Json &j, std::initializer_list<const char *> valid) {
  if (!j.is_object())
    throw std::invalid_argument("configuration must be object");
  for (auto it = j.begin(); it != j.end(); ++it)
    if (std::find(valid.begin(), valid.end(), it.key()) == valid.end())
      throw std::invalid_argument("unknown key: " + it.key());
}
std::uint64_t mix(std::uint64_t x) {
  x ^= x >> 30;
  x *= 0xbf58476d1ce4e5b9ULL;
  x ^= x >> 27;
  x *= 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}
namespace {
struct Fixed final : Partition {
  std::size_t grain;
  explicit Fixed(const Json &j) {
    keys(j, {"name", "grain"});
    auto g = j.value("grain", 64LL);
    if (g <= 0)
      throw std::invalid_argument("grain must be positive");
    grain = static_cast<std::size_t>(g);
  }
  std::vector<Task> split(std::size_t n, std::size_t p) const override {
    std::vector<Task> ts;
    for (std::size_t b = 0; b < n;) {
      auto e = b + std::min(grain, n - b);
      ts.push_back({ts.size(), b, e, ts.size() % p});
      b = e;
    }
    return ts;
  }
};
struct Balanced final : Partition {
  std::size_t chunks;
  explicit Balanced(const Json &j) {
    keys(j, {"name", "chunks_per_worker"});
    auto c = j.value("chunks_per_worker", 8LL);
    if (c <= 0)
      throw std::invalid_argument("chunks must be positive");
    chunks = static_cast<std::size_t>(c);
  }
  std::vector<Task> split(std::size_t n, std::size_t p) const override {
    auto g = n ? 1 + (n - 1) / (p * chunks) : 1;
    return Fixed(Json{{"grain", g}}).split(n, p);
  }
};
struct RoundRobin final : Victim {
  explicit RoundRobin(const Json &j) { keys(j, {"name"}); }
  std::size_t next(std::size_t me, std::size_t p,
                   std::uint64_t &s) const override {
    if (p == 1)
      return p;
    auto v = (me + 1 + (s++ % (p - 1))) % p;
    return v;
  }
};
struct Random final : Victim {
  std::uint64_t seed;
  explicit Random(const Json &j) {
    keys(j, {"name", "seed"});
    seed = j.value("seed", 17ULL);
  }
  std::size_t next(std::size_t me, std::size_t p,
                   std::uint64_t &s) const override {
    if (p == 1)
      return p;
    auto v = mix(++s + seed) % (p - 1);
    return v >= me ? v + 1 : v;
  }
};
struct Disabled final : Timing {
  explicit Disabled(const Json &j) { keys(j, {"name"}); }
  bool enabled() const override { return false; }
  Idle idle(std::size_t) const override { return Idle::wait; }
};
struct Immediate final : Timing {
  explicit Immediate(const Json &j) { keys(j, {"name"}); }
  bool enabled() const override { return true; }
  Idle idle(std::size_t) const override { return Idle::yield; }
};
struct Backoff final : Timing {
  explicit Backoff(const Json &j) { keys(j, {"name"}); }
  bool enabled() const override { return true; }
  Idle idle(std::size_t f) const override {
    return f < 32 ? Idle::yield : Idle::backoff;
  }
};
struct Single final : Migration {
  explicit Single(const Json &j) { keys(j, {"name"}); }
  std::size_t count(std::size_t n) const override {
    return std::min<std::size_t>(1, n);
  }
};
struct Half final : Migration {
  std::size_t cap;
  explicit Half(const Json &j) {
    keys(j, {"name", "cap"});
    auto c = j.value("cap", 32LL);
    if (c <= 0)
      throw std::invalid_argument("cap must be positive");
    cap = static_cast<std::size_t>(c);
  }
  std::size_t count(std::size_t n) const override {
    return std::min(cap, (n + 1) / 2);
  }
};
struct Unbound final : Affinity {
  explicit Unbound(const Json &j) { keys(j, {"name"}); }
  std::vector<int> plan(std::size_t p,
                        const std::vector<int> &) const override {
    return std::vector<int>(p, -1);
  }
};
struct Explicit final : Affinity {
  std::vector<int> cpus;
  explicit Explicit(const Json &j) {
    keys(j, {"name", "cpus"});
    cpus = j.at("cpus").get<std::vector<int>>();
  }
  std::vector<int> plan(std::size_t p,
                        const std::vector<int> &allowed) const override {
    if (cpus.size() != p)
      throw std::invalid_argument("CPU count must equal workers");
    std::set<int> seen;
    for (auto c : cpus)
      if (std::find(allowed.begin(), allowed.end(), c) == allowed.end() ||
          !seen.insert(c).second)
        throw std::invalid_argument("CPU unavailable or repeated");
    return cpus;
  }
};
struct RRPlacement final : Placement {
  explicit RRPlacement(const Json &j) { keys(j, {"name"}); }
  std::size_t owner(const Task &t, std::size_t p) const override {
    return t.id % p;
  }
};
struct Home final : Placement {
  explicit Home(const Json &j) { keys(j, {"name"}); }
  std::size_t owner(const Task &t, std::size_t p) const override {
    return t.home % p;
  }
};
template <class B, class D> void reg(const char *name) {
  Registry<B>::get().add(name,
                         [](const Json &j) { return std::make_unique<D>(j); });
}
const bool registered = [] {
  reg<Partition, Fixed>("fixed_grain");
  reg<Partition, Balanced>("balanced_chunks");
  reg<Victim, RoundRobin>("round_robin");
  reg<Victim, Random>("seeded_random");
  reg<Timing, Disabled>("disabled");
  reg<Timing, Immediate>("immediate");
  reg<Timing, Backoff>("bounded_backoff");
  reg<Migration, Single>("single");
  reg<Migration, Half>("capped_half");
  reg<Affinity, Unbound>("unbound");
  reg<Affinity, Explicit>("explicit");
  reg<Placement, RRPlacement>("round_robin");
  reg<Placement, Home>("home");
  return true;
}();
} // namespace
Policies make_policies(const Json &j) {
  keys(j, {"partition", "victim", "steal_timing", "migration", "affinity",
           "placement"});
  return {Registry<Partition>::get().make(j.at("partition")),
          Registry<Victim>::get().make(j.at("victim")),
          Registry<Timing>::get().make(j.at("steal_timing")),
          Registry<Migration>::get().make(j.at("migration")),
          Registry<Affinity>::get().make(j.at("affinity")),
          Registry<Placement>::get().make(j.at("placement"))};
}
Json list_policies() {
  return {{"partition", Registry<Partition>::get().names()},
          {"victim", Registry<Victim>::get().names()},
          {"steal_timing", Registry<Timing>::get().names()},
          {"migration", Registry<Migration>::get().names()},
          {"affinity", Registry<Affinity>::get().names()},
          {"placement", Registry<Placement>::get().names()}};
}
std::vector<int> allowed_cpus() {
  cpu_set_t mask;
  CPU_ZERO(&mask);
  if (sched_getaffinity(0, sizeof(mask), &mask))
    throw std::system_error(errno, std::generic_category(), "getaffinity");
  std::vector<int> v;
  for (int c = 0; c < CPU_SETSIZE; ++c)
    if (CPU_ISSET(c, &mask))
      v.push_back(c);
  return v;
}
std::vector<int> bind_and_query(int cpu) {
  if (cpu >= 0) {
    cpu_set_t m;
    CPU_ZERO(&m);
    CPU_SET(cpu, &m);
    if (sched_setaffinity(0, sizeof(m), &m))
      throw std::system_error(errno, std::generic_category(), "setaffinity");
  }
  auto actual = allowed_cpus();
  if (cpu >= 0 && actual != std::vector<int>{cpu})
    throw std::runtime_error("affinity mismatch");
  return actual;
}
} // namespace ws
