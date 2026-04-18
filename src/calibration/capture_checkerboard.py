"""
独立的棋盘格采集脚本。

文件作用：
1. 交互选择摄像头索引、分辨率和帧率；
2. 实时检测棋盘格角点；
3. 按空格保存原始采集图像，供后续离线标定使用。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CAPTURE_DIR = SCRIPT_DIR / "captures"
DEFAULT_QUALITY_PRESET = "1080p"

QUALITY_PRESETS: dict[str, tuple[int, int]] = {
    "240p": (320, 240),
    "480p": (640, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}

FPS_PRESETS: tuple[float, ...] = (15.0, 30.0, 60.0, 120.0)
COMMON_FOURCC_OPTIONS: tuple[str, ...] = ("AUTO", "MJPG", "YUY2", "YUYV")


def ensure_dir(path: Path) -> Path:
    """确保输出目录存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def has_interactive_input() -> bool:
    """判断当前是否支持命令行交互。"""
    return sys.stdin is not None and sys.stdin.isatty()


def normalize_quality_name(value: str) -> str:
    """统一分辨率预设名称。"""
    return value.strip().lower()


def normalize_fourcc(value: str | None) -> str:
    """统一像素格式字符串；AUTO 表示不主动请求格式。"""
    if value is None:
        return ""
    text = value.strip().upper()
    return "" if text == "AUTO" else text


def decode_fourcc(value: float | int) -> str:
    """把 OpenCV 读回的 FOURCC 数值转成人可读文本。"""
    code = int(value)
    if code <= 0:
        return "unknown"

    chars = [chr((code >> shift) & 0xFF) for shift in (0, 8, 16, 24)]
    text = "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in chars).strip("\x00 ?")
    return text or "unknown"


def build_quality_preset_lines() -> list[str]:
    """生成当前支持的分辨率预设说明。"""
    lines: list[str] = []
    for name, (width, height) in QUALITY_PRESETS.items():
        default_tag = "（默认）" if name == DEFAULT_QUALITY_PRESET else ""
        lines.append(f"  - {name:>5} -> {width}x{height}{default_tag}")
    return lines


def print_quality_presets() -> None:
    """打印当前支持的分辨率预设。"""
    print("=" * 50)
    print("当前支持的分辨率预设")
    print("-" * 50)
    for line in build_quality_preset_lines():
        print(line)
    print("=" * 50)


def list_cameras(max_to_test: int = 5) -> list[int]:
    """探测当前可用的摄像头索引。"""
    available: list[int] = []
    for camera_index in range(max_to_test):
        if os.name == "nt":
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            available.append(camera_index)
            cap.release()
    return available


def print_available_cameras(available_cameras: Sequence[int]) -> None:
    """打印当前探测到的摄像头。"""
    print("=" * 50)
    print("当前可用摄像头索引")
    print("-" * 50)
    if not available_cameras:
        print("未检测到可用摄像头，请检查 USB 连接和驱动。")
    else:
        for index in available_cameras:
            print(f"  - 摄像头索引: {index}")
    print("=" * 50)


def prompt_menu_choice(prompt: str, options: Sequence[str], default_index: int = 0) -> int:
    """显示菜单并读取用户选择。"""
    print(prompt)
    for idx, option in enumerate(options, start=1):
        print(f"  {idx}. {option}")

    while True:
        try:
            user_input = input(f"请输入编号（直接回车默认第 {default_index + 1} 项）：").strip()
        except EOFError:
            print(f"\n未读取到交互输入，默认选择第 {default_index + 1} 项。")
            return default_index

        if not user_input:
            return default_index

        try:
            selected = int(user_input)
        except ValueError:
            print("输入无效，请输入数字编号。")
            continue

        if 1 <= selected <= len(options):
            return selected - 1
        print("编号超出范围，请重新输入。")


def prompt_positive_int(message: str, default_value: int) -> int:
    """读取正整数，用于自定义宽高。"""
    while True:
        try:
            user_input = input(f"{message}（直接回车默认 {default_value}）：").strip()
        except EOFError:
            print(f"\n未读取到交互输入，默认使用 {default_value}。")
            return default_value

        if not user_input:
            return default_value

        try:
            value = int(user_input)
        except ValueError:
            print("输入无效，请输入正整数。")
            continue

        if value > 0:
            return value
        print("输入无效，必须大于 0。")


def prompt_positive_float(message: str, default_value: float) -> float:
    """读取正浮点数，用于自定义帧率。"""
    while True:
        try:
            user_input = input(f"{message}（直接回车默认 {default_value:g}）：").strip()
        except EOFError:
            print(f"\n未读取到交互输入，默认使用 {default_value:g}。")
            return default_value

        if not user_input:
            return default_value

        try:
            value = float(user_input)
        except ValueError:
            print("输入无效，请输入正数。")
            continue

        if value > 0:
            return value
        print("输入无效，必须大于 0。")


def prompt_stream_resolution() -> tuple[int, int, str, str | None]:
    """交互选择相机分辨率。"""
    preset_names = list(QUALITY_PRESETS.keys())
    options = [f"{name} ({QUALITY_PRESETS[name][0]}x{QUALITY_PRESETS[name][1]})" for name in preset_names]
    options.append("自定义分辨率")
    default_index = preset_names.index(DEFAULT_QUALITY_PRESET)

    selected_index = prompt_menu_choice("请选择相机分辨率：", options, default_index)
    if selected_index < len(preset_names):
        preset_name = preset_names[selected_index]
        width, height = QUALITY_PRESETS[preset_name]
        return width, height, f"{preset_name} ({width}x{height})", preset_name

    width = prompt_positive_int("请输入自定义宽度", QUALITY_PRESETS[DEFAULT_QUALITY_PRESET][0])
    height = prompt_positive_int("请输入自定义高度", QUALITY_PRESETS[DEFAULT_QUALITY_PRESET][1])
    return width, height, f"自定义 ({width}x{height})", None


def prompt_stream_fps() -> tuple[float | None, str]:
    """交互选择相机帧率。"""
    options = ["保持驱动默认帧率"]
    options.extend([f"{fps:g} FPS" for fps in FPS_PRESETS])
    options.append("自定义帧率")

    selected_index = prompt_menu_choice("请选择相机帧率：", options, 0)
    if selected_index == 0:
        return None, "驱动默认"
    if 1 <= selected_index <= len(FPS_PRESETS):
        fps = FPS_PRESETS[selected_index - 1]
        return fps, f"{fps:g} FPS"

    fps = prompt_positive_float("请输入自定义帧率", FPS_PRESETS[1])
    return fps, f"{fps:g} FPS"


def resolve_camera_index(camera_index: int | None, max_to_test: int) -> int:
    """解析最终使用的摄像头索引。"""
    if camera_index is not None:
        return camera_index

    available_cameras = list_cameras(max_to_test=max_to_test)
    if not available_cameras:
        raise RuntimeError("未检测到可用摄像头，请检查设备连接后重试。")

    if len(available_cameras) == 1:
        selected_index = available_cameras[0]
        print(f"仅检测到 1 个可用摄像头，自动选择索引 {selected_index}。")
        return selected_index

    print_available_cameras(available_cameras)
    if not has_interactive_input():
        selected_index = available_cameras[0]
        print(f"当前环境不支持交互输入，默认使用索引 {selected_index}。")
        return selected_index

    selected_index = prompt_menu_choice(
        "请选择要使用的摄像头：",
        [f"摄像头索引 {index}" for index in available_cameras],
        0,
    )
    return available_cameras[selected_index]


def add_stream_arguments(parser: argparse.ArgumentParser, *, allow_list_presets: bool = False) -> None:
    """添加相机相关参数。"""
    parser.add_argument(
        "--quality",
        type=normalize_quality_name,
        choices=tuple(QUALITY_PRESETS.keys()),
        default=None,
        help=f"分辨率预设；未手动指定宽高且不走交互选择时默认 {DEFAULT_QUALITY_PRESET}。",
    )
    parser.add_argument("--width", type=int, default=None, help="请求的相机宽度（像素）。")
    parser.add_argument("--height", type=int, default=None, help="请求的相机高度（像素）。")
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="请求的相机帧率；不填时保持驱动默认值，也可在交互模式里选择。",
    )
    parser.add_argument(
        "--fourcc",
        default="AUTO",
        help=f"请求的相机像素格式；常见值可先试 {', '.join(COMMON_FOURCC_OPTIONS)}。",
    )
    if allow_list_presets:
        parser.add_argument(
            "--list-quality-presets",
            action="store_true",
            help="仅列出当前支持的分辨率预设，不进入采集流程。",
        )


def resolve_stream_resolution(args: argparse.Namespace) -> tuple[int, int, str]:
    """解析本次请求的分辨率。"""
    requested_quality = normalize_quality_name(
        str(getattr(args, "quality", "") or DEFAULT_QUALITY_PRESET)
    )
    if requested_quality not in QUALITY_PRESETS:
        raise ValueError(f"不支持的分辨率预设: {requested_quality}")

    raw_width = getattr(args, "width", None)
    raw_height = getattr(args, "height", None)
    preset_width, preset_height = QUALITY_PRESETS[requested_quality]

    if raw_width is None and raw_height is None:
        width = preset_width
        height = preset_height
        label = f"{requested_quality} ({width}x{height})"
    elif raw_width is None or raw_height is None:
        raise ValueError("手动指定分辨率时必须同时提供 --width 和 --height。")
    else:
        width = int(raw_width)
        height = int(raw_height)
        if width <= 0 or height <= 0:
            raise ValueError("手动指定的宽高必须是正整数。")
        label = f"自定义 ({width}x{height})"

    args.width = width
    args.height = height
    return width, height, label


def resolve_stream_fps(args: argparse.Namespace) -> tuple[float | None, str]:
    """解析本次请求的帧率。"""
    fps = getattr(args, "fps", None)
    if fps is None:
        return None, "驱动默认"

    fps = float(fps)
    if fps <= 0:
        raise ValueError("请求帧率必须大于 0。")
    args.fps = fps
    return fps, f"{fps:g} FPS"


def open_camera(
    camera_index: int,
    width: int,
    height: int,
    fps: float | None,
    fourcc: str,
) -> cv2.VideoCapture:
    """打开相机，并按请求设置分辨率、帧率和像素格式。"""
    if os.name == "nt":
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)

    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if fps is not None and hasattr(cv2, "CAP_PROP_FPS"):
        cap.set(cv2.CAP_PROP_FPS, fps)
    if fourcc:
        if len(fourcc) != 4:
            raise ValueError("FOURCC 必须是 4 个字符，例如 MJPG 或 YUY2。")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    if width > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def print_camera_runtime_info(
    cap: cv2.VideoCapture,
    requested_width: int,
    requested_height: int,
    requested_fps: float | None,
    requested_fourcc: str,
    actual_frame: np.ndarray,
) -> None:
    """打印请求值和驱动实际生效值。"""
    actual_fps = 0.0
    if hasattr(cv2, "CAP_PROP_FPS"):
        actual_fps = float(cap.get(cv2.CAP_PROP_FPS))

    actual_fourcc = "unknown"
    if hasattr(cv2, "CAP_PROP_FOURCC"):
        actual_fourcc = decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC))

    backend_name = "unknown"
    if hasattr(cap, "getBackendName"):
        try:
            backend_name = cap.getBackendName()
        except Exception:
            backend_name = "unknown"

    requested_fps_text = "驱动默认" if requested_fps is None else f"{requested_fps:g} FPS"
    actual_fps_text = "unknown" if actual_fps <= 0 else f"{actual_fps:.2f} FPS"
    print("相机流参数：")
    print(f"  请求分辨率: {requested_width}x{requested_height}")
    print(f"  实际分辨率: {actual_frame.shape[1]}x{actual_frame.shape[0]}")
    print(f"  请求帧率: {requested_fps_text}")
    print(f"  实际帧率: {actual_fps_text}")
    print(f"  请求像素格式: {requested_fourcc or 'AUTO'}")
    print(f"  实际像素格式: {actual_fourcc}")
    print(f"  OpenCV 后端: {backend_name}")


def detect_checkerboard(
    gray: np.ndarray,
    pattern_size: tuple[int, int],
    scale: float = 1.0,
) -> tuple[bool, np.ndarray | None]:
    """检测棋盘格角点，并在找到后做亚像素精细化。"""
    if scale != 1.0:
        height, width = gray.shape[:2]
        small_gray = cv2.resize(gray, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_LINEAR)
        working_gray = small_gray
    else:
        working_gray = gray

    if hasattr(cv2, "findChessboardCornersSB"):
        found, corners = cv2.findChessboardCornersSB(working_gray, pattern_size, flags=cv2.CALIB_CB_ACCURACY)
        if found:
            if scale != 1.0:
                corners /= scale
            return True, corners.astype(np.float32)

    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(working_gray, pattern_size, flags)
    if not found:
        return False, None

    if scale != 1.0:
        corners /= scale

    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
    refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return True, refined


def draw_status(frame: np.ndarray, lines: Sequence[str], color: tuple[int, int, int]) -> np.ndarray:
    """在图像左上角叠加状态文字。"""
    overlay = frame.copy()
    y = 30
    for text in lines:
        cv2.putText(overlay, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2, cv2.LINE_AA)
        y += 30
    return overlay


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="独立的棋盘格采集工具。")
    parser.add_argument("--camera-index", type=int, default=None, help="要打开的摄像头索引；不填时自动探测并支持交互选择。")
    add_stream_arguments(parser, allow_list_presets=True)
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="仅列出当前探测到的摄像头索引，不进入采集流程。",
    )
    parser.add_argument(
        "--max-test-cameras",
        type=int,
        default=5,
        help="启动前最多探测多少个摄像头索引。",
    )
    parser.add_argument(
        "--interactive-stream-config",
        action="store_true",
        help="启动前交互选择相机索引、分辨率和帧率。",
    )
    parser.add_argument("--cols", type=int, required=True, help="棋盘格内角点列数（宽度方向）。")
    parser.add_argument("--rows", type=int, required=True, help="棋盘格内角点行数（高度方向）。")
    parser.add_argument("--output-dir", default=str(DEFAULT_CAPTURE_DIR), help="保存采集图像的目录。")
    parser.add_argument(
        "--min-interval-sec",
        type=float,
        default=0.6,
        help="两次保存之间的最小时间间隔，避免连按空格产生重复样本。",
    )
    parser.add_argument(
        "--preview-scale",
        type=float,
        default=0.5,
        help="角点检测前的缩放比例，数值越小越流畅，但稳定性可能下降。",
    )
    parser.add_argument(
        "--detect-interval",
        type=int,
        default=2,
        help="每隔多少帧执行一次角点检测；1 表示每帧都检测。",
    )
    return parser


def run_capture(args: argparse.Namespace) -> int:
    """执行棋盘格采集流程。"""
    if getattr(args, "camera_index", None) is None:
        args.camera_index = resolve_camera_index(args.camera_index, args.max_test_cameras)

    should_prompt_resolution = (
        has_interactive_input()
        and (
            getattr(args, "interactive_stream_config", False)
            or (getattr(args, "quality", None) is None and getattr(args, "width", None) is None and getattr(args, "height", None) is None)
        )
    )
    should_prompt_fps = (
        has_interactive_input()
        and (
            getattr(args, "interactive_stream_config", False)
            or getattr(args, "fps", None) is None
        )
    )

    if should_prompt_resolution:
        width, height, resolution_label, resolved_quality = prompt_stream_resolution()
        args.width = width
        args.height = height
        args.quality = resolved_quality
    else:
        width, height, resolution_label = resolve_stream_resolution(args)

    if should_prompt_fps:
        fps, fps_label = prompt_stream_fps()
        args.fps = fps
    else:
        fps, fps_label = resolve_stream_fps(args)

    fourcc = normalize_fourcc(getattr(args, "fourcc", "AUTO") or "AUTO")
    preview_scale = float(max(0.1, min(1.0, args.preview_scale)))
    detect_interval = max(1, int(args.detect_interval))

    cap = open_camera(args.camera_index, width, height, fps, fourcc)
    if not cap.isOpened():
        raise RuntimeError("无法打开采集相机。")

    output_dir = ensure_dir(Path(args.output_dir).resolve())
    pattern_size = (args.cols, args.rows)
    saved_count = 0
    last_saved_time = 0.0
    frame_index = 0
    last_found = False
    last_corners = None
    runtime_info_printed = False

    print("=" * 50)
    print("棋盘格采集工具")
    print("-" * 50)
    print(f"摄像头索引: {args.camera_index}")
    print(f"请求分辨率: {resolution_label}")
    print(f"请求帧率: {fps_label}")
    print(f"请求像素格式: {fourcc or 'AUTO'}")
    print(f"输出目录: {output_dir}")
    print("操作说明: [空格] 保存原图  [Q/ESC] 退出")
    print("=" * 50)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("读取相机帧失败。")

            if not runtime_info_printed:
                print_camera_runtime_info(cap, width, height, fps, fourcc, frame)
                runtime_info_printed = True

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            should_detect_now = (frame_index % detect_interval == 0) or (last_corners is None)
            if should_detect_now:
                last_found, last_corners = detect_checkerboard(gray, pattern_size, scale=preview_scale)

            preview = frame.copy()
            if should_detect_now and last_found and last_corners is not None:
                cv2.drawChessboardCorners(preview, pattern_size, last_corners, last_found)

            preview = draw_status(
                preview,
                [
                    f"board: {'DETECTED' if last_found else 'not found'}",
                    f"saved images: {saved_count}",
                    f"raw size: {frame.shape[1]}x{frame.shape[0]}",
                    f"detect every: {detect_interval} frame(s)",
                    "SPACE=save  Q/ESC=quit",
                ],
                (0, 255, 0) if last_found else (0, 0, 255),
            )
            cv2.imshow("checkerboard_capture", preview)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

            if key == ord(" "):
                now = time.time()
                if now - last_saved_time < args.min_interval_sec:
                    frame_index += 1
                    continue

                save_found = last_found
                if not should_detect_now:
                    save_found, last_corners = detect_checkerboard(gray, pattern_size, scale=preview_scale)
                    last_found = save_found

                if not save_found:
                    print("跳过：当前帧未检测到完整棋盘格角点。")
                else:
                    image_path = output_dir / f"calib_{saved_count:03d}.jpg"
                    cv2.imwrite(str(image_path), frame)
                    print(f"已保存: {image_path}")
                    saved_count += 1
                    last_saved_time = now

            frame_index += 1
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print(f"采集结束。共保存 {saved_count} 张图像至: {output_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """脚本主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_cameras:
        print_available_cameras(list_cameras(max_to_test=args.max_test_cameras))
        return 0

    if args.list_quality_presets:
        print_quality_presets()
        return 0

    try:
        return run_capture(args)
    except Exception as exc:
        print(f"运行时发生错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
