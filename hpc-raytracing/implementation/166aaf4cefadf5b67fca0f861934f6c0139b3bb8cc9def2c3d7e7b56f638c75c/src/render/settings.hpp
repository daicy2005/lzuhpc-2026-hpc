#pragma once

#include <cerrno>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <string>

inline int setting_int(const char *name, int fallback)
{
    const char *value = std::getenv(name);
    if(!value)
        return fallback;
    char *end = nullptr;
    errno = 0;
    const long parsed = std::strtol(value, &end, 10);
    if(errno || end == value || *end || parsed < 1 || parsed > std::numeric_limits<int>::max())
        throw std::invalid_argument(std::string("Invalid positive integer: ") + name);
    return static_cast<int>(parsed);
}

inline std::string setting_text(const char *name, const char *fallback)
{
    const char *value = std::getenv(name);
    return value ? value : fallback;
}
