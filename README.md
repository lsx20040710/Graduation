# A-Graduation

本仓库用于毕业设计项目：面向海参捕捞实验的双关节绳驱软体机器人视觉伺服控制。

当前主线是 PC 端闭环验证：USB 相机获取图像，YOLO 检测海参目标，计算图像平面误差，再通过 USB/TTL 控制六个舵机驱动两关节软体机器人完成对准。

## 目录结构

```text
A-Graduation/
├── AGENTS.md                 # 项目协作约定和代码风格要求
├── README.md                 # 根目录说明
├── experiments/              # 实验方案、分析模板和本地结果归档
├── paper/                    # 论文写作工作区；正文、图片和个人稿件默认不提交
├── ppt/                      # 本地汇报材料，默认不提交
├── references/               # 论文、资料和文献条目
├── src/
│   ├── calibration/          # USB 相机采集、棋盘格标定和去畸变预览
│   ├── Identification_code/  # YOLO 数据准备、训练、推理和跟踪入口
│   ├── control/              # 运动学、舵机控制和视觉伺服控制脚本
│   └── Gradua/               # ROS2 预留包，当前不是主线运行入口
├── build/                    # ROS2/colcon 构建产物，默认不提交
├── install/                  # ROS2/colcon 安装产物，默认不提交
└── log/                      # ROS2/colcon 日志，默认不提交
```

## 主要模块

`src/calibration/` 负责相机相关工具，包括棋盘格采集、标定参数生成、原始预览和去畸变预览。标定图和输出参数通常与本机相机、镜头和分辨率绑定，默认作为本地数据管理。

`src/Identification_code/` 负责识别链路，包括数据抽帧、数据集划分、YOLO26 训练、推理、ByteTrack 跟踪和误差记录。`raw_data/`、`datasets/`、`runs/` 和 `.pt` 权重默认按本地资产处理。

`src/control/` 负责机器人控制链路，包括单关节/双关节运动学、键盘控制、舵机驱动验证和视觉伺服控制。这里是当前 PC + USB/TTL 硬件闭环的核心代码区。

`experiments/` 用于保存实验协议和分析说明。每个实验主题建议包含 `protocol.md`、`code/`、`analysis.md` 和本地 `results/`；其中 `results/` 是原始日志、视频、图片和导出指标，默认不提交。

`paper/` 用于论文写作。`paper/tex/bachelor/` 是可复用 LaTeX 模板；`paper/tex/main/`、`paper/prepared_images/`、`paper/docs/` 和 `paper/tex/Idea/` 属于个人论文正文、图片、草稿或阶段稿，默认不提交。

## 版本控制规则

仓库默认提交可复用代码、脚本、说明文档、模板和非个人化配置；默认不提交个人论文、实验结果、原始采集数据、训练输出、模型权重、汇报 PPT、本机 IDE 配置和运行缓存。

`.gitignore` 已按隐私优先设置，但 Git 只会自动忽略未跟踪文件。已经被 Git 跟踪的论文、图片、实验结果或本机文件，需要先用 `git rm --cached <path>` 从索引移除，之后 `.gitignore` 才能阻止它们继续进入提交。

## 当前硬件假设

当前阶段使用单 USB 相机、六个 UART/TTL 总线舵机和双关节三绳驱动软体机器人。ROS2 目录保留为后续扩展，不作为当前视觉伺服主线的必需运行入口。
