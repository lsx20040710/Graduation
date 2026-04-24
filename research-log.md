# Research Log

按时间顺序记录研究决策、实验动作和阶段性结论。

| # | Date | Type | Summary |
|---|------|------|---------|
| 1 | 2026-04-15 | bootstrap | 已安装 Orchestra AI Research Skills，并读取 autoresearch 规则。检查当前仓库后确认：已有相机标定脚本、YOLO 海参检测训练与推理模块、本地文献目录，但“视觉结果 -> 伺服计算 -> 执行器命令 -> 执行反馈”的闭环链路尚未在项目根层统一整理。已初始化 `research-state.yaml`、`findings.md` 与 `literature/` 工作区，形成初始研究假设。 |
| 2 | 2026-04-20 | refocus | 当前实现方向调整为“电脑通过 USB/TTL 直控六个舵机的双关节六绳驱动软体机器人视觉伺服实验平台”。机构参考 `DewiEtAl-2024-TendonDrivenContinuumRobot-ModularStiffness-ZHTranslation.pdf.pdf` 的模块化连续体关节思路，但改成每个关节三个单元、三根绳控制，整机两个关节共六根绳。`src/Gradua` 中的 ROS 包保留为后续改进储备，不再作为当前主线前提。 |
