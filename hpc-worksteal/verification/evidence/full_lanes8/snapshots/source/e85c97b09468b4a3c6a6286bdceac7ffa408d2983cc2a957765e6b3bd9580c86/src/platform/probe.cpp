#include "worksteal/policy.hpp"
#include <cpuid.h>
#include <fstream>
#include <iostream>
#include <sys/utsname.h>
#include <thread>
int main() {
  try {
    ws::Json cpus = ws::Json::array();
    auto allowed = ws::allowed_cpus();
    for (auto cpu : allowed) {
      ws::Json result;
      std::thread t([&] {
        auto mask = ws::bind_and_query(cpu);
        unsigned a = 0, b = 0, c = 0, d = 0;
        __cpuid_count(0, 0, a, b, c, d);
        auto maximum = a;
        ws::Json caches = ws::Json::array();
        for (unsigned i = 0; i < 32; ++i) {
          __cpuid_count(4, i, a, b, c, d);
          if (!(a & 31))
            break;
          auto size = std::uint64_t((b & 4095) + 1) * (((b >> 12) & 1023) + 1) *
                      ((b >> 22) + 1) * (std::uint64_t(c) + 1);
          caches.push_back(
              {{"level", (a >> 5) & 7},
               {"type", a & 31},
               {"bytes", size},
               {"max_addressable_logical_sharers", ((a >> 14) & 4095) + 1}});
        }
        auto leaf = maximum >= 31 ? 31U : 11U;
        ws::Json topology = ws::Json::array();
        unsigned apic = 0;
        for (unsigned i = 0; i < 8; ++i) {
          __cpuid_count(leaf, i, a, b, c, d);
          if (!(b & 65535))
            break;
          apic = d;
          topology.push_back({{"shift", a & 31},
                              {"type", (c >> 8) & 255},
                              {"logical_count", b & 65535},
                              {"x2apic", d}});
        }
        unsigned core_type = 0;
        if (maximum >= 26) {
          __cpuid_count(26, 0, a, b, c, d);
          core_type = a >> 24;
        }
        result = {{"linux_cpu", cpu}, {"mask", mask},
                  {"x2apic", apic},   {"hybrid_core_type", core_type},
                  {"caches", caches}, {"topology", topology}};
      });
      t.join();
      cpus.push_back(result);
    }
    utsname u{};
    uname(&u);
    std::cout << ws::Json{{"kernel", u.release},
                          {"machine", u.machine},
                          {"allowed", allowed},
                          {"cpus", cpus},
                          {"source",
                           "CPUID leaves 4, 0x1f/0xb, 0x1a executed after "
                           "verified singleton sched_setaffinity"}}
                     .dump(2)
              << '\n';
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
