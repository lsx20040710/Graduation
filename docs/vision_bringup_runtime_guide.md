# vision_bringup 运行说明

本文档只说明 `vision_bringup` 当前保留的主处理链路，不再包含任何自动预览逻辑。

## 1. 当前结构

当前运行期链路固定为：

- `usb_cam` 发布 `/camera/image_raw`
- `usb_cam` 发布 `/camera/camera_info`
- `vision_bringup/rectify_node` 订阅上述两个话题，并发布 `/camera/image_rect`

当前默认运行基线为：

- `320 x 240`
- `30 FPS`
- `MJPEG -> rgb8`

当前版本的目标很明确：

- 先保证单目采图和正畸数据流稳定
- 不再把 GUI 预览负载混进运行结果
- 让后续检测节点和视觉伺服节点直接面向 `/camera/image_rect`

## 2. 运行命令

在工作空间根目录执行：

```bash
source /opt/ros/humble/setup.bash
colcon build --packages-select vision_bringup
source install/setup.bash
ros2 run vision_bringup vision_bringup
```

也可以直接用 launch：

```bash
ros2 launch vision_bringup camera_rectify.launch.py
```

运行时会自动把配置里的稳定相机别名 `/dev/v4l/by-id/...` 解析成当前实际的 `/dev/videoN`，避免 USB 透传后设备号漂移导致 `usb_cam` 直接起不来。

兼容说明：

```bash
ros2 run vision_bringup vision_bringup --preview-mode none
```

- `--preview-mode none` 仍然可用
- 如果传 `raw`、`rectified` 或 `both`，当前版本会提示该参数已被忽略，并只启动主处理链路

## 3. 运行后应该看到什么

正常情况下，至少应满足：

- `ros2 pkg executables | grep vision_bringup` 能看到 `vision_bringup vision_bringup`
- `ros2 topic list | grep /camera` 能看到 `/camera/image_raw`、`/camera/camera_info`、`/camera/image_rect`
- `ros2 topic echo --once /camera/camera_info` 能读到非零内参
- `ros2 topic info /camera/image_rect --verbose` 能看到发布者是 `/camera/rectify_node`
- `/camera/image_rect` 统一使用 `bgr8` 编码，并由 `rectify_node` 以 `RELIABLE` QoS 发布

对主链验证，优先看这两个点：

- `/camera/camera_info` 是否有效
- `/camera/image_rect` 是否稳定发布

## 4. 单独调试 `rectify_node`

如果你怀疑问题不在 `usb_cam`，而在正畸节点本身，最直接的方法就是把 `rectify_node` 独立出来调试。

先注意：

- `rectify_node` 只做正畸，不负责开相机
- 它默认使用相对话题名 `image_raw`、`camera_info`、`image_rect`
- 为了让它接到当前主链，单独运行时应加上 `/camera` 命名空间

推荐命令如下。

终端 1，单独启动 `usb_cam`：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
USB_CAM_CONFIG="$(ros2 pkg prefix vision_bringup)/share/vision_bringup/config/usb_cam.yaml"
ros2 run usb_cam usb_cam_node_exe \
  --ros-args \
  -r __ns:=/camera \
  --params-file "$USB_CAM_CONFIG" \
  -p video_device:=/dev/video1
```

终端 2，单独启动 `rectify_node`：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run vision_bringup rectify_node --ros-args -r __ns:=/camera
```

终端 3，验证结果：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 topic list | grep /camera
ros2 topic echo --once /camera/camera_info
ros2 topic info /camera/image_rect --verbose
ros2 topic hz /camera/image_rect
```

判定标准：

- `/camera/camera_info` 有非零内参
- `/camera/image_rect` 发布者是 `/camera/rectify_node`
- `/camera/image_rect` 的 QoS 是 `RELIABLE`
- `/camera/image_rect` 有持续频率输出

如果你要人工看图，可以另外安装并手动运行：

```bash
sudo apt install ros-humble-image-view
ros2 run image_view image_view --ros-args -r image:=/camera/image_rect
```

更可靠的调试依据仍然是话题和日志，不是单纯看有没有窗口。

### 4.1 看稳定性，不只看“能不能启动”

当前 `rectify_node` 会周期性打印运行统计，格式类似：

```text
Rectify stats [5.0s] in=150 (29.95 Hz), out=150 (29.95 Hz), ratio=1.00, proc_avg=4.2 ms, proc_max=7.1 ms, input_gap_max=36.8 ms, skips(info/empty/map/in_conv/out_conv)=0/0/0/0/0, totals(in/out)=300/300
```

这条日志比单纯看话题名更重要，因为它直接反映：

- 节点在这个时间窗口内收到了多少原图
- 实际发布了多少正畸图
- 输入和输出是否基本一一对应
- 处理耗时是否接近你的帧周期上限
- 是否存在缺内参、空帧、映射失败或编解码失败

判断标准建议用这几个：

- `ratio` 尽量接近 `1.00`
- `out` 不应长期明显低于 `in`
- `proc_avg`、`proc_max` 不应长期接近帧周期
- `skips(info/empty/map/in_conv/out_conv)` 最好长期为 `0`

如果日志里反复出现：

```text
publish_ratio below threshold
```

或：

```text
output stalled
```

就不要继续往后做检测和控制了，先把视觉正畸链跑稳。对这个项目来说，稳定持续发布比强行保留高画质更重要。

如果你要调统计频率，可以直接给 `rectify_node` 传参数：

```bash
ros2 run vision_bringup rectify_node --ros-args -r __ns:=/camera -p diagnostics_period_sec:=2.0
```

可用参数：

- `diagnostics_period_sec`：统计输出周期，默认 `5.0`
- `stale_stream_warn_sec`：输入或输出多久没更新就报警，默认 `2.0`
- `min_publish_ratio_warn`：输入输出比低于多少时报警，默认 `0.9`

### 4.2 本次已确认的瓶颈位置

当前环境中，真正的问题不是相机硬件，而是运行环境和图像消息路径：

- 相机直接通过 `ffmpeg` 采集时可以稳定跑起来
- 设备号会在 `/dev/videoN` 之间漂移，这是第一层问题
- 进入 ROS2 + Python 链之后，大分辨率图像会显著拖慢有效输入频率，这是第二层问题

实测结果可以概括为：

- `1280x720 @ 20`：大约 `1 ~ 4 Hz`
- `640x480 @ 30`：大约 `5 ~ 11 Hz`
- `320x240 @ 30`：可稳定接近 `30 Hz`

所以当前默认基线被压到 `320x240 @ 30`。如果你后面想重新提高分辨率，必须每次都看 `Rectify stats ...` 日志，而不是只看预览窗口。

## 5. 如果运行不了，一般卡在哪里

### 5.1 ROS2 运行依赖没装

至少要有：

```bash
sudo apt install ros-humble-usb-cam ros-humble-cv-bridge
```

如果没装：

- `colcon build` 可能通过
- 但 `ros2 run vision_bringup vision_bringup` 运行时会在拉起 `usb_cam` 或 `rectify_node` 时失败

### 5.2 没有正确 source 环境

如果你忘了：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

会表现为：

- `ros2 run` 找不到 `vision_bringup`
- 或者找不到包内新的可执行入口

### 5.3 相机设备层有问题

如果 `/dev/video0` 不存在、被占用、或者当前用户没有访问权限，会卡在 `usb_cam` 启动阶段。

典型表现：

- `usb_cam` 无法打开设备
- 没有 `/camera/image_raw`
- 后续 `/camera/image_rect` 也不会有

### 5.4 标定文件有问题

当前默认读取：

`/home/lsx/Graduation/src/calibration/output/camera_info.yaml`

如果这个文件缺失、内容损坏、或者内参矩阵全为 0，会表现为：

- `/camera/camera_info` 异常
- `/camera/image_rect` 不发布有效正畸图
- `rectify_node` 会报内参无效

### 5.5 图形界面环境不可用

当前版本默认不启动任何图形窗口，所以即使没有桌面环境，也不影响采图和正畸主链。

如果你后面要手动运行 `image_view` 做单独调试，再考虑 `DISPLAY` 或 X11 转发问题。

### 5.6 `unknown control` 告警

如果日志里出现：

```text
unknown control 'white_balance_temperature_auto'
unknown control 'exposure_auto'
unknown control 'focus_auto'
```

这通常不是主链路故障，而是当前相机暴露的 V4L2 控件名字和 `usb_cam` 固定控件名不完全对应。

它的影响是：

- 自动曝光、自动白平衡、自动对焦这些设备级配置可能没有按期望写进去
- 但 `image_raw -> camera_info -> image_rect` 仍然可以正常工作

## 6. 当前实测结论

本次在当前工作空间内已经完成以下验证：

- `colcon build --packages-select vision_bringup` 通过
- `ros2 pkg executables` 能看到 `vision_bringup vision_bringup`
- `ros2 run vision_bringup vision_bringup --help` 正常
- 当前版本不再自动拉起任何预览组件，主链验证以 ROS2 话题为准

如果你后面还是“运行不了”，优先不要再从预览逻辑找原因，先按上面的 5.1 到 5.4 逐层排查。
