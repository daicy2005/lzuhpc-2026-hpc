// Standalone sequential diagnostic; intentionally not linked into the runtime.
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <nlohmann/json.hpp>

using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;
constexpr std::uint64_t offset = 14695981039346656037ULL;

static std::uint64_t mix(std::uint64_t x) {
  x ^= x >> 30;
  x *= 0xbf58476d1ce4e5b9ULL;
  x ^= x >> 27;
  x *= 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}

// Explicit boundaries are diagnostic instrumentation, not production codegen.
[[gnu::noinline]] static std::unique_ptr<std::uint64_t[]>
allocate_words(std::size_t n, bool overwrite) {
  return overwrite ? std::make_unique_for_overwrite<std::uint64_t[]>(n)
                   : std::make_unique<std::uint64_t[]>(n);
}
[[gnu::noinline]] static void fill_words(std::uint64_t *data, std::size_t n,
                                       std::uint64_t seed) {
  for (std::size_t i = 0; i < n; ++i) data[i] = mix(seed + i);
}
[[gnu::noinline]] static std::uint64_t hash_words(const std::uint64_t *data,
                                               std::size_t n) {
  std::uint64_t h = offset;
  for (std::size_t i = 0; i < n; ++i)
    for (int byte = 0; byte < 8; ++byte) {
      h ^= (data[i] >> (byte * 8)) & 255;
      h *= 1099511628211ULL;
    }
  return h;
}
static rusage usage() {
  rusage r{};
  if (getrusage(RUSAGE_SELF, &r) != 0) throw std::runtime_error("getrusage failed");
  return r;
}
static Json delta(const rusage &a, const rusage &b,
                  Clock::time_point start, Clock::time_point end) {
  return {{"seconds", std::chrono::duration<double>(end-start).count()},
          {"minor_faults", b.ru_minflt-a.ru_minflt},
          {"major_faults", b.ru_majflt-a.ru_majflt}};
}
static Json run(std::size_t n, std::uint64_t seed, bool overwrite, bool selftest) {
  // Four fixed boundary snapshots; each measured wall interval includes the
  // ending rusage query. Do not interpret sub-microsecond allocation as exact.
  const auto r0 = usage(); const auto t0 = Clock::now();
  auto data = allocate_words(n, overwrite);
  const auto r1 = usage(); const auto t1 = Clock::now();
  if (selftest && !overwrite)
    for (std::size_t i = 0; i < n; ++i)
      if (data[i] != 0) throw std::runtime_error("zero initialization mismatch");
  fill_words(data.get(), n, seed);
  const auto r2 = usage(); const auto t2 = Clock::now();
  const auto h = hash_words(data.get(), n);
  const auto r3 = usage(); const auto t3 = Clock::now();
  // Full check stays outside the measured three-stage interval.
  for (std::size_t i = 0; i < n; ++i)
    if (data[i] != mix(seed+i)) throw std::runtime_error("stored data mismatch");
  std::ostringstream text;
  text << std::hex << std::setw(16) << std::setfill('0') << h;
  Json j{{"words", n}, {"seed", seed}, {"allocation", overwrite ? "overwrite" : "zeroed"},
         {"data_hash_fnv1a64", text.str()}, {"compared_words", n}, {"pass", true},
         {"phases", {{"allocation", delta(r0,r1,t0,t1)},
                     {"fill", delta(r1,r2,t1,t2)}, {"fnv", delta(r2,r3,t2,t3)}}},
         {"combined", delta(r0,r3,t0,t3)}, {"selftest", selftest}};
  if (selftest) {
    j["data"] = Json::array();
    for (std::size_t i = 0; i < n; ++i) j["data"].push_back(data[i]);
  }
  return j;
}
int main(int argc, char **argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--selftest") {
      Json rows = Json::array();
      for (std::size_t n : {0U,1U,2U,3U,17U,4097U})
        for (std::uint64_t seed : {0ULL,42ULL,UINT64_MAX-2ULL})
          for (bool overwrite : {false,true}) rows.push_back(run(n,seed,overwrite,true));
      std::cout << Json{{"pass", true}, {"cases", rows}}.dump() << '\n';
    } else {
      if (argc != 4) throw std::invalid_argument("expected words seed zeroed|overwrite");
      const auto n = std::stoull(argv[1]);
      const auto seed = std::stoull(argv[2]);
      const std::string mode = argv[3];
      if (n > 256ULL*1024*1024 || (mode != "zeroed" && mode != "overwrite"))
        throw std::invalid_argument("invalid bounds or allocation");
      std::cout << run(static_cast<std::size_t>(n),seed,mode=="overwrite",false).dump() << '\n';
    }
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
