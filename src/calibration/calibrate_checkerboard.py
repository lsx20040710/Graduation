"""
独立的离线标定脚本。

文件作用：
1. 读取采集好的棋盘格图像；
2. 计算标准针孔或鱼眼模型的相机参数；
3. 输出 JSON 和 ROS 可用的 `camera_info.yaml`。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CAPTURE_DIR = SCRIPT_DIR / "captures"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"


@dataclass
class CalibrationResult:
    """保存一次标定的完整结果，便于写盘和后续正畸脚本复用。"""

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
    roi: tuple[int, int, int, int]


def ensure_dir(path: Path) -> Path:
    """确保输出目录存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def collect_image_paths(image_dir: Path) -> list[Path]:
    """收集目录中的常见图像文件。"""
    image_paths: list[Path] = []
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        image_paths.extend(sorted(image_dir.glob(pattern)))
    return sorted(image_paths)


def build_object_points(cols: int, rows: int, square_size_mm: float) -> np.ndarray:
    """生成棋盘格在标定板坐标系下的三维角点坐标。"""
    object_points = np.zeros((rows * cols, 3), np.float32)
    object_points[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    object_points *= square_size_mm
    return object_points


def detect_checkerboard(gray: np.ndarray, pattern_size: tuple[int, int]) -> tuple[bool, np.ndarray | None]:
    """检测棋盘格角点，并做亚像素精细化。"""
    if hasattr(cv2, "findChessboardCornersSB"):
        found, corners = cv2.findChessboardCornersSB(gray, pattern_size, flags=cv2.CALIB_CB_ACCURACY)
        if found:
            return True, corners.astype(np.float32)

    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
    if not found:
        return False, None

    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
    refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return True, refined


def compute_standard_error(
    object_points: Sequence[np.ndarray],
    image_points: Sequence[np.ndarray],
    rvecs: Sequence[np.ndarray],
    tvecs: Sequence[np.ndarray],
    camera_matrix: np.ndarray,
    distortion_coeffs: np.ndarray,
) -> float:
    """计算标准针孔模型的平均重投影误差。"""
    total_error = 0.0
    total_points = 0
    for objp, corners, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
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
    """计算鱼眼模型的平均重投影误差。"""
    total_error = 0.0
    total_points = 0
    for objp, corners, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        projected, _ = cv2.fisheye.projectPoints(objp, rvec, tvec, camera_matrix, distortion_coeffs)
        total_error += cv2.norm(corners, projected, cv2.NORM_L2)
        total_points += len(projected)
    return total_error / max(total_points, 1)


def save_json(result: CalibrationResult, path: Path) -> None:
    """将标定结果写入 JSON。"""
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
    """写出 ROS 可直接使用的 `camera_info.yaml`。"""
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


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="独立的棋盘格离线标定工具。")
    parser.add_argument("--image-dir", default=str(DEFAULT_CAPTURE_DIR), help="存放标定图像的目录。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="保存标定结果的目录。")
    parser.add_argument("--camera-name", default="usb_camera", help="写入 ROS YAML 的相机名称。")
    parser.add_argument("--cols", type=int, required=True, help="棋盘格内角点列数（宽度方向）。")
    parser.add_argument("--rows", type=int, required=True, help="棋盘格内角点行数（高度方向）。")
    parser.add_argument(
        "--square-size-mm",
        type=float,
        default=20.0,
        help="棋盘格单格边长，单位毫米。",
    )
    parser.add_argument(
        "--model",
        choices=("fisheye", "standard"),
        default="fisheye",
        help="标定模型类型；超广角镜头通常优先尝试 fisheye。",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.0,
        help="去畸变保留边界的程度，0 更裁边，1 保留更多原始视场。",
    )
    parser.add_argument(
        "--min-images",
        type=int,
        default=12,
        help="继续执行标定所需的最少有效图像数量。",
    )
    return parser


def run_calibrate(args: argparse.Namespace) -> int:
    """执行离线标定流程。"""
    image_dir = Path(args.image_dir).resolve()
    output_dir = ensure_dir(Path(args.output_dir).resolve())
    debug_dir = ensure_dir(output_dir / "debug_corners")

    image_paths = collect_image_paths(image_dir)
    if not image_paths:
        raise RuntimeError(f"在 {image_dir} 下未找到可用的标定图像。")

    pattern_size = (args.cols, args.rows)
    object_template = build_object_points(args.cols, args.rows, args.square_size_mm)
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    image_size: tuple[int, int] | None = None

    for image_path in image_paths:
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"跳过无法读取的图像: {image_path}")
            continue

        height, width = image.shape[:2]
        if image_size is None:
            image_size = (width, height)
        elif image_size != (width, height):
            print(f"跳过分辨率不一致的图像: {image_path}")
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, corners = detect_checkerboard(gray, pattern_size)
        preview = image.copy()

        if found and corners is not None:
            cv2.drawChessboardCorners(preview, pattern_size, corners, found)
            if args.model == "fisheye":
                object_points.append(object_template.reshape(-1, 1, 3).astype(np.float64))
                image_points.append(corners.reshape(-1, 1, 2).astype(np.float64))
            else:
                object_points.append(object_template.astype(np.float32))
                image_points.append(corners.astype(np.float32))

        cv2.imwrite(str(debug_dir / f"{image_path.stem}_corners.jpg"), preview)

    if image_size is None:
        raise RuntimeError("未能从输入图像中解析出有效分辨率。")

    if len(image_points) < args.min_images:
        raise RuntimeError(
            f"有效标定图像只有 {len(image_points)} 张，少于要求的最小数量 {args.min_images}。"
        )

    width, height = image_size
    if args.model == "fisheye":
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

    json_path = output_dir / "camera_calibration.json"
    yaml_path = output_dir / "camera_info.yaml"
    save_json(result, json_path)
    save_ros_camera_info(result, args.camera_name, yaml_path)

    print("标定完成。")
    print(f"模型类型: {result.model}")
    print(f"有效图像: {result.valid_images}/{result.total_images}")
    print(f"图像分辨率: {result.image_width}x{result.image_height}")
    print(f"RMS: {result.rms:.6f}")
    print(f"平均重投影误差: {result.mean_error_px:.6f} px")
    print(f"JSON 输出: {json_path}")
    print(f"ROS YAML 输出: {yaml_path}")
    print(f"角点可视化输出: {debug_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """脚本主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_calibrate(args)
    except Exception as exc:
        print(f"运行时发生错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
