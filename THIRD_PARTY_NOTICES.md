# 来源与版权说明

本仓库中的原始光线追踪题目、源码和参考图来自 [LZUOSS/LZUHPC](https://github.com/LZUOSS/LZUHPC)，使用的上游版本为 `33dad592cd74d8cf36ae7921a29c0e8393034a70`。上游 Apache License 2.0 全文保留于 [upstream/LICENSE](upstream/LICENSE)。原始快照位于 `upstream/HPC.RayTracing/`。

`hpc-raytracing/implementation/` 中各版本基于该题目修改，主要涉及 Makefile、geometry 和 render 中的编译选项、空间加速、像素并行及命中记录处理。最终采用版本的源码身份以 `results/final-selection.json` 为准。为保留原始测量身份，已归档的源码、输入与输出按原字节复制，具体变化和采用情况在报告及附录中说明。原有版权声明保留。

Mini WorkSteal 使用由系统包管理器提供的 nlohmann/json、编译器及标准库，本仓库不打包这些依赖的实现。OpenMP、BVH、SAH 和工作窃取均为已有方法，不作为本项目原创算法声明。
