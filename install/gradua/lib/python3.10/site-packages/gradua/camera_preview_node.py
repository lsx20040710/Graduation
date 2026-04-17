"""ROS2 相机预览节点。

该节点故意保持最短数据链路：
USB 相机 -> OpenCV 取流 -> ROS2 图像发布 -> OpenCV 窗口预览。

当前版本在保持低延迟预览链路的同时，
把原始图像发布为 ROS2 `sensor_msgs/Image` 话题，
为后续检测、视觉伺服和控制节点接入提供统一输入。
"""

from __future__ import annotations

import platform
import time

import cv2
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.logging import get_logger
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


# 后端映射表：键是参数名，值是 OpenCV 的后端常量。
# 某些平台可能没有对应常量，因此使用 getattr 做兼容处理。
BACKEND_MAP = {
    "auto": None,
    "v4l2": getattr(cv2, "CAP_V4L2", None),
    "msmf": getattr(cv2, "CAP_MSMF", None),
    "dshow": getattr(cv2, "CAP_DSHOW", None),
    "avfoundation": getattr(cv2, "CAP_AVFOUNDATION", None),
}

# 按操作系统给出自动模式下的默认候选顺序。
# 设计目标不是“所有机器都强制同一后端”，而是优先选择当前平台最常见、最稳的路径。
PLATFORM_BACKEND_CANDIDATES = {
    "linux": ["v4l2", "auto"],
    "windows": ["msmf", "dshow", "auto"],
    "darwin": ["avfoundation", "auto"],
}

# 图像发布频率只允许这三个离散选项，避免再次把虚拟机和 DDS 压满。
ALLOWED_PUBLISH_RATES_HZ = (10, 15, 30)


class CameraPreviewNode(Node):
    """打开 USB 相机，并以尽量低开销的方式进行预览。"""

    def __init__(self) -> None:
        super().__init__("camera_preview")

        # 参数保持精简，并尽量贴近当前已经验证可用的裸 OpenCV 脚本。
        self.declare_parameter("camera_index", 0)
        self.declare_parameter("backend", "auto")
        self.declare_parameter("resolution", "")
        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps", 30.0)
        self.declare_parameter("fourcc", "MJPG")
        self.declare_parameter("buffer_size", 1)
        self.declare_parameter("enable_image_publish", True)
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("publish_rate_hz", 15)
        self.declare_parameter("enable_preview", True)
        self.declare_parameter("show_fps", True)
        self.declare_parameter("window_name", "CameraPreview")

        # 记录当前运行平台，供 backend 自动选择逻辑使用。
        self.platform_name = platform.system().strip().lower()
        self.camera_index = int(self.get_parameter("camera_index").value)
        self.backend = str(self.get_parameter("backend").value).strip().lower()
        self.resolution_text = str(self.get_parameter("resolution").value).strip().lower()
        fallback_width = int(self.get_parameter("width").value)
        fallback_height = int(self.get_parameter("height").value)
        self.width, self.height = self._resolve_resolution(
            self.resolution_text,
            fallback_width,
            fallback_height,
        )
        self.requested_fps = float(self.get_parameter("fps").value)
        self.fourcc = str(self.get_parameter("fourcc").value).strip().upper() or "MJPG"
        self.buffer_size = int(self.get_parameter("buffer_size").value)
        self.enable_image_publish = bool(self.get_parameter("enable_image_publish").value)
        self.image_topic = str(self.get_parameter("image_topic").value).strip() or "/camera/image_raw"
        self.frame_id = str(self.get_parameter("frame_id").value).strip() or "camera"
        self.publish_rate_hz = self._validate_publish_rate(
            self.get_parameter("publish_rate_hz").value
        )
        self.enable_preview = bool(self.get_parameter("enable_preview").value)
        self.show_fps = bool(self.get_parameter("show_fps").value)
        self.window_name = str(self.get_parameter("window_name").value)
        self.selected_backend = "unknown"
        self.last_publish_time = 0.0

        # 参数回调用于支持运行中动态切换图像发布频率。
        self.add_on_set_parameters_callback(self._on_parameters_changed)

        # 图像发布器使用传感器数据 QoS，尽量减少排队和延迟。
        self.image_publisher = None
        if self.enable_image_publish:
            self.image_publisher = self.create_publisher(
                Image,
                self.image_topic,
                qos_profile_sensor_data,
            )

        self.capture = self._open_camera()
        self.frame_count = 0
        self.start_time = time.time()

    def _validate_publish_rate(self, publish_rate_value) -> int:
        """校验图像发布频率，只接受 10 / 15 / 30 Hz。"""
        try:
            publish_rate_hz = int(publish_rate_value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"图像发布频率参数无效：{publish_rate_value}，只允许 10、15、30 Hz。"
            ) from exc

        if publish_rate_hz not in ALLOWED_PUBLISH_RATES_HZ:
            allowed_values_text = ", ".join(str(rate) for rate in ALLOWED_PUBLISH_RATES_HZ)
            raise RuntimeError(
                f"图像发布频率 {publish_rate_hz} Hz 不被允许，只允许：{allowed_values_text} Hz。"
            )
        return publish_rate_hz

    def _on_parameters_changed(self, parameters) -> SetParametersResult:
        """处理运行中参数更新，当前只开放图像发布频率动态修改。"""
        # 先做整批校验，避免一部分参数改成功、一部分失败。
        next_publish_rate_hz = self.publish_rate_hz

        for parameter in parameters:
            if parameter.name != "publish_rate_hz":
                continue

            try:
                next_publish_rate_hz = self._validate_publish_rate(parameter.value)
            except RuntimeError as exc:
                return SetParametersResult(successful=False, reason=str(exc))

        # 校验全部通过后再正式生效。
        publish_rate_changed = next_publish_rate_hz != self.publish_rate_hz
        self.publish_rate_hz = next_publish_rate_hz
        if publish_rate_changed:
            self.last_publish_time = 0.0
            self.get_logger().info(
                f"图像发布频率已更新为 {self.publish_rate_hz} Hz。"
            )

        return SetParametersResult(successful=True)

    def _resolve_resolution(
        self,
        resolution_text: str,
        fallback_width: int,
        fallback_height: int,
    ) -> tuple[int, int]:
        """解析分辨率参数。

        优先使用 `resolution` 字符串参数，例如 `640x480`。
        如果该参数为空，则回退到 `width` 与 `height`。
        """
        # 如果没有提供字符串形式的分辨率，就继续沿用 width / height。
        if not resolution_text:
            return fallback_width, fallback_height

        # 兼容常见分隔符，避免因为输入格式细节导致启动失败。
        normalized_text = (
            resolution_text.replace("*", "x")
            .replace("X", "x")
            .replace(" ", "")
        )
        parts = normalized_text.split("x")
        if len(parts) != 2:
            raise RuntimeError(
                f"分辨率参数 '{resolution_text}' 格式无效，应为类似 640x480 的形式。"
            )

        try:
            width = int(parts[0])
            height = int(parts[1])
        except ValueError as exc:
            raise RuntimeError(
                f"分辨率参数 '{resolution_text}' 解析失败，宽高必须是整数。"
            ) from exc

        if width <= 0 or height <= 0:
            raise RuntimeError("分辨率宽高必须大于 0。")

        return width, height

    def _get_backend_candidates(self) -> list[str]:
        """根据参数和平台生成本次打开相机时的后端候选列表。"""
        # 若用户显式指定了 backend，则完全按用户指定执行，不做自动切换。
        if self.backend != "auto":
            if self.backend not in BACKEND_MAP:
                supported_backends = ", ".join(sorted(BACKEND_MAP.keys()))
                raise RuntimeError(
                    f"不支持的 backend 参数 '{self.backend}'，可选值为：{supported_backends}。"
                )
            return [self.backend]

        # auto 模式下按平台给出优先级；未知平台则直接回退给 OpenCV 自己选择。
        candidates = PLATFORM_BACKEND_CANDIDATES.get(self.platform_name, ["auto"])

        # 过滤掉当前 OpenCV 构建中根本不存在的后端常量，避免无效尝试。
        valid_candidates = []
        for candidate in candidates:
            backend_id = BACKEND_MAP.get(candidate)
            if candidate == "auto" or backend_id is not None:
                valid_candidates.append(candidate)

        if not valid_candidates:
            return ["auto"]
        return valid_candidates

    def _create_capture(self, backend_name: str) -> cv2.VideoCapture:
        """按指定后端创建 VideoCapture 对象。"""
        backend_id = BACKEND_MAP.get(backend_name)
        if backend_name == "auto" or backend_id is None:
            return cv2.VideoCapture(self.camera_index)
        return cv2.VideoCapture(self.camera_index, backend_id)

    def _open_camera(self) -> cv2.VideoCapture:
        """打开相机，并尽量应用与原脚本一致的低延迟取流设置。"""
        tried_backends = []
        capture = None

        # 逐个尝试候选后端，方便在不同平台上获得更稳定的默认行为。
        for backend_name in self._get_backend_candidates():
            tried_backends.append(backend_name)
            candidate_capture = self._create_capture(backend_name)
            if candidate_capture.isOpened():
                capture = candidate_capture
                self.selected_backend = backend_name
                break
            candidate_capture.release()

        if capture is None:
            raise RuntimeError(
                f"无法打开相机：camera_index={self.camera_index}，"
                f"requested_backend='{self.backend}'，tried_backends={tried_backends}。"
            )

        # MJPG 往往能降低 USB 相机链路上的解码和传输压力，有助于保持流畅预览。
        if len(self.fourcc) == 4:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))

        # 分辨率直接作用在底层采集设备上。
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # 帧率是“向驱动申请”的目标值，最终是否生效由相机和驱动共同决定。
        if self.requested_fps > 0.0:
            capture.set(cv2.CAP_PROP_FPS, self.requested_fps)

        # 缓冲区尽量设小，减少显示链路短时卡顿带来的滞后感。
        if self.buffer_size > 0:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)

        actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = capture.get(cv2.CAP_PROP_FPS)
        self.get_logger().info(
            f"Camera opened: index={self.camera_index} "
            f"platform={self.platform_name} "
            f"requested_backend={self.backend} selected_backend={self.selected_backend} "
            f"size={actual_width}x{actual_height} "
            f"requested_fps={self.requested_fps:.2f} "
            f"reported_fps={actual_fps:.2f} "
            f"publish={self.enable_image_publish} publish_rate={self.publish_rate_hz}Hz "
            f"topic={self.image_topic} frame_id={self.frame_id} "
            f"preview={self.enable_preview} fourcc={self.fourcc}"
        )
        return capture

    def _build_image_message(self, frame) -> Image:
        """将 OpenCV 帧封装为 ROS2 Image 消息。"""
        # 按 OpenCV 返回的数组维度推断编码格式。
        if frame.ndim == 2:
            encoding = "mono8"
            height, width = frame.shape
            step = int(frame.strides[0])
        elif frame.ndim == 3 and frame.shape[2] == 3:
            encoding = "bgr8"
            height, width, channels = frame.shape
            step = int(frame.strides[0])
        elif frame.ndim == 3 and frame.shape[2] == 4:
            encoding = "bgra8"
            height, width, channels = frame.shape
            step = int(frame.strides[0])
        else:
            raise RuntimeError(f"暂不支持的图像数据形状：{frame.shape}")

        # 逐帧写入时间戳和 frame_id，便于后续节点做时间同步和坐标关联。
        message = Image()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self.frame_id
        message.height = height
        message.width = width
        message.encoding = encoding
        message.is_bigendian = False
        message.step = step
        message.data = frame.tobytes()
        return message

    def _publish_image(self, frame) -> None:
        """将当前帧发布到 ROS2 图像话题。"""
        if self.image_publisher is None:
            return

        # 软件限速只作用于 ROS2 图像发布，不影响相机读帧和本地预览。
        now = time.monotonic()
        publish_interval = 1.0 / float(self.publish_rate_hz)
        if self.last_publish_time > 0.0 and (now - self.last_publish_time) < publish_interval:
            return

        self.image_publisher.publish(self._build_image_message(frame))
        self.last_publish_time = now

    def _draw_fps(self, frame) -> None:
        """每 10 帧在画面上更新一次简易 FPS 文本。"""
        self.frame_count += 1
        if self.frame_count % 10 != 0:
            return

        now = time.time()
        elapsed = max(now - self.start_time, 1e-6)
        fps = self.frame_count / elapsed
        cv2.putText(
            frame,
            f"FPS:{fps:.2f}",
            (0, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
        )
        self.frame_count = 0
        self.start_time = now

    def run(self) -> None:
        """持续读帧；若启用预览，则显示窗口直到 ROS 关闭或按下 q。"""
        # 只有在确实需要预览时才创建窗口，便于后续无界面运行。
        if self.enable_preview:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        else:
            self.get_logger().info("预览窗口已关闭，节点将只进行相机取流。")

        while rclpy.ok():
            ret, frame = self.capture.read()
            if not ret:
                # 如果 ROS 上下文已经结束，就直接退出循环，不再追加无意义告警。
                if not rclpy.ok():
                    break
                self.get_logger().warning("相机读帧失败。")
                continue

            # 先发布原始图像，再做本地预览，保证外部节点拿到的是未叠加 UI 的原画面。
            self._publish_image(frame)

            # 只有在需要显示窗口时，才有必要把 FPS 叠加到图像上。
            if self.enable_preview and self.show_fps:
                self._draw_fps(frame)

            # 预览开启时显示原画面，并支持按 q 退出。
            if self.enable_preview:
                cv2.imshow(self.window_name, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.get_logger().info("检测到键盘输入，停止预览。")
                    break

            # 这里不改成定时器取帧，避免人为拉长相机到显示的路径。
            rclpy.spin_once(self, timeout_sec=0.0)

    def close(self) -> None:
        """释放相机资源，并关闭 OpenCV 窗口。"""
        if hasattr(self, "capture") and self.capture is not None:
            self.capture.release()
        cv2.destroyAllWindows()


def main(args=None) -> None:
    """ROS2 节点入口。"""
    rclpy.init(args=args)
    node = None
    try:
        node = CameraPreviewNode()
        node.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        get_logger("camera_preview").error(str(exc))
        raise SystemExit(1) from exc
    finally:
        # 无论正常退出还是异常退出，都确保底层资源被释放。
        if node is not None:
            node.close()
            node.destroy_node()
        # 某些退出路径下 rclpy 上下文可能已被外部关闭，此时不再重复 shutdown。
        if rclpy.ok():
            rclpy.shutdown()
