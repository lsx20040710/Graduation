"""
USB 相机标定辅助脚本。

文件作用：
- 采集棋盘格标定图像
- 根据采集结果估计相机内参与畸变系数
- 导出 JSON 和 ROS `camera_info.yaml`
- 预览实时去畸变效果

典型使用流程：
1. 打印棋盘格并确认单格物理边长，单位通常为毫米。
2. 以最终工作分辨率采集 25 到 40 张清晰、姿态分散的标定图像。
3. 执行标定并查看重投影误差及角点可视化结果。
4. 将导出的参数接入后续 ROS2 图像链路或视觉伺服模块。

命令示例：
    python calibrate_usb_camera.py capture --cols 9 --rows 6 --width 1920 --height 1080
    python calibrate_usb_camera.py calibrate --cols 9 --rows 6 --square-size-mm 15
    python calibrate_usb_camera.py preview --calibration-file output/camera_calibration.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CAPTURE_DIR = SCRIPT_DIR / "captures"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"


@dataclass
class CalibrationResult:
    """保存一次标定的完整结果，便于写盘、加载和预览阶段复用。"""

    # 基本信息：记录模型类型、图像尺寸和有效数据量
    model: str
    image_width: int
    image_height: int
    rms: float
    mean_error_px: float
    valid_images: int
    total_images: int
    pattern_cols: int
    pattern_rows: int
    square_size_mm: float
    camera_matrix: np.ndarray
    distortion_coeffs: np.ndarray
    rectification_matrix: np.ndarray
    projection_matrix: np.ndarray
    roi: Tuple[int, int, int, int]


def ensure_dir(path: Path) -> Path:
    """确保目标目录存在，并返回规范化后的目录对象。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_cameras(max_to_test: int = 5) -> List[int]:
    """测试并列出系统中可用的相机索引。"""
    available = []
    for i in range(max_to_test):
        if os.name == "nt":
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available


def open_camera(camera_index: int, width: int, height: int, fourcc: str) -> cv2.VideoCapture:
    """打开相机流，在 Windows 上优先使用 CAP_DSHOW 后端。"""
    if os.name == "nt":
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)

    # 尽量缩小驱动侧缓存，减少预览画面落后于真实运动的延迟感
    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    if width > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def detect_checkerboard(gray: np.ndarray, pattern_size: Tuple[int, int], scale: float = 1.0) -> Tuple[bool, np.ndarray | None]:
    """检测棋盘格角点，并将其精细化到亚像素精度。
    
    参数:
        gray: 输入的灰度图像。
        pattern_size: 标定板内角点的行列数 (cols, rows)。
        scale: 下采样比例，用于加速检测过程。
    """
    # 如果设置了缩放比例，先缩小图像以加速检测
    if scale != 1.0:
        h, w = gray.shape[:2]
        small_gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
        working_gray = small_gray
    else:
        working_gray = gray

    # 尝试使用 OpenCV 的 findChessboardCornersSB (更鲁棒但更慢)
    if hasattr(cv2, "findChessboardCornersSB"):
        # SB 模式自带精细化，在预览模式下不使用 EXHAUSTIVE 标志以加速
        sb_flags = cv2.CALIB_CB_ACCURACY
        found, corners = cv2.findChessboardCornersSB(working_gray, pattern_size, flags=sb_flags)
        if found:
            if scale != 1.0:
                corners /= scale
            return True, corners.astype(np.float32)

    # 回退到标准的 findChessboardCorners
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(working_gray, pattern_size, flags)
    
    if not found:
        return False, None

    # 如果使用了缩放，将坐标还原
    if scale != 1.0:
        corners /= scale

    # 在原始大图上进行亚像素精细化 (仅当找到角点时执行一次，开销可接受)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
    refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return True, refined


def build_object_points(cols: int, rows: int, square_size_mm: float) -> np.ndarray:
    """生成棋盘格在标定板坐标系下的三维角点坐标。"""
    # 标定板位于 Z=0 平面，因此只需要在 XY 平面按网格展开角点
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size_mm
    return objp


def collect_image_paths(image_dir: Path) -> List[Path]:
    """收集目录中的常见图像文件，供离线标定阶段批量处理。"""
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
    paths: List[Path] = []
    for ext in exts:
        paths.extend(sorted(image_dir.glob(ext)))
    return sorted(paths)


def draw_status(frame: np.ndarray, lines: Sequence[str], color: Tuple[int, int, int]) -> np.ndarray:
    """在图像左上角叠加多行状态文本，便于预览阶段观察运行状态。"""
    overlay = frame.copy()
    y = 30
    for text in lines:
        cv2.putText(overlay, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2, cv2.LINE_AA)
        y += 30
    return overlay


def compose_preview_frame(raw_frame: np.ndarray, rectified_frame: np.ndarray, layout: str) -> np.ndarray:
    """根据预览布局组织显示内容，避免始终固定为左右拼接。"""
    # 仅查看原图或去畸变图时，不再拼接两幅图，便于放大检查局部细节
    if layout == "raw":
        return raw_frame
    if layout == "rectified":
        return rectified_frame
    # 上下布局适合宽屏空间不足、但希望保留较大宽度的场景
    if layout == "vertical":
        return np.vstack([raw_frame, rectified_frame])
    # 默认使用左右对比，便于直接观察畸变校正前后的差异
    return np.hstack([raw_frame, rectified_frame])


def resize_frame_to_fit(frame: np.ndarray, max_width: int, max_height: int) -> Tuple[np.ndarray, float]:
    """将显示画面按比例缩小到目标窗口范围内，避免对比图超出单屏。"""
    height, width = frame.shape[:2]
    scale_candidates = []

    # 只对有效的宽高约束计算缩放比例，允许用户将某一项设为 0 表示不限制
    if max_width > 0:
        scale_candidates.append(max_width / float(width))
    if max_height > 0:
        scale_candidates.append(max_height / float(height))

    if not scale_candidates:
        return frame, 1.0

    scale = min(scale_candidates)
    if scale >= 1.0:
        return frame, 1.0

    resized_width = max(1, int(width * scale))
    resized_height = max(1, int(height * scale))
    resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    return resized, scale


def build_preview_window_flags() -> int:
    """构建可缩放的预览窗口标志，保证单屏和多屏环境行为更稳定。"""
    flags = cv2.WINDOW_NORMAL
    # 保持宽高比可以避免窗口缩放后画面被拉伸变形
    if hasattr(cv2, "WINDOW_KEEPRATIO"):
        flags |= cv2.WINDOW_KEEPRATIO
    return flags


def scale_camera_matrix(camera_matrix: np.ndarray, source_size: Tuple[int, int], target_size: Tuple[int, int]) -> np.ndarray:
    """按分辨率比例缩放内参矩阵，保证预览分辨率变化时映射仍然正确。"""
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


def compute_standard_error(
    object_points: Sequence[np.ndarray],
    image_points: Sequence[np.ndarray],
    rvecs: Sequence[np.ndarray],
    tvecs: Sequence[np.ndarray],
    camera_matrix: np.ndarray,
    distortion_coeffs: np.ndarray,
) -> float:
    """计算标准针孔模型的平均重投影误差，作为标定质量指标。"""
    total_error = 0.0
    total_points = 0
    for objp, corners, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        # 将三维角点重新投影回图像平面，并与实际检测角点比较误差
        projected, _ = cv2.projectPoints(objp, rvec, tvec, camera_matrix, distortion_coeffs)
        total_error += cv2.norm(corners, projected, cv2.NORM_L2)
        total_points += len(projected)
    return total_error / max(total_points, 1)


def compute_fisheye_error(
    object_points: Sequence[np.ndarray],
    image_points: Sequence[np.ndarray],
    rvecs: Sequence[np.ndarray],
    tvecs: Sequence[np.ndarray],
    camera_matrix: np.ndarray,
    distortion_coeffs: np.ndarray,
) -> float:
    """计算鱼眼模型的平均重投影误差，便于与针孔模型结果对比。"""
    total_error = 0.0
    total_points = 0
    for objp, corners, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        # 鱼眼模型使用 fisheye 投影接口，不能直接复用标准针孔模型公式
        projected, _ = cv2.fisheye.projectPoints(objp, rvec, tvec, camera_matrix, distortion_coeffs)
        total_error += cv2.norm(corners, projected, cv2.NORM_L2)
        total_points += len(projected)
    return total_error / max(total_points, 1)


def save_json(result: CalibrationResult, path: Path) -> None:
    """将标定结果写入 JSON，便于后续程序直接读取和复用。"""
    # 统一转成基础 Python 类型，避免 numpy 数组直接序列化失败
    payload = {
        "model": result.model,
        "image_width": result.image_width,
        "image_height": result.image_height,
        "rms": result.rms,
        "mean_error_px": result.mean_error_px,
        "valid_images": result.valid_images,
        "total_images": result.total_images,
        "pattern_cols": result.pattern_cols,
        "pattern_rows": result.pattern_rows,
        "square_size_mm": result.square_size_mm,
        "camera_matrix": result.camera_matrix.tolist(),
        "distortion_coeffs": result.distortion_coeffs.reshape(-1).tolist(),
        "rectification_matrix": result.rectification_matrix.tolist(),
        "projection_matrix": result.projection_matrix.tolist(),
        "roi": list(result.roi),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_ros_camera_info(result: CalibrationResult, camera_name: str, path: Path) -> None:
    """生成 ROS 可直接使用的 camera_info YAML 文件。"""
    # 根据标定模型选择 ROS 侧对应的畸变模型名称
    distortion_model = "equidistant" if result.model == "fisheye" else "plumb_bob"
    camera_matrix = [float(x) for x in result.camera_matrix.reshape(-1)]
    distortion = [float(x) for x in result.distortion_coeffs.reshape(-1)]
    rectification = [float(x) for x in result.rectification_matrix.reshape(-1)]
    projection = [float(x) for x in result.projection_matrix.reshape(-1)]

    lines = [
        f"image_width: {result.image_width}",
        f"image_height: {result.image_height}",
        f"camera_name: {camera_name}",
        "camera_matrix:",
        "  rows: 3",
        "  cols: 3",
        f"  data: [{', '.join(f'{x:.10f}' for x in camera_matrix)}]",
        f"distortion_model: {distortion_model}",
        "distortion_coefficients:",
        "  rows: 1",
        f"  cols: {len(distortion)}",
        f"  data: [{', '.join(f'{x:.10f}' for x in distortion)}]",
        "rectification_matrix:",
        "  rows: 3",
        "  cols: 3",
        f"  data: [{', '.join(f'{x:.10f}' for x in rectification)}]",
        "projection_matrix:",
        "  rows: 3",
        "  cols: 4",
        f"  data: [{', '.join(f'{x:.10f}' for x in projection)}]",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_calibration(path: Path) -> CalibrationResult:
    """从 JSON 文件加载标定结果，并恢复为结构化对象。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return CalibrationResult(
        model=data["model"],
        image_width=int(data["image_width"]),
        image_height=int(data["image_height"]),
        rms=float(data["rms"]),
        mean_error_px=float(data["mean_error_px"]),
        valid_images=int(data["valid_images"]),
        total_images=int(data["total_images"]),
        pattern_cols=int(data["pattern_cols"]),
        pattern_rows=int(data["pattern_rows"]),
        square_size_mm=float(data["square_size_mm"]),
        camera_matrix=np.asarray(data["camera_matrix"], dtype=np.float64),
        distortion_coeffs=np.asarray(data["distortion_coeffs"], dtype=np.float64).reshape(-1, 1),
        rectification_matrix=np.asarray(data["rectification_matrix"], dtype=np.float64),
        projection_matrix=np.asarray(data["projection_matrix"], dtype=np.float64),
        roi=tuple(int(x) for x in data.get("roi", [0, 0, 0, 0])),
    )


def build_undistort_maps(
    calibration: CalibrationResult,
    current_size: Tuple[int, int],
    alpha: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """根据标定结果和当前分辨率生成去畸变映射表。"""
    source_size = (calibration.image_width, calibration.image_height)
    camera_matrix = scale_camera_matrix(calibration.camera_matrix, source_size, current_size)
    distortion = calibration.distortion_coeffs
    width, height = current_size

    if calibration.model == "fisheye":
        # 鱼眼模型使用 fisheye 专用接口，balance 对应去畸变后的视场保留比例
        new_camera_matrix = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            camera_matrix,
            distortion,
            (width, height),
            np.eye(3),
            balance=alpha,
        )
        map1, map2 = cv2.fisheye.initUndistortRectifyMap(
            camera_matrix,
            distortion,
            np.eye(3),
            new_camera_matrix,
            (width, height),
            cv2.CV_16SC2,
        )
        return map1, map2

    # 标准针孔模型走 OpenCV 通用去畸变接口
    new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
        camera_matrix,
        distortion,
        (width, height),
        alpha,
        (width, height),
    )
    map1, map2 = cv2.initUndistortRectifyMap(
        camera_matrix,
        distortion,
        None,
        new_camera_matrix,
        (width, height),
        cv2.CV_16SC2,
    )
    return map1, map2


def run_capture(args: argparse.Namespace) -> int:
    """启动相机采集界面，按空格保存棋盘格图像。"""
    output_dir = ensure_dir(Path(args.output_dir).resolve())
    cap = open_camera(args.camera_index, args.width, args.height, args.fourcc)
    
    if not cap.isOpened():
        print(f"无法打开相机 (索引: {args.camera_index})。", file=sys.stderr)
        available = list_cameras()
        if available:
            print(f"检测到可用相机索引: {available}，请尝试使用 --camera-index {available[0]}", file=sys.stderr)
        else:
            print("未检测到任何可用相机，请检查连接或驱动。", file=sys.stderr)
        return 1

    pattern_size = (args.cols, args.rows)
    saved = 0
    last_saved_time = 0.0

    # 优先读取新的缩放参数；如果旧脚本仍传 fast_preview，则继续兼容旧行为
    preview_scale = getattr(args, "preview_scale", None)
    if preview_scale is None:
        fast_preview = getattr(args, "fast_preview", False)
        preview_scale = 0.5 if fast_preview else 1.0

    # 将缩放比例限制在有效区间，避免 resize 因非法尺寸报错
    detection_scale = float(max(0.1, min(1.0, preview_scale)))
    # 通过降低检测频率减轻 CPU 压力，让实时预览更顺畅
    detect_interval = max(1, int(getattr(args, "detect_interval", 1)))

    print("采集模式已启动。")
    print("操作指令:")
    print("  [空格] - 当检测到角点时保存当前帧")
    print("  [Q]    - 退出采集程序")
    print(f"  当前检测缩放比例: {detection_scale:.2f}")
    print(f"  当前检测间隔: 每 {detect_interval} 帧检测一次")

    frame_index = 0
    last_found = False
    last_corners = None

    while True:
        ok, frame = cap.read()
        if not ok:
            print("读取相机帧失败。", file=sys.stderr)
            break

        # 每帧都先转为灰度图，供周期性检测和手动保存时复用，避免重复颜色空间转换
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        should_detect_now = (frame_index % detect_interval == 0) or (last_corners is None)
        if should_detect_now:
            last_found, last_corners = detect_checkerboard(gray, pattern_size, scale=detection_scale)

        preview = frame.copy()
        # 只在当前帧刚完成检测时绘制角点，避免把上一帧角点叠到当前帧造成错位
        if should_detect_now and last_found and last_corners is not None:
            cv2.drawChessboardCorners(preview, pattern_size, last_corners, last_found)

        # 绘制状态信息（左上角）
        status = [
            f"board: {'DETECTED' if last_found else 'not found'}",
            f"saved images: {saved}",
            f"resolution: {frame.shape[1]}x{frame.shape[0]}",
            f"detect every: {detect_interval} frame(s)",
            "SPACE=save  Q=quit",
        ]
        color = (0, 255, 0) if last_found else (0, 0, 255)
        preview = draw_status(preview, status, color)

        # 显示预览窗口
        cv2.imshow("checkerboard_capture", preview)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):  # 按 Q 或 ESC 退出
            break
        if key == ord(" "):  # 按空格保存图像
            now = time.time()
            # 限制保存频率，防止连按时采到大量重复图像
            if now - last_saved_time >= args.min_interval_sec:
                # 如果当前帧没有执行检测，则保存前补做一次检测，确保判定结果对应当前图像
                if should_detect_now:
                    save_found = last_found
                else:
                    save_found, last_corners = detect_checkerboard(gray, pattern_size, scale=detection_scale)
                    last_found = save_found

                if not save_found:
                    print("跳过：当前帧未检测到完整的棋盘格角点。")
                else:
                    file_path = output_dir / f"calib_{saved:03d}.jpg"
                    # 保存原始帧（非预览帧，无叠加绘制），保证后续标定使用的是完整原图
                    cv2.imwrite(str(file_path), frame)
                    print(f"已保存: {file_path}")
                    saved += 1
                    last_saved_time = now

        frame_index += 1

    cap.release()
    cv2.destroyAllWindows()
    print(f"采集结束。共保存 {saved} 张图像至: {output_dir}")
    return 0


def run_calibrate(args: argparse.Namespace) -> int:
    """执行离线标定流程，输出内参、畸变系数和调试图像。"""
    # 统一规范输入输出目录，避免后续写文件时路径不一致
    image_dir = Path(args.image_dir).resolve()
    output_dir = ensure_dir(Path(args.output_dir).resolve())
    debug_dir = ensure_dir(output_dir / "debug_corners")

    # 先收集图像路径，若没有输入数据则直接终止
    image_paths = collect_image_paths(image_dir)
    if not image_paths:
        print(f"No calibration images found in {image_dir}", file=sys.stderr)
        return 1

    pattern_size = (args.cols, args.rows)
    obj_template = build_object_points(args.cols, args.rows, args.square_size_mm)
    object_points: List[np.ndarray] = []
    image_points: List[np.ndarray] = []
    image_size: Tuple[int, int] | None = None

    for image_path in image_paths:
        # 逐张图像检测角点，并把可视化结果写入 debug 目录，便于排查无效样本
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Skipped unreadable image: {image_path}")
            continue

        height, width = image.shape[:2]
        if image_size is None:
            image_size = (width, height)
        elif image_size != (width, height):
            print(f"Skipped size mismatch image: {image_path}")
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, corners = detect_checkerboard(gray, pattern_size)
        preview = image.copy()

        if found and corners is not None:
            cv2.drawChessboardCorners(preview, pattern_size, corners, found)
            # 鱼眼接口和标准接口对角点数组形状要求不同，这里分别整理
            if args.model == "fisheye":
                object_points.append(obj_template.reshape(-1, 1, 3).astype(np.float64))
                image_points.append(corners.reshape(-1, 1, 2).astype(np.float64))
            else:
                object_points.append(obj_template.astype(np.float32))
                image_points.append(corners.astype(np.float32))

        cv2.imwrite(str(debug_dir / f"{image_path.stem}_corners.jpg"), preview)

    if image_size is None:
        print("Could not determine image size from the calibration set.", file=sys.stderr)
        return 1

    if len(image_points) < args.min_images:
        print(
            f"Only {len(image_points)} valid calibration images were found. "
            f"At least {args.min_images} are recommended.",
            file=sys.stderr,
        )
        return 1

    width, height = image_size

    if args.model == "fisheye":
        # 鱼眼模型更适合大视场镜头，但对输入角点质量和覆盖范围更敏感
        flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)
        camera_matrix = np.zeros((3, 3), dtype=np.float64)
        distortion = np.zeros((4, 1), dtype=np.float64)
        rms, camera_matrix, distortion, rvecs, tvecs = cv2.fisheye.calibrate(
            object_points,
            image_points,
            (width, height),
            camera_matrix,
            distortion,
            None,
            None,
            flags=flags,
            criteria=criteria,
        )
        rectification = np.eye(3, dtype=np.float64)
        new_camera_matrix = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            camera_matrix,
            distortion,
            (width, height),
            rectification,
            balance=args.alpha,
        )
        projection = np.hstack([new_camera_matrix, np.zeros((3, 1), dtype=np.float64)])
        roi = (0, 0, width, height)
        mean_error = compute_fisheye_error(object_points, image_points, rvecs, tvecs, camera_matrix, distortion)
    else:
        # 标准模型使用 OpenCV 常规标定流程，适合普通视场镜头
        rms, camera_matrix, distortion, rvecs, tvecs = cv2.calibrateCamera(
            object_points,
            image_points,
            (width, height),
            None,
            None,
        )
        rectification = np.eye(3, dtype=np.float64)
        new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
            camera_matrix,
            distortion,
            (width, height),
            args.alpha,
            (width, height),
        )
        projection = np.hstack([new_camera_matrix, np.zeros((3, 1), dtype=np.float64)])
        mean_error = compute_standard_error(object_points, image_points, rvecs, tvecs, camera_matrix, distortion)

    # 将核心标定结果整理成统一结构，方便后续写出和预览复用
    result = CalibrationResult(
        model=args.model,
        image_width=width,
        image_height=height,
        rms=float(rms),
        mean_error_px=float(mean_error),
        valid_images=len(image_points),
        total_images=len(image_paths),
        pattern_cols=args.cols,
        pattern_rows=args.rows,
        square_size_mm=float(args.square_size_mm),
        camera_matrix=camera_matrix,
        distortion_coeffs=distortion,
        rectification_matrix=rectification,
        projection_matrix=projection,
        roi=tuple(int(x) for x in roi),
    )

    # 同时导出机器可读 JSON 和 ROS 友好的 YAML，满足后续不同集成方式
    json_path = output_dir / "camera_calibration.json"
    yaml_path = output_dir / "camera_info.yaml"
    save_json(result, json_path)
    save_ros_camera_info(result, args.camera_name, yaml_path)

    print("Calibration finished.")
    print(f"Model: {result.model}")
    print(f"Valid images: {result.valid_images}/{result.total_images}")
    print(f"Image size: {result.image_width}x{result.image_height}")
    print(f"RMS: {result.rms:.6f}")
    print(f"Mean reprojection error: {result.mean_error_px:.6f} px")
    print(f"JSON saved to: {json_path}")
    print(f"ROS YAML saved to: {yaml_path}")
    print(f"Corner overlays saved to: {debug_dir}")
    return 0


def run_preview(args: argparse.Namespace) -> int:
    """启动去畸变预览，支持实时相机和单张图片两种输入模式。"""
    calibration = load_calibration(Path(args.calibration_file).resolve())
    layout = getattr(args, "layout", "horizontal")
    window_width = max(0, int(getattr(args, "window_width", 1280)))
    window_height = max(0, int(getattr(args, "window_height", 720)))
    window_name = "preview_undistort"
    last_window_size = None

    # 使用可缩放窗口，解决默认窗口固定大小、对比图过宽时难以查看的问题
    cv2.namedWindow(window_name, build_preview_window_flags())

    if args.image:
        frame = cv2.imread(str(Path(args.image).resolve()))
        if frame is None:
            print("读取预览图片失败。", file=sys.stderr)
            return 1

        # 离线图片模式下只做一次映射和显示，适合快速核对标定效果
        maps = build_undistort_maps(calibration, (frame.shape[1], frame.shape[0]), args.alpha)
        rectified = cv2.remap(frame, maps[0], maps[1], interpolation=cv2.INTER_LINEAR)
        combined = compose_preview_frame(frame, rectified, layout)
        display, display_scale = resize_frame_to_fit(combined, window_width, window_height)
        display = draw_status(
            display,
            [
                f"raw size: {frame.shape[1]}x{frame.shape[0]}",
                f"layout: {layout}",
                f"display scale: {display_scale:.2f}x",
                "Q / ESC = quit",
            ],
            (0, 220, 0),
        )
        last_window_size = (display.shape[1], display.shape[0])
        cv2.resizeWindow(window_name, last_window_size[0], last_window_size[1])
        cv2.imshow(window_name, display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        return 0

    cap = open_camera(args.camera_index, args.width, args.height, args.fourcc)
    if not cap.isOpened():
        print("无法打开预览相机。", file=sys.stderr)
        cv2.destroyWindow(window_name)
        return 1

    maps = None
    current_size = None

    while True:
        ok, frame = cap.read()
        if not ok:
            print("读取相机预览帧失败。", file=sys.stderr)
            break

        size = (frame.shape[1], frame.shape[0])
        if maps is None or current_size != size:
            # 分辨率变化时需要重新生成映射表，否则去畸变结果会错位
            maps = build_undistort_maps(calibration, size, args.alpha)
            current_size = size

        rectified = cv2.remap(frame, maps[0], maps[1], interpolation=cv2.INTER_LINEAR)
        combined = compose_preview_frame(frame, rectified, layout)
        # 先把内容压缩到单屏可见范围内，避免左右拼接后的总宽度超出显示器
        display, display_scale = resize_frame_to_fit(combined, window_width, window_height)
        display = draw_status(
            display,
            [
                f"raw size: {size[0]}x{size[1]}",
                f"calibrated size: {calibration.image_width}x{calibration.image_height}",
                f"layout: {layout}",
                f"display scale: {display_scale:.2f}x",
                "Q / ESC = quit",
            ],
            (0, 220, 0),
        )
        # 仅在初次显示或输入分辨率变化时更新初始窗口大小，不覆盖用户手动缩放
        current_window_size = (display.shape[1], display.shape[0])
        if last_window_size != current_window_size:
            cv2.resizeWindow(window_name, current_window_size[0], current_window_size[1])
            last_window_size = current_window_size
        cv2.imshow(window_name, display)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构建统一命令行入口，便于通过子命令切换采集、标定和预览阶段。"""
    parser = argparse.ArgumentParser(description="USB 相机标定辅助工具。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 采集子命令：从实时相机获取棋盘格图像
    capture = subparsers.add_parser("capture", help="从相机采集棋盘格图像。")
    capture.add_argument("--camera-index", type=int, default=0, help="OpenCV 使用的相机索引。")
    capture.add_argument("--width", type=int, default=1920, help="请求的采集宽度。")
    capture.add_argument("--height", type=int, default=1080, help="请求的采集高度。")
    capture.add_argument("--fourcc", default="MJPG", help="请求的相机像素格式，例如 MJPG。")
    capture.add_argument("--cols", type=int, required=True, help="棋盘格内角点列数（宽度方向）。")
    capture.add_argument("--rows", type=int, required=True, help="棋盘格内角点行数（高度方向）。")
    capture.add_argument("--output-dir", default=str(DEFAULT_CAPTURE_DIR), help="保存采集图像的目录。")
    capture.add_argument(
        "--min-interval-sec",
        type=float,
        default=0.6,
        help="两次保存之间的最小时间间隔。",
    )

    # 标定子命令：根据已采集图像计算内参与畸变参数
    calibrate = subparsers.add_parser("calibrate", help="根据棋盘格图像执行相机标定。")
    calibrate.add_argument("--image-dir", default=str(DEFAULT_CAPTURE_DIR), help="存放标定图像的目录。")
    calibrate.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="保存标定结果的目录。")
    calibrate.add_argument("--camera-name", default="usb_camera", help="写入 ROS YAML 的相机名称。")
    calibrate.add_argument("--cols", type=int, required=True, help="棋盘格内角点列数（宽度方向）。")
    calibrate.add_argument("--rows", type=int, required=True, help="棋盘格内角点行数（高度方向）。")
    calibrate.add_argument(
        "--square-size-mm",
        type=float,
        default=15.0,
        help="棋盘格单格边长，单位毫米。",
    )
    calibrate.add_argument(
        "--model",
        choices=("fisheye", "standard"),
        default="fisheye",
        help="标定模型类型；超广角镜头通常优先尝试 fisheye。",
    )
    calibrate.add_argument(
        "--alpha",
        type=float,
        default=0.0,
        help="去畸变时保留边界的程度，0 裁边更多，1 保留视场更多。",
    )
    calibrate.add_argument(
        "--min-images",
        type=int,
        default=12,
        help="继续执行标定所需的最少有效图像数量。",
    )

    # 预览子命令：根据标定结果检查去畸变效果
    preview = subparsers.add_parser("preview", help="预览实时或离线去畸变效果。")
    preview.add_argument("--calibration-file", required=True, help="导出的标定结果 JSON 路径。")
    preview.add_argument("--camera-index", type=int, default=0, help="实时预览使用的相机索引。")
    preview.add_argument("--width", type=int, default=1920, help="请求的预览宽度。")
    preview.add_argument("--height", type=int, default=1080, help="请求的预览高度。")
    preview.add_argument("--fourcc", default="MJPG", help="请求的相机像素格式。")
    preview.add_argument("--image", default="", help="预览单张图片；提供后不再打开相机。")
    preview.add_argument(
        "--alpha",
        type=float,
        default=0.0,
        help="去畸变保留边界的程度，0 更裁边，1 保留更多视场。",
    )

    return parser


def main() -> int:
    """统一脚本主入口，根据子命令分发到对应工作阶段。"""
    parser = build_parser()
    args = parser.parse_args()

    # 根据子命令选择对应流程，保持采集、标定、预览的入口一致
    if args.command == "capture":
        return run_capture(args)
    if args.command == "calibrate":
        return run_calibrate(args)
    if args.command == "preview":
        return run_preview(args)

    parser.error("未知命令。")
    return 1


if __name__ == "__main__":
    # 使用 SystemExit 传递退出码，便于命令行脚本和外部流程判断执行结果
    raise SystemExit(main())
