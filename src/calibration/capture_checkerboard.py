"""
采集棋盘格标定图像的独立入口脚本。

使用方法：
1. 先查看当前可用摄像头索引：
   python capture_checkerboard.py --list-cameras
2. 不确定应该选哪个摄像头时，直接运行脚本并按提示选择：
   python capture_checkerboard.py --cols 10 --rows 7
3. 已知摄像头索引时，直接指定后开始采集：
   python capture_checkerboard.py --camera-index 1 --cols 10 --rows 7
4. 如果预览仍然偏卡，可以继续降低角点检测负载：
   python capture_checkerboard.py --camera-index 1 --cols 10 --rows 7 --preview-scale 0.4 --detect-interval 3

参数说明：
- `--preview-scale`
  角点检测前的缩放比例，范围建议在 0.1 到 1.0 之间。
  数值越小，检测越快，但角点定位稳定性可能下降。
- `--detect-interval`
  每隔多少帧执行一次角点检测。
  数值越大，预览越流畅，但角点状态更新会更慢。

采集时的按键说明：
- 空格：当检测到完整棋盘格角点时保存当前原始图像
- Q / ESC：退出采集
"""

from __future__ import annotations

import argparse
import sys

# 导入底层标定工具中的默认保存目录、摄像头探测函数和采集主流程
from calibrate_usb_camera import DEFAULT_CAPTURE_DIR, list_cameras, run_capture


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器，统一管理采集阶段需要的配置项。"""
    parser = argparse.ArgumentParser(description="捕获用于相机标定的棋盘格图像。")

    # 相机相关参数：支持直接指定索引，也支持先列出摄像头再交互选择
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="要打开的 OpenCV 相机索引；不传时会先检测可用摄像头，并让你交互选择。",
    )
    parser.add_argument("--width", type=int, default=1920, help="请求的采集宽度（像素）。")
    parser.add_argument("--height", type=int, default=1080, help="请求的采集高度（像素）。")
    parser.add_argument("--fourcc", default="MJPG", help="请求的相机像素格式，例如 MJPG、YUYV。")
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="仅列出当前探测到的摄像头索引，不进入图像采集。",
    )
    parser.add_argument(
        "--max-test-cameras",
        type=int,
        default=5,
        help="启动前最多探测多少个摄像头索引，用于列出和选择摄像头。",
    )

    # 棋盘格相关参数：这里使用的是内角点数量，不是方格数量
    parser.add_argument("--cols", type=int, default=None, help="标定板内角点列数（宽度方向）。")
    parser.add_argument("--rows", type=int, default=None, help="标定板内角点行数（高度方向）。")

    # 输出和性能相关参数：输出目录保持原有逻辑，另外补充预览调优参数
    parser.add_argument("--output-dir", default=str(DEFAULT_CAPTURE_DIR), help="保存图像的目录路径。")
    parser.add_argument(
        "--min-interval-sec",
        type=float,
        default=0.6,
        help="两次保存帧之间的最小时间间隔（秒），用于避免连按空格导致重复采样。",
    )
    parser.add_argument(
        "--preview-scale",
        type=float,
        default=0.5,
        help="角点检测前的缩放比例，数值越小越流畅，但过小可能降低检测稳定性；1.0 表示不缩放。",
    )
    parser.add_argument(
        "--detect-interval",
        type=int,
        default=2,
        help="每隔多少帧执行一次角点检测；1 表示每帧检测，数值越大越流畅。",
    )

    # 兼容旧参数写法，避免已有命令无法继续使用
    parser.add_argument(
        "--fast-preview",
        dest="preview_scale",
        action="store_const",
        const=0.5,
        help="兼容旧参数：等价于 --preview-scale 0.5。",
    )
    parser.add_argument(
        "--no-fast-preview",
        dest="preview_scale",
        action="store_const",
        const=1.0,
        help="兼容旧参数：关闭检测缩放，按原始分辨率做角点检测。",
    )

    return parser


def print_available_cameras(available_cameras: list[int]) -> None:
    """打印探测到的摄像头索引，方便用户手动选择正确设备。"""
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
    """解析最终要使用的摄像头索引。

    参数：
        camera_index: 用户显式传入的摄像头索引；为 None 时表示需要自动探测并交互选择。
        max_to_test: 最多探测的摄像头索引数量。

    返回：
        最终用于 OpenCV 打开摄像头的索引值。
    """
    # 如果用户已经明确指定索引，就直接使用该值，避免改变既有使用习惯
    if camera_index is not None:
        return camera_index

    available_cameras = list_cameras(max_to_test=max_to_test)
    if not available_cameras:
        raise RuntimeError("未检测到可用摄像头，请检查设备连接后重试。")

    # 只有一个摄像头时自动选择，减少一次额外交互
    if len(available_cameras) == 1:
        selected_index = available_cameras[0]
        print(f"仅检测到 1 个可用摄像头，自动选择索引 {selected_index}。")
        return selected_index

    print_available_cameras(available_cameras)

    # 非交互环境下无法 input，此时回退到第一个可用摄像头，保证脚本仍可运行
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

        # 允许直接回车，减少频繁试错时的输入成本
        if not user_input:
            selected_index = available_cameras[0]
            print(f"未输入索引，默认使用 {selected_index}。")
            return selected_index

        try:
            selected_index = int(user_input)
        except ValueError:
            print("输入无效，请输入整数索引，例如 0、1、2。")
            continue

        # 只允许选择已经探测成功的索引，避免再次打开错误设备
        if selected_index not in available_cameras:
            print(f"索引 {selected_index} 不在已探测到的列表中，请重新输入。")
            continue
        return selected_index


def main() -> int:
    """脚本主入口：解析参数、选择摄像头，并调用底层采集逻辑。"""
    parser = build_parser()
    args = parser.parse_args()

    # 仅查看摄像头时不进入采集流程，避免误开窗口
    if args.list_cameras:
        print_available_cameras(list_cameras(max_to_test=args.max_test_cameras))
        return 0

    # 只有真正进入采集流程时，棋盘格规格才是必填参数
    if args.cols is None or args.rows is None:
        parser.error("进入采集模式时必须通过 --cols 和 --rows 指定棋盘格内角点数量。")

    # 在入口层先统一修正性能参数，保证终端提示和实际运行配置一致
    args.preview_scale = float(max(0.1, min(1.0, args.preview_scale)))
    args.detect_interval = max(1, args.detect_interval)

    try:
        args.camera_index = resolve_camera_index(args.camera_index, args.max_test_cameras)
    except Exception as exc:
        print(f"摄像头选择失败: {exc}", file=sys.stderr)
        return 1

    print("=" * 50)
    print("相机标定图像采集工具")
    print("-" * 50)
    print(f"相机索引: {args.camera_index}")
    print(f"标定板尺寸: {args.cols} x {args.rows}")
    print(f"输出目录: {args.output_dir}")
    print(f"检测缩放比例: {args.preview_scale}")
    print(f"检测间隔: 每 {max(1, args.detect_interval)} 帧检测一次")
    print("-" * 50)
    print("操作提示:")
    print("  [空格] - 当检测到角点时保存当前帧")
    print("  [Q]    - 退出程序")
    print("=" * 50)

    try:
        return run_capture(args)
    except Exception as exc:
        print(f"运行时发生错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # 使用 SystemExit 将 main 的返回值转换为进程退出码
    raise SystemExit(main())
