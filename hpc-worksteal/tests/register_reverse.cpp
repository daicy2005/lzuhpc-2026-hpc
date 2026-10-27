#include "worksteal/policy.hpp"
// Test-only extension. This file and one build-source entry are the entire
// change.
namespace {
struct Reverse final : ws::Victim {
  explicit Reverse(const ws::Json &j) { ws::keys(j, {"name"}); }
  std::size_t next(std::size_t me, std::size_t p,
                   std::uint64_t &state) const override {
    if (p == 1) {
      return p;
    }
    return (me + p - 1 - (state++ % (p - 1))) % p;
  }
};
const bool added = [] {
  ws::Registry<ws::Victim>::get().add("test_reverse", [](const ws::Json &j) {
    return std::make_unique<Reverse>(j);
  });
  return true;
}();
} // namespace
