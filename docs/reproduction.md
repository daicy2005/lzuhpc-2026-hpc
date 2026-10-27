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

依赖 C++20、G++ 和 OpenMP。上述命令用于构建和检查输出图像。报告中的性能测试还设置了 32 线程、close 和显式 OMP_PLACES；换机器时需要调整 CPU 编号，运行时间也可能不同。

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

默认 Release 可用于检查功能。复现实验中的优化版本，还需使用 `configs/verified/builds.json` 或 `configs/memory-interleaved/builds.json` 中列出的源码和编译选项。仓库保留了对应源码快照。Linux 下的重新构建和测试结果在 `submission/reproduction/20261025/`。

`.devcontainer` 配置尚未实际构建。更多构建选项和配置说明见[报告附录](appendices.md)。
