# 实验工作区

后续每个假设单独建一个子目录，推荐结构如下：

```text
experiments/
  H1-image-error-centering/
    protocol.md
    code/
    results/
    analysis.md
```

建议规则：

- `protocol.md` 先写实验目的、变量、预测，再开始跑实验。
- `results/` 保存原始日志、表格、图片和导出指标。
- `analysis.md` 只写“结果说明了什么”，不要把原始数据混进去。
