"""ROS2 去畸变预览节点。

该节点只保留一条最短运行链路：
usb_cam 图像话题 -> 去畸变 -> OpenCV 预览窗口。

设计目标是贴近用户现有的 `topic_webcam_sub.py` 使用方式，
不再自己采集和发布图像，而是直接订阅 USB 相机节点发布的话题。
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def load_calibration(calibration_file: Path) -> tuple[str, tuple[int, int], np.ndarray, np.ndarray]:
    """读取 calibration 目录导出的 JSON 标定结果。"""
    data = json.loads(calibration_file.read_text(encoding="utf-8"))
    model = str(data["model"]).strip().lower()
    image_size = (int(data["image_width"]), int(data["image_height"]))
    camera_matrix = np.asarray(data["camera_matrix"], dtype=np.float64)
    distortion_coeffs = np.asarray(data["distortion_coeffs"], dtype=np.float64).reshape(-1, 1)
    return model, image_size, camera_matrix, distortion_coeffs


def scale_camera_matrix(
    camera_matrix: np.ndarray,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> np.ndarray:
    """按分辨率比例缩放内参矩阵，保证运行分辨率变化时仍可正确去畸变。"""
    src_w, src_h = source_size
    dst_w, dst_h = target_size
    sx = float(dst_w) / float(src_w)
    sy = float(dst_h) / float(src_h)

    scaled = camera_matrix.copy().astype(np.float64)
    scaled[0, 0] *= sx
    scaled[0, 2] *= sx
    scaled[1, 1] *= sy
    scaled[1, 2] *= sy
    return scaled


def build_undistort_maps(
    model: str,
    calibration_size: tuple[int, int],
    camera_matrix: np.ndarray,
    distortion_coeffs: np.ndarray,
    current_size: tuple[int, int],
    alpha: float,
) -> tuple[np.ndarray, np.ndarray]:
    """根据当前输入图像尺寸生成去畸变映射。"""
    scaled_camera_matrix = scale_camera_matrix(camera_matrix, calibration_size, current_size)
    width, height = current_size

    if model == "fisheye":
        new_camera_matrix = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            scaled_camera_matrix,
            distortion_coeffs,
            (width, height),
            np.eye(3),
            balance=alpha,
        )
        return cv2.fisheye.initUndistortRectifyMap(
            scaled_camera_matrix,
            distortion_coeffs,
            np.eye(3),
            new_camera_matrix,
            (width, height),
            cv2.CV_16SC2,
        )

    new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
        scaled_camera_matrix,
        distortion_coeffs,
        (width, height),
        alpha,
        (width, height),
    )
    return cv2.initUndistortRectifyMap(
        scaled_camera_matrix,
        distortion_coeffs,
        None,
        new_camera_matrix,
        (width, height),
        cv2.CV_16SC2,
    )


class UndistortPreviewNode(Node):
    """订阅 USB 相机图像话题，并弹出正畸后的预览窗口。"""

    def __init__(self) -> None:
        super().__init__("undistort_preview")

        self.declare_parameter("image_topic", "/image_raw")
        self.declare_parameter("calibration_file", "")
        self.declare_parameter("alpha", 0.0)
        self.declare_parameter("window_name", "rectified_preview")

        self.image_topic = str(self.get_parameter("image_topic").value).strip() or "/image_raw"
        calibration_file = str(self.get_parameter("calibration_file").value).strip()
        self.alpha = float(self.get_parameter("alpha").value)
        self.window_name = str(self.get_parameter("window_name").value).strip() or "rectified_preview"

        if not calibration_file:
            raise RuntimeError("参数 calibration_file 不能为空，请指定 calibration/output 下的 JSON 文件。")

        calibration_path = Path(calibration_file).expanduser().resolve()
        if not calibration_path.is_file():
            raise RuntimeError(f"未找到标定文件: {calibration_path}")

        self.model, self.calibration_size, self.camera_matrix, self.distortion_coeffs = load_calibration(
            calibration_path
        )
        self.bridge = CvBridge()
        self.current_size: tuple[int, int] | None = None
        self.map1: np.ndarray | None = None
        self.map2: np.ndarray | None = None
        self.window_has_been_visible = False

        # 保持和原始苹果检测脚本相同的窗口工作方式：回调里直接 imshow。
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)

        self.sub = self.create_subscription(
            Image,
            self.image_topic,
            self.listener_callback,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            f"订阅图像话题 {self.image_topic}，使用 {calibration_path.name} 进行去畸变预览。"
        )

    def _ensure_undistort_maps(self, frame_size: tuple[int, int]) -> None:
        """仅在输入分辨率变化时重建映射，避免每帧重复计算。"""
        if self.current_size == frame_size and self.map1 is not None and self.map2 is not None:
            return

        self.map1, self.map2 = build_undistort_maps(
            self.model,
            self.calibration_size,
            self.camera_matrix,
            self.distortion_coeffs,
            frame_size,
            self.alpha,
        )
        self.current_size = frame_size
        self.get_logger().info(f"去畸变映射已更新，当前输入分辨率: {frame_size[0]}x{frame_size[1]}")

    def listener_callback(self, msg: Image) -> None:
        """收到 ROS 图像后完成去畸变，并直接弹出预览画面。"""
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        frame_size = (frame.shape[1], frame.shape[0])
        self._ensure_undistort_maps(frame_size)

        rectified = cv2.remap(frame, self.map1, self.map2, interpolation=cv2.INTER_LINEAR)
        cv2.imshow(self.window_name, rectified)
        key = cv2.waitKey(1) & 0xFF

        # 保持最简单的人机交互：按 q / ESC 或直接关窗口都退出节点。
        if key in (ord("q"), 27):
            self.get_logger().info("检测到退出按键，停止去畸变预览。")
            rclpy.shutdown()
            return

        # 某些 OpenCV GUI 后端在窗口首次刷新时会短暂返回不可见状态。
        # 因此只有窗口曾经真正可见后，再检测到不可见，才认为用户手动关闭了窗口。
        try:
            visible = cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE)
        except cv2.error:
            visible = -1

        if visible >= 1:
            self.window_has_been_visible = True
        elif self.window_has_been_visible:
            self.get_logger().info("预览窗口已关闭，停止去畸变预览。")
            rclpy.shutdown()

    def close(self) -> None:
        """释放 OpenCV 预览窗口。"""
        cv2.destroyAllWindows()


def main(args=None) -> None:
    """ROS2 节点入口。"""
    rclpy.init(args=args)
    node = None

    try:
        node = UndistortPreviewNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
