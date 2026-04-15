"""
基于已有标定结果预览去畸变效果的独立入口脚本。

使用方法：
1. 先查看当前可用摄像头索引：
   python preview_undistort.py --list-cameras
2. 查看当前支持的画质档位：
   python preview_undistort.py --list-quality-presets
3. 不确定应该选哪个摄像头时，直接运行脚本并按提示选择：
   python preview_undistort.py --calibration-file output/camera_calibration.json
4. 已知摄像头索引时，直接预览实时去畸变效果：
   python preview_undistort.py --calibration-file output/camera_calibration.json --camera-index 1 --quality 720p
5. 如果单屏下左右对比图太宽，可以切换为上下布局：
   python preview_undistort.py --calibration-file output/camera_calibration.json --layout vertical
6. 如果只想检查某一张图片的去畸变结果：
   python preview_undistort.py --calibration-file output/camera_calibration.json --image test.jpg

预览时的按键说明：
- Q / ESC：退出预览窗口
"""

from __future__ import annotations

import argparse
import sys

# 导入底层去畸变预览函数和摄像头探测函数
from calibrate_usb_camera import add_stream_resolution_arguments, list_cameras, print_quality_presets, run_preview


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器，统一管理预览阶段的输入参数。"""
    parser = argparse.ArgumentParser(description="预览实时画面或离线图片的去畸变效果。")

    # 标定文件和输入源参数：既支持实时相机，也支持单张图片验证
    parser.add_argument(
        "--calibration-file",
        default=None,
        help="导出的标定结果 JSON 路径；进入预览模式时必须提供。",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="要打开的 OpenCV 相机索引；不传时会先检测可用摄像头，并让你交互选择。",
    )
    parser.add_argument("--image", default="", help="预览单张图片；提供后将不再打开相机。")
    add_stream_resolution_arguments(
        parser,
        width_help="请求的预览宽度（像素）",
        height_help="请求的预览高度（像素）",
        fourcc_help="请求的相机像素格式，例如 MJPG。",
        allow_list_presets=True,
    )

    # 摄像头选择相关参数：用于排查索引错误或设备顺序变化的问题
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="仅列出当前探测到的摄像头索引，不进入去畸变预览。",
    )
    parser.add_argument(
        "--max-test-cameras",
        type=int,
        default=5,
        help="启动前最多探测多少个摄像头索引，用于列出和选择摄像头。",
    )

    # 显示相关参数：支持切换布局和限制初始显示大小，避免对比图超出单屏范围
    parser.add_argument(
        "--layout",
        choices=("horizontal", "vertical", "raw", "rectified"),
        default="horizontal",
        help="预览布局：horizontal 为左右对比，vertical 为上下对比。",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=1280,
        help="预览窗口的初始最大宽度；程序会自动缩小显示内容以适配该宽度。",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=720,
        help="预览窗口的初始最大高度；程序会自动缩小显示内容以适配该高度。",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.0,
        help="去畸变保留边界的程度，0 更裁边，1 保留更多视场。",
    )
    return parser


def print_available_cameras(available_cameras: list[int]) -> None:
    """打印探测到的摄像头索引，帮助用户选中正确的视频设备。"""
    print("=" * 50)
    print("当前可用摄像头索引")
    print("-" * 50)
    if not available_cameras:
        print("未检测到可用摄像头，请检查 USB 连接、驱动或权限。")
    else:
        for index in available_cameras:
            print(f"  - 摄像头索引: {index}")
    print("=" * 50)


def resolve_camera_index(camera_index: int | None, max_to_test: int) -> int:
    """解析最终用于预览的摄像头索引。

    参数：
        camera_index: 用户显式传入的摄像头索引；为 None 时表示需要自动探测并交互选择。
        max_to_test: 最多探测的摄像头索引数量。

    返回：
        最终用于打开实时预览的摄像头索引。
    """
    # 用户已经指定索引时直接沿用，保持命令行行为简单直接
    if camera_index is not None:
        return camera_index

    available_cameras = list_cameras(max_to_test=max_to_test)
    if not available_cameras:
        raise RuntimeError("未检测到可用摄像头，请检查设备连接后重试。")

    # 只有一个设备时自动选择，避免多余输入
    if len(available_cameras) == 1:
        selected_index = available_cameras[0]
        print(f"仅检测到 1 个可用摄像头，自动选择索引 {selected_index}。")
        return selected_index

    print_available_cameras(available_cameras)

    # 在非交互环境中无法等待用户输入，因此回退到第一个可用索引
    if not sys.stdin.isatty():
        selected_index = available_cameras[0]
        print(f"当前环境不支持交互输入，默认使用索引 {selected_index}。")
        return selected_index

    while True:
        try:
            user_input = input("请输入要使用的摄像头索引（直接回车默认选择第一个）：").strip()
        except EOFError:
            selected_index = available_cameras[0]
            print(f"\n未读取到交互输入，默认使用索引 {selected_index}。")
            return selected_index

        # 允许直接回车，方便快速尝试默认设备
        if not user_input:
            selected_index = available_cameras[0]
            print(f"未输入索引，默认使用 {selected_index}。")
            return selected_index

        try:
            selected_index = int(user_input)
        except ValueError:
            print("输入无效，请输入整数索引，例如 0、1、2。")
            continue

        # 只允许选择已探测成功的设备，避免再次打开错误相机
        if selected_index not in available_cameras:
            print(f"索引 {selected_index} 不在已探测到的列表中，请重新输入。")
            continue
        return selected_index


def main() -> int:
    """脚本主入口：解析参数、选择输入源，并调用底层预览逻辑。"""
    parser = build_parser()
    args = parser.parse_args()

    # 仅查看摄像头时直接返回，不要求标定文件存在
    if args.list_cameras:
        print_available_cameras(list_cameras(max_to_test=args.max_test_cameras))
        return 0

    # 仅查看画质预设时不要求标定文件存在，避免做无关校验
    if args.list_quality_presets:
        print_quality_presets()
        return 0

    # 进入真正的去畸变预览时必须提供标定文件
    if not args.calibration_file:
        parser.error("进入预览模式时必须通过 --calibration-file 指定标定结果 JSON。")

    # 没有指定离线图片时，默认进入实时相机预览，并需要先确定正确的摄像头索引
    if not args.image:
        try:
            args.camera_index = resolve_camera_index(args.camera_index, args.max_test_cameras)
        except Exception as exc:
            print(f"摄像头选择失败: {exc}", file=sys.stderr)
            return 1

    # 在入口层统一规范窗口尺寸，避免出现负值或 0 导致显示异常
    args.window_width = max(0, args.window_width)
    args.window_height = max(0, args.window_height)

    print("=" * 50)
    print("去畸变预览工具")
    print("-" * 50)
    print(f"标定文件: {args.calibration_file}")
    if args.image:
        print(f"预览模式: 单张图片 ({args.image})")
    else:
        print(f"预览模式: 实时相机 (索引 {args.camera_index})")
    print(f"显示布局: {args.layout}")
    print(f"窗口最大尺寸: {args.window_width} x {args.window_height}")
    print("-" * 50)
    print("操作提示:")
    print("  [Q] - 退出程序")
    print("=" * 50)

    try:
        return run_preview(args)
    except Exception as exc:
        print(f"运行时发生错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # 使用 SystemExit 将 main 的返回值转换为进程退出码
    raise SystemExit(main())
