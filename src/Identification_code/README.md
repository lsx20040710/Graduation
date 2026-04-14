# 🌊 水下海产智能巡检与盘点系统 (Sea Project)

这是一个基于 YOLO 系列模型开发的水下海参检测系统，包含数据转换、模型训练和带 GUI 界面的推理演示功能。

---

## 🚀 使用指南

### 第一步：一键安装环境
打开你的终端（CMD 或 PowerShell），进入到这个文件夹下，运行下面的命令：

```bash
pip install -r requirements.txt
```

> **注意**：如果你有 NVIDIA 显卡，建议先手动安装支持 CUDA 的 PyTorch 以获得更快的训练速度。

---

### 第二步：在独立环境中直接启动官方 LabelImg
你当前验证下来最稳妥的做法，是在单独的 `Python 3.9` 环境里直接启动官方 `labelImg`，不要再依赖仓库里的启动脚本。

推荐流程：

```bash
conda activate 你的标注环境
labelImg
```

如果你还没有准备专门的标注环境，可以参考下面这组命令：

```bash
conda create -n labelimg39 python=3.9 -y
conda activate labelimg39
python -m pip install labelImg lxml
```

官方 `labelImg` 支持两种常用格式：
1. `YOLO TXT`：直接生成训练可用的 `.txt` 标签；
2. `Pascal VOC XML`：生成 `.xml` 标签，适合需要保留 VOC 标注时使用。

默认类别文件在 `raw_data/predefined_classes.txt`，当前预置类别是 `seacucumber`。

注意：
1. 官方 `labelImg` 在 `YOLO TXT` 模式下，会把 `.txt` 直接保存到图片目录；
2. 官方 `labelImg` 在 `Pascal VOC XML` 模式下，可以通过 `Ctrl+R` 指定 XML 输出目录；
3. 模式切换按钮不在右下角，而是在官方 `labelImg` 工具栏中 `Save` 按钮的下方；
4. 你当前已经验证 `Python 3.9` 环境直接启动官方 `labelImg` 最稳妥，文档后续都按这个流程说明；
5. 当前训练流程推荐直接使用 `YOLO TXT` 模式，这样不再需要 XML 转换脚本。

如果你想看更完整的中文说明和常见问题排查，请直接查看：

```text
LabelImg_中文使用说明.md
```

如果你需要先从视频抽帧，再进入标注，请运行：

```bash
python video_frames.py
```

---

### 第三步：划分训练集和验证集
如果你使用 `YOLO TXT` 直接标注，那么图片和标签都在 `raw_data/images` 目录下。此时划分数据集时可以让图片目录和标签目录都指向这个目录：

```bash
python split_dataset.py --image-dir raw_data/images --label-dir raw_data/images --target-root datasets/my_dataset --val-ratio 0.2
```

补充说明：
1. 如果某张图片没有同名 `.txt` 标签，`split_dataset.py` 不会报错；
2. 当前脚本会复制这张图片，但不会复制标签文件；
3. 这类图片会被当成“无目标负样本”参与训练。

---

### 第四步：开始训练模型
当你准备好数据集并配置好 `data.yaml` 后（请确保 `data.yaml` 中的 `path` 指向你的数据集文件夹），运行：

```bash
python train_yolo26.py
```
模型会开始学习如何识别海参，训练好的权重会保存在 `yolo26_runs/` 文件夹下。

---

### 第五步：启动巡检/推理 (带界面)
训练完成后（或者直接使用现有的 `yolo26m.pt`），运行：

```bash
python infer_yolo26.py
```
这会弹出一个简单的窗口，你可以：
1. **加载模型**：选择 `.pt` 权重文件。
2. **选择来源**：支持图片、视频或本地摄像头。
3. **功能**：
   - 开启**水下增强**：自动修正水下偏色和雾感。
   - **智能盘点**：自动统计画面中海参的数量。
   - **生成报告**：任务结束后自动生成巡检报告。

---

## 📁 文件夹结构说明
- `raw_data/`: 存放原始图片、视频和标注。
- `data.yaml`: 训练时的数据集路径配置文件。
- `requirements.txt`: 运行本项目所需的第三方库列表。
- `yolo26n.pt`: 预训练好的模型权重。

---

祝你巡检愉快！🐟🦀
