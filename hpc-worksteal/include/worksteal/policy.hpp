#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <vector>

namespace ws {
using Json = nlohmann::json;
struct Task {
  std::size_t id, begin, end, home;
};
struct Partition {
  virtual ~Partition() = default;
  virtual std::vector<Task> split(std::size_t n, std::size_t p) const = 0;
};
struct Victim {
  virtual ~Victim() = default;
  virtual std::size_t next(std::size_t me, std::size_t p,
                           std::uint64_t &state) const = 0;
};
enum class Idle { wait, yield, backoff };
struct Timing {
  virtual ~Timing() = default;
  virtual bool enabled() const = 0;
  virtual Idle idle(std::size_t failures) const = 0;
};
struct Migration {
  virtual ~Migration() = default;
  virtual std::size_t count(std::size_t available) const = 0;
};
struct Affinity {
  virtual ~Affinity() = default;
  virtual std::vector<int> plan(std::size_t p,
                                const std::vector<int> &allowed) const = 0;
};
struct Placement {
  virtual ~Placement() = default;
  virtual std::size_t owner(const Task &t, std::size_t p) const = 0;
};

template <class T> class Registry {
public:
  using Factory = std::function<std::unique_ptr<T>(const Json &)>;
  static Registry &get() {
    static Registry instance;
    return instance;
  }
  void add(const std::string &name, Factory f) {
    if (!factories.emplace(name, std::move(f)).second)
      throw std::invalid_argument("duplicate policy: " + name);
  }
  std::unique_ptr<T> make(const Json &j) const {
    auto it = factories.find(j.at("name").get<std::string>());
    if (it == factories.end())
      throw std::invalid_argument("unknown policy: " + j.dump());
    return it->second(j);
  }
  std::vector<std::string> names() const {
    std::vector<std::string> n;
    for (auto &[key, unused] : factories) {
      (void)unused;
      n.push_back(key);
    }
    return n;
  }

private:
  std::map<std::string, Factory> factories;
};
struct Policies {
  std::unique_ptr<Partition> partition;
  std::unique_ptr<Victim> victim;
  std::unique_ptr<Timing> timing;
  std::unique_ptr<Migration> migration;
  std::unique_ptr<Affinity> affinity;
  std::unique_ptr<Placement> placement;
};
void keys(const Json &j, std::initializer_list<const char *> valid);
Policies make_policies(const Json &j);
Json list_policies();
std::vector<int> allowed_cpus();
std::vector<int> bind_and_query(int cpu);
std::uint64_t mix(std::uint64_t x);
} // namespace ws
