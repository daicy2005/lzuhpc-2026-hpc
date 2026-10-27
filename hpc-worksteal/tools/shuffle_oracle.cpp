// Independent standard-library probe for the collector's Python shuffle model.
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <random>
#include <vector>

int main() {
  bool first = true;
  std::cout << '[';
  for (auto seed : {0ULL, 42ULL, 138007ULL, 140009ULL, 146021ULL}) {
    for (std::size_t n : {0U, 1U, 2U, 3U, 5U, 17U, 312U, 313U, 896U, 1408U}) {
      std::vector<std::size_t> ids(n);
      std::iota(ids.begin(), ids.end(), 0U);
      std::mt19937_64 rng(seed);
      std::shuffle(ids.begin(), ids.end(), rng);
      if (!first) std::cout << ',';
      first = false;
      std::cout << "{\"seed\":" << seed << ",\"count\":" << n << ",\"ids\":[";
      for (std::size_t i = 0; i < n; ++i) {
        if (i) std::cout << ',';
        std::cout << ids[i];
      }
      std::cout << "]}";
    }
  }
  std::cout << "]\n";
}
