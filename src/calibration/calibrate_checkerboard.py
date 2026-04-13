"""
基于已采集棋盘格图像执行相机标定的独立入口脚本。

使用方法：
1. 使用默认采集目录中的图像进行标定：
   python calibrate_checkerboard.py --cols 10 --rows 7
2. 指定棋盘格单格物理尺寸并输出到指定目录：
   python calibrate_checkerboard.py --cols 10 --rows 7 --square-size-mm 20 --output-dir output
3. 针对广角镜头优先尝试鱼眼模型：
   python calibrate_checkerboard.py --cols 10 --rows 7 --model fisheye

说明：
- `--cols` 和 `--rows` 表示棋盘格内角点数量，不是黑白方格数量。
- 标定前应保证采集图像分辨率一致、角点清晰，并尽量覆盖不同位置和姿态。
"""

from __future__ import annotations

import argparse

# 复用底层标定脚本中的默认目录和标定主流程，避免两套实现分叉
from calibrate_usb_camera import DEFAULT_CAPTURE_DIR, DEFAULT_OUTPUT_DIR, run_calibrate


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器，定义标定阶段需要的输入项。"""
    parser = argparse.ArgumentParser(description="根据棋盘格图像估计相机内参与畸变参数。")

    # 输入输出路径参数：默认沿用 calibration 目录下的既有数据组织方式
    parser.add_argument("--image-dir", default=str(DEFAULT_CAPTURE_DIR), help="存放标定图像的目录路径。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="保存标定结果的输出目录。")
    parser.add_argument("--camera-name", default="usb_camera", help="写入 ROS YAML 的相机名称。")

    # 棋盘格和模型参数：这些参数会直接影响角点坐标解释和标定模型选择
    parser.add_argument("--cols", type=int, required=True, help="棋盘格内角点列数（宽度方向）。")
    parser.add_argument("--rows", type=int, required=True, help="棋盘格内角点行数（高度方向）。")
    parser.add_argument(
        "--square-size-mm",
        type=float,
        default=20.0,
        help="棋盘格单格边长，单位为毫米。",
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


def main() -> int:
    """脚本主入口：解析参数后调用底层标定流程。"""
    parser = build_parser()
    args = parser.parse_args()
    return run_calibrate(args)


if __name__ == "__main__":
    # 使用 SystemExit 将返回值转换为进程退出码，便于脚本集成调用
    raise SystemExit(main())
