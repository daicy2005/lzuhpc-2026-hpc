# 图表说明与重绘

报告中的两张性能图先用图像生成工具设计布局，再由 Python 读取原有实验结果绘制为 SVG。PDF 中嵌入的是矢量图。

布局参考了 [TensorIR（ASPLOS 2023）图 10、11](https://arxiv.org/pdf/2207.04296)和 [Ligra（PPoPP 2013）图 2、3](https://people.csail.mit.edu/jshun/ligra.pdf)，主要借鉴分面、坐标对齐和简洁的标注方式。参考论文中的数据没有用于本报告。

- 光追：横轴采用对数刻度，空心圆表示三次测量，菱形表示中位数，短线表示观测到的最小至最大值。圆点在纵向错开以便辨认；纵向位置不表示耗时。短线不是置信区间。
- WorkSteal：按 seed 分为两个子图，共用 0 到 6 的纵轴。柱高仍为 off 中位数 / on 中位数，虚线为 1。颜色和纹理共同区分两种布局，方便黑白打印。

在仓库根目录执行以下命令即可重画两张图。脚本只使用 Python 标准库，不会启动性能实验。

```bash
python3 report/figure-source/paper_figure_style.py \
  --data report/figure-data-v2.json \
  --outdir report/assets
```

SVG 使用 Microsoft YaHei 字体。其他系统可安装该字体或替换为本机的中文字体，数据与坐标不受影响。
