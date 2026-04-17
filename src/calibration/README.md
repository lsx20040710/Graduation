# calibration 使用说明

## 1. 目录作用

这个目录用于完成 USB 相机的标定准备、棋盘格采集、离线标定以及去畸变预览。

结合本项目的实际用途，它的作用不是做通用视觉 Demo，而是为后续海参采捕视觉伺服链路提供稳定、可复用的相机内参与去畸变结果。

当前目录里的几个主要脚本如下：

| 文件 | 作用 |
| --- | --- |
| `capture_checkerboard.py` | 采集棋盘格图片，供后续相机标定使用 |
| `calibrate_checkerboard.py` | 根据采集好的棋盘格图片计算相机内参与畸变系数 |
| `preview_undistort.py` | 基于标定结果预览实时画面或单张图片的去畸变效果 |
| `calibrate_usb_camera.py` | 上面几个功能的底层实现与统一命令入口 |

---

## 2. 这次审阅后的结论

我检查了当前脚本里所有和摄像头分辨率相关的部分，结论如下：

- 原来已经支持通过 `--width` 和 `--height` 手动指定分辨率。
- 原来**没有**一个明确的“画质档位切换”入口，比如 `720p / 1080p / 4k` 这种直接切换。
- 原来目录下也**没有**说明这件事的 README。

因此，这次已经补上了两部分内容：

- 为采集和预览脚本新增了 `--quality` 画质预设参数。
- 为该目录新增本 README，说明完整使用流程。

---

## 3. 现在怎么切换画质

### 3.1 查看支持的画质预设

先执行下面任意一个命令：

```bash
python capture_checkerboard.py --list-quality-presets
python preview_undistort.py --list-quality-presets
```

当前内置预设如下：

- `480p` -> `640x480`
- `720p` -> `1280x720`
- `900p` -> `1600x900`
- `1080p` -> `1920x1080`
- `1440p` -> `2560x1440`
- `4k` -> `3840x2160`

默认预设是 `1080p`。

### 3.2 直接按画质档位切换

采集棋盘格时：

```bash
python capture_checkerboard.py --cols 10 --rows 7 --quality 720p
```

实时去畸变预览时：

```bash
python preview_undistort.py --calibration-file output/camera_calibration.json --quality 720p
```

### 3.3 手动指定宽高

如果你的摄像头支持一些非标准分辨率，或者你想精确测试某个分辨率，可以继续直接写宽高：

```bash
python capture_checkerboard.py --cols 10 --rows 7 --width 1280 --height 800
python preview_undistort.py --calibration-file output/camera_calibration.json --width 1280 --height 800
```

说明：

- `--width` 和 `--height` 一旦同时提供，会覆盖 `--quality`。
- 如果只写了 `--width` 或只写了 `--height`，脚本会报错，避免出现半配置状态。

### 3.4 怎么确认摄像头是否真的切过去了

需要注意，脚本只是“向摄像头驱动请求”某个分辨率，摄像头是否真正按这个分辨率输出，最终取决于：

- 相机本身是否支持该分辨率
- 当前驱动是否支持该分辨率
- 当前像素格式 `--fourcc` 是否匹配

所以运行时请看窗口左上角状态文字：

- `request` 表示脚本请求的分辨率
- `actual` 或 `raw size` 表示摄像头实际输出的分辨率

如果两者不一致，说明驱动没有按请求值生效，此时建议：

- 换一个 `--quality`
- 或者切换 `--fourcc MJPG` / `--fourcc YUYV`
- 再观察实际输出是否变化

---

## 4. 推荐使用流程

### 第一步：确认摄像头索引

```bash
python capture_checkerboard.py --list-cameras
```

如果不确定哪个索引是目标相机，也可以直接运行采集脚本，程序会先探测摄像头并让你选择。

### 第二步：采集棋盘格图片

示例：

```bash
python capture_checkerboard.py --cols 10 --rows 7 --quality 1080p
```

如果预览卡顿，可以降低检测负载：

```bash
python capture_checkerboard.py --cols 10 --rows 7 --quality 720p --preview-scale 0.4 --detect-interval 3
```

采集阶段建议注意：

- 标定时使用什么工作分辨率，采集时就尽量用什么分辨率。
- 棋盘格要覆盖画面中心、边缘、不同倾角和不同距离。
- 不要只拍中心正对图像，否则边缘畸变估计会不稳定。
- 建议至少保留 25 到 40 张质量较好的样本图。

按键说明：

- `空格`：检测到完整棋盘格后保存当前原始图像
- `Q` 或 `ESC`：退出采集

### 第三步：执行标定

```bash
python calibrate_checkerboard.py --cols 10 --rows 7 --square-size-mm 20 --model fisheye
```

常用说明：

- `--cols` 和 `--rows` 是棋盘格**内角点数**，不是黑白方格数。
- 如果是普通镜头，可以尝试 `--model standard`。
- 如果是广角或畸变较明显的镜头，通常优先尝试 `--model fisheye`。

输出结果默认在 `output/` 目录下，包括：

- `camera_calibration.json`
- `camera_info.yaml`
- `debug_corners/` 角点检测可视化结果

### 第四步：预览去畸变效果

```bash
python preview_undistort.py --calibration-file output/camera_calibration.json --quality 1080p
```

如果左右拼接太宽，可以切换布局：

```bash
python preview_undistort.py --calibration-file output/camera_calibration.json --quality 1080p --layout vertical
```

如果只想验证某张图片：

```bash
python preview_undistort.py --calibration-file output/camera_calibration.json --image captures/calib_000.jpg
```

---

## 5. 统一入口脚本

如果你更习惯用一个脚本切全部流程，也可以直接用 `calibrate_usb_camera.py`：

```bash
python calibrate_usb_camera.py capture --cols 10 --rows 7 --quality 720p
python calibrate_usb_camera.py calibrate --cols 10 --rows 7 --square-size-mm 20
python calibrate_usb_camera.py preview --calibration-file output/camera_calibration.json --quality 720p
```

这个脚本和独立入口脚本共用同一套底层逻辑，区别只是入口组织方式不同。

---

## 6. 常见排查建议

### 6.1 默认明明写了 `720p`，为什么还是显示 `1920x1080`

优先看窗口状态里的 `actual` 或 `raw size`：

- 如果还是 `1920x1080`，说明驱动没有采纳你的请求。
- 可以尝试把 `--fourcc` 从 `MJPG` 改为 `YUYV`，或者反过来。
- 也可能是这个摄像头在当前接口模式下只支持固定输出。

### 6.2 标定时报图像尺寸不一致

这通常是因为你混用了不同分辨率的采集结果。

建议做法：

- 每次标定只使用同一分辨率的一组图像
- 切换画质后单独建一套采集目录

### 6.3 预览能跑，但是去畸变结果错位

当前脚本已经在预览时对“分辨率变化”做了重新映射处理。

如果还出现明显错位，优先检查：

- 当前实时输入分辨率是否和你理解的一致
- 标定时的图像是否全部来自同一分辨率
- 标定模型是否选错，例如应使用 `fisheye` 却用了 `standard`

---

## 7. 建议的项目内使用原则

结合本课题“水下海参采捕机器人伸缩式吸取末端视觉伺服”的实际需求，这个目录建议按下面方式使用：

- 标定分辨率尽量与后续视觉伺服运行分辨率保持一致。
- 如果后续控制链路实时性紧张，可以先用 `720p` 或 `900p` 做在线测试。
- 如果后续识别精度不足，再评估是否提高到 `1080p` 或更高。
- 切换分辨率后，最好重新采集并重新标定，不要直接混用旧内参。

这样做的原因很直接：

- 分辨率变化会改变像素坐标尺度
- 视觉误差到控制量的映射会受到影响
- 去畸变和伺服误差估计也会一起受到影响

对这个项目来说，分辨率不是单纯“画质好不好”的问题，而是会影响后续视觉闭环稳定性的一个基础配置项。

---

## 8. ROS2 运行期接入说明

当前 `src/calibration` 目录仍然只负责离线标定，不负责 ROS2 运行期图像话题处理。

也就是说，本目录下的：

- `calibrate_checkerboard.py`
- `calibrate_usb_camera.py`
- `preview_undistort.py`

主要用途仍然是：

- 采集棋盘格
- 计算相机内参与畸变系数
- 导出 `camera_info.yaml`
- 本地预览去畸变效果

如果你在 Ubuntu + ROS2 环境中已经安装了 `ros-humble-usb-cam`，建议把运行期图像链路交给新增的 `src/vision_bringup` 包，而不是把这里的本地 OpenCV 预览脚本改成 ROS2 节点。

推荐链路如下：

```text
usb_cam -> /camera/image_raw + /camera/camera_info
        -> image_proc::RectifyNode
        -> /camera/image_rect
        -> 下游检测 / 视觉伺服
```

这样划分后，职责边界会更清楚：

- Windows 端：更新 `src/calibration/output/camera_info.yaml`
- Ubuntu 端：使用 `vision_bringup` 启动 `usb_cam` 和运行期正畸

ROS2 运行命令请查看：

- `src/vision_bringup/README.md`

这也是当前更适合本课题的做法，因为视觉伺服链路真正关心的是：

- 原始图像是否稳定进入 ROS2
- 标定参数是否伴随图像一起发布
- 正畸后的图像是否能继续送入检测和控制节点

而不是在运行时重复走一套独立的 OpenCV 本地窗口预览流程。
