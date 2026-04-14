"""
文件作用：
为海参检测模型提供可复用的推理入口，同时保留本地交互式选择界面。

主要内容：
1. 自动搜索当前工程里最新的 YOLO 权重，并允许用户手动切换其他 .pt 文件；
2. 交互选择识别模式，支持图片、视频和摄像头三种输入源；
3. 将权重搜索、路径选择、摄像头探测和推理执行拆成独立函数，便于后续工程直接复用；
4. 提供可直接 import 的推理类，方便后续视觉伺服链路在单帧或连续流上复用检测能力。
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

# Windows 环境里，OpenCV、PyTorch、NumPy 混合使用时偶尔会触发 OpenMP 重复加载报错。
# 这里沿用训练脚本的兼容处理，避免脚本一启动就因为底层运行时冲突退出。
if os.name == "nt":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2
from ultralytics import YOLO

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:
    # 某些无桌面环境下可能无法正常导入 Tk。
    # 这里保留降级分支，后续自动退回命令行交互，避免脚本完全不可用。
    tk = None
    filedialog = None
    messagebox = None
    simpledialog = None
    ttk = None


# 当前脚本所在目录，所有相对路径都以这里为基准，避免从其他目录启动时找不到权重或测试素材。
SCRIPT_DIR = Path(__file__).resolve().parent

# 默认推理结果输出目录，和训练结果分开，避免识别结果覆盖训练产物。
DEFAULT_PREDICT_PROJECT_DIR = SCRIPT_DIR / "runs" / "predict"

# 统一维护常见图片和视频后缀，用于交互选择时给出更明确的过滤条件。
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v"}

# 摄像头分辨率优先按常见 USB 相机档位给出选项，兼顾当前设备说明里的 240p/480p/720p/1080p。
CAMERA_RESOLUTION_PRESETS = [
    ("default", "保持相机默认分辨率"),
    ("1920x1080", "1920x1080 (1080p)"),
    ("1280x720", "1280x720 (720p)"),
    ("640x480", "640x480 (480p)"),
    ("320x240", "320x240 (240p)"),
    ("custom", "自定义分辨率"),
]

# 识别模式在模块内统一使用英文键值，便于和 YOLO 接口以及命令行参数保持一致。
InferenceMode = Literal["image", "video", "camera"]


@dataclass(frozen=True)
class CameraInfo:
    """
    作用：
    记录可用摄像头的索引和基础分辨率信息，方便界面和日志里展示。
    """

    index: int
    width: int
    height: int
    backend_name: str

    @property
    def display_name(self) -> str:
        """返回给交互界面展示的摄像头说明文本。"""

        resolution_text = "未知分辨率"
        if self.width > 0 and self.height > 0:
            resolution_text = f"{self.width}x{self.height}"
        return f"摄像头 {self.index} | 分辨率：{resolution_text} | 后端：{self.backend_name}"


@dataclass
class InferenceConfig:
    """
    作用：
    统一管理一次推理任务的核心配置，便于命令行入口和其他工程共用同一套参数结构。
    """

    weight_path: Path
    mode: InferenceMode
    source: Path | int
    camera_resolution: tuple[int, int] | None = None
    conf: float = 0.25
    imgsz: int | None = None
    device: str | None = None
    show: bool = True
    save: bool = True
    project_dir: Path = field(default_factory=lambda: DEFAULT_PREDICT_PROJECT_DIR)
    run_name: str | None = None

    def source_text(self) -> str:
        """返回适合打印日志的输入源描述。"""

        if isinstance(self.source, Path):
            return str(self.source)
        return f"camera:{self.source}"


@dataclass
class InferenceSummary:
    """
    作用：
    汇总一次推理任务的执行结果，方便上层模块拿到统计信息后继续联动其他流程。
    """

    mode: InferenceMode
    weight_path: Path
    source_text: str
    frame_count: int
    detection_count: int
    save_dir: Path | None
    actual_resolution: tuple[int, int] | None = None


class Yolo26Inferencer:
    """
    作用：
    封装 YOLO 模型加载和多输入源推理逻辑，方便后续工程直接引用。
    """

    def __init__(self, weight_path: str | Path, device: str | None = None) -> None:
        """
        作用：
        根据权重路径初始化模型实例。

        参数：
        - weight_path: YOLO 权重文件路径。
        - device: 推理设备，示例值包括 "cpu"、"0"、"0,1"。
        """

        self.weight_path = resolve_existing_file(weight_path)
        self.device = device.strip() if isinstance(device, str) and device.strip() else None

        # 模型对象在初始化阶段一次性创建，避免图片/视频/摄像头之间重复加载权重。
        self.model = YOLO(str(self.weight_path))

    def infer_frame(self, frame, conf: float = 0.25, imgsz: int | None = None):
        """
        作用：
        对单帧图像做一次推理，供后续视觉伺服或上层控制模块直接复用。

        参数：
        - frame: OpenCV 读取到的 BGR 图像数组。
        - conf: 置信度阈值。
        - imgsz: 推理尺寸；传 None 表示沿用 YOLO 默认策略。

        返回：
        - Results: ultralytics 的单帧推理结果对象。
        """

        if frame is None:
            raise ValueError("单帧推理失败：输入 frame 为空。")

        predict_kwargs = self._build_common_predict_kwargs(conf=conf, imgsz=imgsz, show=False, save=False)
        results = self.model.predict(source=frame, **predict_kwargs)
        if not results:
            raise RuntimeError("单帧推理未返回有效结果。")
        return results[0]

    def run(self, config: InferenceConfig) -> InferenceSummary:
        """
        作用：
        按配置执行一次完整推理任务。

        参数：
        - config: 本次推理的统一配置对象。

        返回：
        - InferenceSummary: 任务执行后的统计信息。
        """

        # 统一在真正执行前补齐 run_name，确保打印信息、保存目录和实际输出路径保持一致。
        if config.save and not config.run_name:
            config.run_name = build_default_run_name(config.mode)

        if config.mode == "image":
            return self.run_image(config)
        if config.mode == "video":
            return self.run_video(config)
        if config.mode == "camera":
            return self.run_camera(config)
        raise ValueError(f"不支持的识别模式：{config.mode}")

    def run_image(self, config: InferenceConfig) -> InferenceSummary:
        """
        作用：
        对单张图片执行推理，并返回统计信息。

        参数：
        - config: 图片推理配置，source 必须是图片路径。

        返回：
        - InferenceSummary: 图片推理摘要。
        """

        source_path = ensure_mode_file_source(config.mode, config.source)
        predict_kwargs = self._build_common_predict_kwargs(
            conf=config.conf,
            imgsz=config.imgsz,
            show=config.show,
            save=config.save,
            project_dir=config.project_dir,
            run_name=config.run_name,
        )

        results = self.model.predict(source=str(source_path), **predict_kwargs)
        detection_count = sum(len(result.boxes) for result in results if result.boxes is not None)

        return InferenceSummary(
            mode=config.mode,
            weight_path=self.weight_path,
            source_text=str(source_path),
            frame_count=len(results),
            detection_count=detection_count,
            save_dir=self._resolve_save_dir(config),
        )

    def run_video(self, config: InferenceConfig) -> InferenceSummary:
        """
        作用：
        对视频文件执行连续推理，并统计总帧数与总检测框数量。

        参数：
        - config: 视频推理配置，source 必须是视频路径。

        返回：
        - InferenceSummary: 视频推理摘要。
        """

        source_path = ensure_mode_file_source(config.mode, config.source)
        predict_kwargs = self._build_common_predict_kwargs(
            conf=config.conf,
            imgsz=config.imgsz,
            show=config.show,
            save=config.save,
            project_dir=config.project_dir,
            run_name=config.run_name,
        )

        # 视频场景改成流式遍历，避免长视频一次性把所有帧结果堆进内存。
        frame_count = 0
        detection_count = 0
        result_stream = self.model.predict(source=str(source_path), stream=True, **predict_kwargs)
        for result in result_stream:
            frame_count += 1
            if result.boxes is not None:
                detection_count += len(result.boxes)

        return InferenceSummary(
            mode=config.mode,
            weight_path=self.weight_path,
            source_text=str(source_path),
            frame_count=frame_count,
            detection_count=detection_count,
            save_dir=self._resolve_save_dir(config),
        )

    def run_camera(self, config: InferenceConfig) -> InferenceSummary:
        """
        作用：
        对本地摄像头执行连续推理，适合现场联调或后续上层控制链路接入前的识别验证。

        参数：
        - config: 摄像头推理配置，source 必须是摄像头索引。

        返回：
        - InferenceSummary: 摄像头推理摘要。
        """

        if not isinstance(config.source, int):
            raise ValueError("摄像头模式要求 source 为整数索引。")

        backend_flag = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        capture = cv2.VideoCapture(config.source, backend_flag)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"无法打开摄像头 {config.source}，请检查索引或设备占用情况。")

        requested_resolution = config.camera_resolution
        if requested_resolution is not None:
            requested_width, requested_height = requested_resolution

            # 分辨率必须在真正读帧前写入，否则很多 USB 相机会忽略设置请求。
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)

        window_name = f"YOLO Camera {config.source}"
        frame_count = 0
        detection_count = 0
        writer = None
        save_dir = self._resolve_save_dir(config)

        try:
            actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_resolution = (actual_width, actual_height)

            if requested_resolution is not None:
                print(f"摄像头请求分辨率：{requested_resolution[0]}x{requested_resolution[1]}")
            print(f"摄像头实际分辨率：{actual_width}x{actual_height}")

            # 某些驱动会静默回退到它真正支持的档位，这里把差异明确提示出来，方便联调。
            if requested_resolution is not None and requested_resolution != actual_resolution:
                print("注意：当前摄像头或驱动未完全接受请求分辨率，已按实际分辨率继续运行。")

            if config.save and save_dir is not None:
                save_dir.mkdir(parents=True, exist_ok=True)
                output_path = save_dir / f"camera_{config.source}.mp4"

                capture_fps = capture.get(cv2.CAP_PROP_FPS)
                if capture_fps <= 1:
                    # USB 相机常见情况是拿不到有效 FPS，这里回退到 30，保证录制文件能正常写出。
                    capture_fps = 30.0

                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(output_path), fourcc, capture_fps, actual_resolution)
                if not writer.isOpened():
                    raise RuntimeError(f"无法创建视频输出文件：{output_path}")

            while True:
                read_ok, frame = capture.read()
                if not read_ok or frame is None:
                    print("摄像头读帧失败，当前推理任务结束。")
                    break

                result = self.infer_frame(frame=frame, conf=config.conf, imgsz=config.imgsz)
                frame_count += 1
                if result.boxes is not None:
                    detection_count += len(result.boxes)

                annotated_frame = result.plot()

                if writer is not None:
                    writer.write(annotated_frame)

                if config.show:
                    cv2.imshow(window_name, annotated_frame)

                    # 摄像头模式下保留 q / Esc 退出，避免必须强制关进程才能结束演示。
                    key_code = cv2.waitKey(1) & 0xFF
                    if key_code in (27, ord("q"), ord("Q")):
                        break

            return InferenceSummary(
                mode=config.mode,
                weight_path=self.weight_path,
                source_text=f"camera:{config.source}",
                frame_count=frame_count,
                detection_count=detection_count,
                save_dir=save_dir,
                actual_resolution=actual_resolution,
            )
        finally:
            capture.release()
            if writer is not None:
                writer.release()
            if config.show:
                cv2.destroyAllWindows()

    def _build_common_predict_kwargs(
        self,
        conf: float,
        imgsz: int | None,
        show: bool,
        save: bool,
        project_dir: Path | None = None,
        run_name: str | None = None,
    ) -> dict:
        """
        作用：
        构建图片、视频、摄像头三种场景共用的 YOLO 推理参数。

        参数：
        - conf: 置信度阈值。
        - imgsz: 推理尺寸。
        - show: 是否显示识别窗口。
        - save: 是否保存识别结果。
        - project_dir: 结果输出根目录。
        - run_name: 本次输出子目录名。

        返回：
        - dict: 可直接传给 model.predict 的参数字典。
        """

        predict_kwargs = {
            "conf": conf,
            "show": show,
            "save": save,
            "verbose": False,
        }

        # 这些参数只有在用户显式传入时才覆盖默认值，避免无意义地改变 ultralytics 的原生行为。
        if imgsz is not None and imgsz > 0:
            predict_kwargs["imgsz"] = imgsz
        if self.device:
            predict_kwargs["device"] = self.device
        if project_dir is not None:
            predict_kwargs["project"] = str(project_dir)
        if run_name:
            predict_kwargs["name"] = run_name
            predict_kwargs["exist_ok"] = True

        return predict_kwargs

    def _resolve_save_dir(self, config: InferenceConfig) -> Path | None:
        """
        作用：
        根据当前配置推导 YOLO 结果保存目录，便于在日志里提示用户输出位置。

        参数：
        - config: 本次推理配置。

        返回：
        - Path | None: 若启用了保存则返回结果目录，否则返回 None。
        """

        if not config.save:
            return None

        # 如果上层没有传 run_name，就按当前时间自动生成，确保不同任务输出目录互不覆盖。
        run_name = config.run_name or build_default_run_name(config.mode)
        return config.project_dir / run_name


def build_parser() -> argparse.ArgumentParser:
    """
    作用：
    构建命令行参数入口，既支持完全交互式启动，也支持被其他脚本直接无界面调用。

    返回：
    - argparse.ArgumentParser: 配置完成的参数解析器。
    """

    parser = argparse.ArgumentParser(description="海参检测交互式推理脚本")
    parser.add_argument("--weight", default="", help="手动指定权重路径；不传时自动搜索最新权重。")
    parser.add_argument("--mode", choices=["image", "video", "camera"], default="", help="手动指定识别模式。")
    parser.add_argument("--source", default="", help="图片或视频路径；当 mode 为 image/video 时使用。")
    parser.add_argument("--camera", type=int, default=None, help="摄像头索引；当 mode 为 camera 时使用。")
    parser.add_argument(
        "--camera-resolution",
        default="",
        help='摄像头分辨率，例如 "1920x1080"；不传时可在交互界面里选择。',
    )
    parser.add_argument("--conf", type=float, default=0.25, help="置信度阈值，默认 0.25。")
    parser.add_argument("--imgsz", type=int, default=0, help="推理尺寸；传 0 表示沿用默认设置。")
    parser.add_argument("--device", default="", help='推理设备，例如 "cpu"、"0"。')
    parser.add_argument("--project", default="", help="识别结果输出目录，默认写入 runs/predict。")
    parser.add_argument("--run-name", default="", help="识别结果子目录名；不传时按时间自动生成。")
    parser.add_argument("--noshow", action="store_true", help="不弹出识别显示窗口。")
    parser.add_argument("--nosave", action="store_true", help="不保存识别结果。")
    parser.add_argument("--no-gui", action="store_true", help="禁用 Tk 图形交互，强制使用命令行选择。")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="禁用交互式补全。启用后必须把缺失参数全部通过命令行传完整。",
    )
    parser.add_argument("--max-camera-probe", type=int, default=6, help="自动探测摄像头时扫描的最大索引数。")
    return parser


def resolve_path(path_text: str | Path) -> Path:
    """
    作用：
    将相对路径统一解析成绝对路径，避免从其他工作目录运行时定位失败。

    参数：
    - path_text: 输入的路径文本或 Path 对象。

    返回：
    - Path: 解析后的绝对路径。
    """

    raw_path = Path(path_text)
    if raw_path.is_absolute():
        return raw_path.resolve()

    # 命令行从仓库根目录启动时，用户更常传“相对当前工作目录”的路径。
    # 这里优先尊重用户当前终端位置；只有找不到时再回退到脚本目录，兼容双击脚本启动场景。
    cwd_relative_path = raw_path.resolve()
    if cwd_relative_path.exists():
        return cwd_relative_path

    return (SCRIPT_DIR / raw_path).resolve()


def resolve_existing_path(path_text: str | Path) -> Path:
    """
    作用：
    解析路径并强制检查文件是否存在，避免模型加载或媒体读取阶段才暴露错误。

    参数：
    - path_text: 输入路径。

    返回：
    - Path: 已确认存在的绝对路径。
    """

    resolved_path = resolve_path(path_text)
    if not resolved_path.exists():
        raise FileNotFoundError(f"路径不存在：{resolved_path}")
    return resolved_path


def resolve_existing_file(path_text: str | Path) -> Path:
    """
    作用：
    解析路径并检查它确实是文件，避免把目录误当成权重或媒体文件传入后续流程。

    参数：
    - path_text: 输入路径。

    返回：
    - Path: 已确认存在且为文件的绝对路径。
    """

    resolved_path = resolve_existing_path(path_text)
    if not resolved_path.is_file():
        raise FileNotFoundError(f"目标不是文件：{resolved_path}")
    return resolved_path


def ensure_mode_file_source(mode: InferenceMode, source: Path | int) -> Path:
    """
    作用：
    校验图片/视频模式下的 source 必须是文件路径，避免模式和输入源类型不匹配。

    参数：
    - mode: 当前识别模式。
    - source: 当前输入源。

    返回：
    - Path: 已确认有效的文件路径。
    """

    if isinstance(source, int):
        raise ValueError(f"{mode} 模式要求 source 为文件路径，当前却收到摄像头索引。")
    return resolve_existing_file(source)


def list_weight_candidates(search_root: Path = SCRIPT_DIR) -> list[Path]:
    """
    作用：
    搜索工程内常见位置的权重文件，并按最近修改时间从新到旧排序。

    参数：
    - search_root: 搜索根目录，默认从当前识别脚本目录开始。

    返回：
    - list[Path]: 已排序的权重文件列表。
    """

    candidate_paths: set[Path] = set()

    # 训练输出目录优先纳入搜索，因为“最新权重”通常就在这里产生。
    for weight_path in search_root.glob("runs/**/weights/*.pt"):
        if weight_path.is_file():
            candidate_paths.add(weight_path.resolve())

    # 根目录下的预训练权重也保留，方便用户回退到基础模型做对比。
    for weight_path in search_root.glob("*.pt"):
        if weight_path.is_file():
            candidate_paths.add(weight_path.resolve())

    return sorted(candidate_paths, key=lambda path: path.stat().st_mtime, reverse=True)


def find_latest_weight(search_root: Path = SCRIPT_DIR) -> Path:
    """
    作用：
    返回当前工程里最近修改的权重文件。

    参数：
    - search_root: 权重搜索根目录。

    返回：
    - Path: 最新权重路径。
    """

    candidate_paths = list_weight_candidates(search_root)
    if not candidate_paths:
        raise FileNotFoundError(f"未在 {search_root} 下找到任何 .pt 权重文件。")
    return candidate_paths[0]


def build_default_run_name(mode: InferenceMode) -> str:
    """
    作用：
    为本次推理任务生成稳定且可区分的默认输出目录名。

    参数：
    - mode: 当前识别模式。

    返回：
    - str: 形如 image_20260414_182530 的目录名。
    """

    return f"{mode}_{datetime.now():%Y%m%d_%H%M%S}"


def parse_camera_resolution(resolution_text: str) -> tuple[int, int] | None:
    """
    作用：
    解析命令行或交互输入的分辨率文本。

    参数：
    - resolution_text: 形如 1920x1080 的分辨率字符串，也支持 default。

    返回：
    - tuple[int, int] | None: 返回宽高元组；若表示默认分辨率则返回 None。
    """

    normalized_text = resolution_text.strip().lower().replace(" ", "")
    if not normalized_text or normalized_text == "default":
        return None

    if "x" not in normalized_text:
        raise ValueError(f"分辨率格式错误：{resolution_text}，正确格式应为 宽x高，例如 1280x720。")

    width_text, height_text = normalized_text.split("x", maxsplit=1)
    width = int(width_text)
    height = int(height_text)

    if width <= 0 or height <= 0:
        raise ValueError(f"分辨率必须为正整数，当前输入：{resolution_text}")

    return width, height


def create_tk_root() -> tk.Tk | None:
    """
    作用：
    创建一个隐藏的 Tk 根窗口，供文件选择框或弹窗使用。

    返回：
    - tk.Tk | None: 创建成功则返回根窗口，失败则返回 None。
    """

    if tk is None:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def select_weight_path_interactive(use_gui: bool = True, search_root: Path = SCRIPT_DIR) -> Path:
    """
    作用：
    自动定位最新权重，并保留手动切换权重文件的交互入口。

    参数：
    - use_gui: 是否优先使用图形界面。
    - search_root: 权重搜索根目录。

    返回：
    - Path: 用户最终确认的权重路径。
    """

    latest_weight = find_latest_weight(search_root)

    # 图形界面优先提供“直接用最新权重 / 手动另选文件”两步式交互。
    if use_gui and tk is not None and messagebox is not None and filedialog is not None:
        root = None
        try:
            root = create_tk_root()
            use_latest = messagebox.askyesno(
                "权重选择",
                f"已自动定位到最新权重：\n{latest_weight}\n\n点击“是”直接使用；点击“否”手动选择其他权重。",
                parent=root,
            )
            if use_latest:
                return latest_weight

            selected_path = filedialog.askopenfilename(
                title="请选择 YOLO 权重文件",
                initialdir=str(latest_weight.parent),
                filetypes=[("PyTorch 权重", "*.pt"), ("所有文件", "*.*")],
            )
            if selected_path:
                return resolve_existing_file(selected_path)
        except Exception:
            # 图形界面失败时自动退回命令行，不让整个脚本卡死在 GUI 初始化阶段。
            pass
        finally:
            if root is not None:
                root.destroy()

    print(f"\n已自动定位到最新权重：{latest_weight}")
    custom_choice = input("直接使用该权重请按回车；输入 y 后手动指定其他 .pt 文件：").strip().lower()
    if custom_choice != "y":
        return latest_weight

    while True:
        custom_path = input("请输入权重文件路径：").strip()
        if not custom_path:
            print("未输入路径，继续使用最新权重。")
            return latest_weight
        try:
            return resolve_existing_file(custom_path)
        except FileNotFoundError as error:
            print(error)


def select_mode_interactive(use_gui: bool = True) -> InferenceMode:
    """
    作用：
    交互式选择识别模式。

    参数：
    - use_gui: 是否优先使用图形界面。

    返回：
    - InferenceMode: 用户选择的模式。
    """

    mode_options = [
        ("image", "图片模式"),
        ("video", "视频模式"),
        ("camera", "摄像头模式"),
    ]

    selected_mode = choose_option_interactive(
        title="识别模式选择",
        prompt="请选择要执行的识别模式：",
        options=mode_options,
        default_value="image",
        use_gui=use_gui,
    )
    return selected_mode  # type: ignore[return-value]


def select_media_path_interactive(mode: InferenceMode, use_gui: bool = True) -> Path:
    """
    作用：
    为图片或视频模式交互选择输入文件路径。

    参数：
    - mode: 当前识别模式，只能是 image 或 video。
    - use_gui: 是否优先使用图形界面。

    返回：
    - Path: 用户选择的媒体文件路径。
    """

    if mode not in {"image", "video"}:
        raise ValueError("只有图片和视频模式才需要选择文件路径。")

    filetypes = [("所有文件", "*.*")]
    title = "请选择输入文件"
    if mode == "image":
        filetypes = [("图片文件", "*.jpg *.jpeg *.png *.bmp *.webp"), ("所有文件", "*.*")]
        title = "请选择待识别图片"
    elif mode == "video":
        filetypes = [("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.m4v"), ("所有文件", "*.*")]
        title = "请选择待识别视频"

    if use_gui and tk is not None and filedialog is not None:
        root = None
        try:
            root = create_tk_root()
            selected_path = filedialog.askopenfilename(
                title=title,
                initialdir=str(SCRIPT_DIR),
                filetypes=filetypes,
            )
            if selected_path:
                return resolve_existing_file(selected_path)
        except Exception:
            pass
        finally:
            if root is not None:
                root.destroy()

    while True:
        custom_path = input(f"{title}，请输入文件路径：").strip()
        try:
            return resolve_existing_file(custom_path)
        except FileNotFoundError as error:
            print(error)


def probe_camera_indices(max_camera_probe: int = 6) -> list[CameraInfo]:
    """
    作用：
    预扫描本机可用摄像头，便于在交互界面里让用户明确选择设备索引。

    参数：
    - max_camera_probe: 最大探测索引数，会按 0 到该值前一位依次扫描。

    返回：
    - list[CameraInfo]: 当前可用摄像头列表。
    """

    camera_infos: list[CameraInfo] = []
    backend_flag = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY

    for index in range(max_camera_probe):
        capture = cv2.VideoCapture(index, backend_flag)
        if not capture.isOpened():
            capture.release()
            continue

        # 这里主动抓一帧，目的是过滤掉“索引存在但无法真正读帧”的伪可用设备。
        read_ok, _ = capture.read()
        if not read_ok:
            capture.release()
            continue

        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        backend_name = "unknown"
        if hasattr(capture, "getBackendName"):
            try:
                backend_name = capture.getBackendName()
            except Exception:
                backend_name = "unknown"

        camera_infos.append(
            CameraInfo(
                index=index,
                width=width,
                height=height,
                backend_name=backend_name,
            )
        )
        capture.release()

    return camera_infos


def select_camera_index_interactive(camera_infos: list[CameraInfo], use_gui: bool = True) -> int:
    """
    作用：
    在已经探测到的摄像头列表中交互选择目标设备。

    参数：
    - camera_infos: 当前可用摄像头列表。
    - use_gui: 是否优先使用图形界面。

    返回：
    - int: 选中的摄像头索引。
    """

    if not camera_infos:
        raise RuntimeError("未探测到可用摄像头，请检查设备连接或调大 --max-camera-probe。")

    option_list = [(str(camera.index), camera.display_name) for camera in camera_infos]
    selected_index = choose_option_interactive(
        title="摄像头选择",
        prompt="请选择要使用的摄像头：",
        options=option_list,
        default_value=str(camera_infos[0].index),
        use_gui=use_gui,
    )
    return int(selected_index)


def select_camera_resolution_interactive(use_gui: bool = True) -> tuple[int, int] | None:
    """
    作用：
    为摄像头模式交互选择目标分辨率，便于针对 USB 相机直接切换常见档位。

    参数：
    - use_gui: 是否优先使用图形界面。

    返回：
    - tuple[int, int] | None: 返回选中的宽高；若保持默认则返回 None。
    """

    selected_value = choose_option_interactive(
        title="摄像头分辨率选择",
        prompt="请选择摄像头工作分辨率：",
        options=CAMERA_RESOLUTION_PRESETS,
        default_value="default",
        use_gui=use_gui,
    )

    if selected_value == "custom":
        return ask_custom_resolution_interactive(use_gui=use_gui)
    return parse_camera_resolution(selected_value)


def ask_custom_resolution_interactive(use_gui: bool = True) -> tuple[int, int]:
    """
    作用：
    在预设分辨率之外，允许用户手动输入自定义宽高。

    参数：
    - use_gui: 是否优先使用图形界面。

    返回：
    - tuple[int, int]: 用户自定义的宽高分辨率。
    """

    if use_gui and tk is not None and simpledialog is not None:
        root = None
        try:
            root = create_tk_root()
            resolution_text = simpledialog.askstring(
                title="自定义分辨率",
                prompt='请输入分辨率，格式示例：1920x1080',
                parent=root,
            )
            if resolution_text:
                parsed_resolution = parse_camera_resolution(resolution_text)
                if parsed_resolution is None:
                    raise ValueError("自定义分辨率不能为空。")
                return parsed_resolution
        except Exception:
            pass
        finally:
            if root is not None:
                root.destroy()

    while True:
        resolution_text = input('请输入自定义分辨率，格式示例：1920x1080：').strip()
        try:
            parsed_resolution = parse_camera_resolution(resolution_text)
            if parsed_resolution is None:
                print("自定义分辨率不能为空。")
                continue
            return parsed_resolution
        except ValueError as error:
            print(error)


def choose_option_interactive(
    title: str,
    prompt: str,
    options: list[tuple[str, str]],
    default_value: str,
    use_gui: bool = True,
) -> str:
    """
    作用：
    提供一个通用的单选交互入口，供模式选择和摄像头选择复用。

    参数：
    - title: 弹窗或命令行标题。
    - prompt: 给用户的选择提示。
    - options: 候选项列表，格式为 (实际值, 展示文本)。
    - default_value: 默认选项的实际值。
    - use_gui: 是否优先使用图形界面。

    返回：
    - str: 用户最终选中的实际值。
    """

    if not options:
        raise ValueError(f"{title} 失败：候选项为空。")

    if use_gui and tk is not None and ttk is not None:
        try:
            return choose_option_gui(title, prompt, options, default_value)
        except Exception:
            # 图形界面失败时，统一降级为命令行选择，避免脚本中断。
            pass

    return choose_option_cli(title, prompt, options, default_value)


def choose_option_gui(
    title: str,
    prompt: str,
    options: list[tuple[str, str]],
    default_value: str,
) -> str:
    """
    作用：
    用 Tk 窗口完成单选项交互。

    参数：
    - title: 窗口标题。
    - prompt: 窗口提示文本。
    - options: 候选项列表。
    - default_value: 默认值。

    返回：
    - str: 用户选中的值。
    """

    if tk is None or ttk is None:
        raise RuntimeError("当前环境不可用 Tk 图形界面。")

    selected_value = {"value": default_value}
    window = tk.Tk()
    window.title(title)
    window.resizable(False, False)
    window.attributes("-topmost", True)
    window.geometry("+500+250")

    ttk.Label(window, text=prompt, padding=(18, 14, 18, 8)).pack(anchor="w")

    radio_value = tk.StringVar(value=default_value)
    for option_value, option_label in options:
        ttk.Radiobutton(
            window,
            text=option_label,
            value=option_value,
            variable=radio_value,
            padding=(18, 4, 18, 4),
        ).pack(anchor="w")

    button_frame = ttk.Frame(window, padding=(18, 12, 18, 16))
    button_frame.pack(fill="x")

    def confirm_selection() -> None:
        """确认按钮回调：保存当前选项并关闭窗口。"""

        selected_value["value"] = radio_value.get()
        window.destroy()

    def cancel_selection() -> None:
        """取消按钮回调：沿用默认值，避免误关闭窗口后出现空结果。"""

        selected_value["value"] = default_value
        window.destroy()

    ttk.Button(button_frame, text="确定", command=confirm_selection).pack(side="left", padx=(0, 10))
    ttk.Button(button_frame, text="取消", command=cancel_selection).pack(side="left")

    window.protocol("WM_DELETE_WINDOW", cancel_selection)
    window.mainloop()
    return selected_value["value"]


def choose_option_cli(
    title: str,
    prompt: str,
    options: list[tuple[str, str]],
    default_value: str,
) -> str:
    """
    作用：
    在没有 GUI 时用命令行完成单选项交互。

    参数：
    - title: 命令行标题。
    - prompt: 选择提示。
    - options: 候选项列表。
    - default_value: 默认值。

    返回：
    - str: 用户选中的值。
    """

    print(f"\n{title}")
    print(prompt)
    for index, (_, label) in enumerate(options, start=1):
        print(f"  {index}. {label}")

    option_value_to_index = {value: index for index, (value, _) in enumerate(options, start=1)}
    default_index = option_value_to_index[default_value]

    while True:
        user_text = input(f"请输入序号，直接回车默认选择第 {default_index} 项：").strip()
        if not user_text:
            return default_value
        if user_text.isdigit():
            selected_index = int(user_text)
            if 1 <= selected_index <= len(options):
                return options[selected_index - 1][0]
        print("输入无效，请重新输入。")


def build_config_from_args(args: argparse.Namespace) -> InferenceConfig:
    """
    作用：
    将命令行参数和交互式补全整合成最终推理配置。

    参数：
    - args: 参数解析后的命名空间对象。

    返回：
    - InferenceConfig: 可直接执行的推理配置。
    """

    use_gui = not args.no_gui

    # 权重路径优先使用命令行参数；未指定时才进入“自动定位 + 可选手动切换”的交互流程。
    if args.weight:
        weight_path = resolve_existing_file(args.weight)
    elif args.no_prompt:
        weight_path = find_latest_weight(SCRIPT_DIR)
    else:
        weight_path = select_weight_path_interactive(use_gui=use_gui, search_root=SCRIPT_DIR)

    # 模式选择支持命令行直传，也支持交互式选择，方便单次演示和后续脚本调用两种场景共存。
    if args.mode:
        mode: InferenceMode = args.mode
    elif args.no_prompt:
        raise ValueError("启用 --no-prompt 时必须显式传入 --mode。")
    else:
        mode = select_mode_interactive(use_gui=use_gui)

    if mode in {"image", "video"}:
        if args.source:
            source: Path | int = resolve_existing_file(args.source)
        elif args.no_prompt:
            raise ValueError(f"启用 --no-prompt 且 mode={mode} 时，必须显式传入 --source。")
        else:
            source = select_media_path_interactive(mode=mode, use_gui=use_gui)
        camera_resolution = None
    else:
        if args.camera is not None:
            source = args.camera
        elif args.no_prompt:
            source = 0
        else:
            camera_infos = probe_camera_indices(args.max_camera_probe)
            source = select_camera_index_interactive(camera_infos, use_gui=use_gui)

        if args.camera_resolution:
            camera_resolution = parse_camera_resolution(args.camera_resolution)
        elif args.no_prompt:
            camera_resolution = None
        else:
            camera_resolution = select_camera_resolution_interactive(use_gui=use_gui)

    project_dir = DEFAULT_PREDICT_PROJECT_DIR
    if args.project:
        project_dir = resolve_path(args.project)

    run_name = args.run_name.strip() if args.run_name else build_default_run_name(mode)
    imgsz = args.imgsz if args.imgsz > 0 else None
    device = args.device.strip() if args.device.strip() else None

    return InferenceConfig(
        weight_path=weight_path,
        mode=mode,
        source=source,
        camera_resolution=camera_resolution,
        conf=args.conf,
        imgsz=imgsz,
        device=device,
        show=not args.noshow,
        save=not args.nosave,
        project_dir=project_dir,
        run_name=run_name,
    )


def print_config_summary(config: InferenceConfig) -> None:
    """
    作用：
    在执行前把当前推理配置打印出来，便于排查“到底用了哪个权重、哪个输入源”的问题。

    参数：
    - config: 即将执行的推理配置。
    """

    print("\n当前推理配置：")
    print(f"  权重文件：{config.weight_path}")
    print(f"  识别模式：{config.mode}")
    print(f"  输入源：{config.source_text()}")
    if config.mode == "camera":
        if config.camera_resolution is None:
            print("  摄像头分辨率：保持设备默认")
        else:
            print(f"  摄像头分辨率：{config.camera_resolution[0]}x{config.camera_resolution[1]}")
    print(f"  置信度阈值：{config.conf}")
    print(f"  推理尺寸：{config.imgsz if config.imgsz else '默认'}")
    print(f"  推理设备：{config.device if config.device else '自动'}")
    print(f"  显示窗口：{'开启' if config.show else '关闭'}")
    print(f"  保存结果：{'开启' if config.save else '关闭'}")
    if config.save:
        print(f"  输出目录：{config.project_dir / (config.run_name or build_default_run_name(config.mode))}")


def print_summary(summary: InferenceSummary) -> None:
    """
    作用：
    输出本次推理任务的统计结果。

    参数：
    - summary: 推理完成后的摘要信息。
    """

    print("\n推理完成：")
    print(f"  模式：{summary.mode}")
    print(f"  权重：{summary.weight_path}")
    print(f"  输入源：{summary.source_text}")
    print(f"  处理帧数：{summary.frame_count}")
    print(f"  检测框总数：{summary.detection_count}")
    if summary.actual_resolution is not None:
        print(f"  实际分辨率：{summary.actual_resolution[0]}x{summary.actual_resolution[1]}")
    if summary.save_dir is not None:
        print(f"  结果目录：{summary.save_dir}")


def main() -> None:
    """
    作用：
    脚本主入口，负责解析参数、补全交互信息并执行推理。
    """

    parser = build_parser()
    args = parser.parse_args()

    config = build_config_from_args(args)
    print_config_summary(config)

    inferencer = Yolo26Inferencer(weight_path=config.weight_path, device=config.device)
    summary = inferencer.run(config)
    print_summary(summary)


if __name__ == "__main__":
    main()
