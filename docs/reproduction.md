# Linux 构建与复现

## 光线追踪

在仓库根目录设定官方图像目录，然后进入最终源码：

```bash
export OFFICIAL="$PWD/upstream/HPC.RayTracing"
cd hpc-raytracing/implementation/16fafcdc65f1ac9c25a14519ead75b345c88b82cd500f1da05e9f07ca99b6bc2
make -B -j4
./build/RayTracing 1200 200 out.ppm
python3 "$OFFICIAL/tools/check_psnr.py" "$OFFICIAL/reference.ppm" out.ppm
```

依赖 C++20、G++ 和 OpenMP。上述为功能检查；历史计时还使用记录中的 32 线程、close 和显式 OMP_PLACES，CPU 编号依赖机器，不能直接保证换机耗时。

## Mini WorkSteal

```bash
sudo apt-get update
sudo apt-get install -y g++ cmake python3 nlohmann-json3-dev
cd hpc-worksteal
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/worksteal --config configs/runtime/diagnostic.json
```

默认 Release 是功能检查构建。历史优化构建须采用 `configs/verified/builds.json` 或 `configs/memory-interleaved/builds.json` 中的选项和源码来源；相关历史源码快照及构建身份亦保留。当前构建和旧测量二进制不能混称。原生 Linux 新目录功能复现记录位于 `submission/reproduction/20261025/`；这次材料整理没有新增构建或计时。

`.devcontainer` 是未实际构建验证的配置，不将原生 Linux 检查写成容器通过。完整命令与已知限制见[报告附录](appendices.md)。
