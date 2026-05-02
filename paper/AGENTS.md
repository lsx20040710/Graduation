# AGENTS.md

## 论文图片素材规则

在修改 `paper/tex/` 下的 LaTeX 论文时，所有论文中需要引用的图片必须先复制到 `paper/prepared_images/`，再从 LaTeX 文件中引用该目录下的副本。

图片文件名必须使用 ASCII 命名，只允许英文字母、数字、下划线和短横线，例如：

- `fig2_1_overall_structure.png`
- `fig3_4_undistort_preview.png`
- `extra_training_curves.png`

不要在 LaTeX 中直接引用中文文件名、中文目录、空格路径或 `experiments/results/` 里的原始图片。原始图片可以保留在实验目录中，但写论文时必须使用 `paper/prepared_images/` 中重命名后的写作副本。

这样做是为了降低 XeLaTeX、SyncTeX、PDF 批注工具、不同编辑器和跨平台编译时对中文路径或特殊字符支持不一致导致的图片缺失、编译异常和定位失败风险。
