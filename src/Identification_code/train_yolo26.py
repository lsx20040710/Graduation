"""
文件作用：
用于海参目标检测模型训练，面向当前陆上验证阶段的小样本单类别数据集。

主要内容：
1. 解析并检查 data.yaml，尽早发现路径或标注缺失问题；
2. 根据当前样本规模自动选择更合适的预训练模型；
3. 统一训练输出目录，保持与现有识别目录结构兼容；
4. 输出数据集规模评估，方便后续判断是否需要继续补数据。
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Windows 环境下，PyTorch、NumPy、OpenCV 等库组合有时会重复加载 OpenMP 运行时。
# 这里提前打开兼容开关，避免脚本还没进入数据检查就直接因为重复初始化报错退出。
if os.name == "nt":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import torch
import yaml
from ultralytics import YOLO


# 当前脚本所在目录，后续所有相对路径都以这里为基准，避免从别的工作目录启动时找错文件。
SCRIPT_DIR = Path(__file__).resolve().parent

# 保持和现有推理脚本的默认搜索路径兼容，避免训练完后还要手动改推理入口。
DEFAULT_RUN_NAME = "yolo26_runs"

# 统一维护支持的图片后缀，后续统计数据集时按这个集合筛选文件。
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}

# 当前阶段只做陆上验证，下面这组规模建议按“单类别海参检测”来估算。
# 这里强调的是“相互独立的样本”，不是同一段视频里连续抽出的高度相似帧。
LAND_MINIMUM_IMAGE_TARGET = (200, 300)
LAND_MINIMUM_BOX_TARGET = (600, 1000)
LAND_STABLE_IMAGE_TARGET = (500, 800)
LAND_STABLE_BOX_TARGET = (1500, 3000)


@dataclass
class SplitStats:
    """
    作用：
    记录单个数据划分的统计信息，便于后续统一打印和做训练参数判断。
    """

    image_count: int
    label_count: int
    negative_image_count: int
    box_count: int
    average_box_area: float
    min_box_area: float
    max_box_area: float
    dominant_name_prefix: str
    dominant_name_prefix_ratio: float


@dataclass
class DatasetStats:
    """
    作用：
    汇总整个数据集的关键规模信息，用于模型选择和训练风险提示。
    """

    data_yaml_path: Path
    dataset_root: Path
    class_count: int
    class_names: list[str]
    train_stats: SplitStats
    val_stats: SplitStats

    @property
    def total_images(self) -> int:
        """返回训练集和验证集的总图片数。"""
        return self.train_stats.image_count + self.val_stats.image_count

    @property
    def total_boxes(self) -> int:
        """返回训练集和验证集的总标注框数量。"""
        return self.train_stats.box_count + self.val_stats.box_count


def build_parser() -> argparse.ArgumentParser:
    """
    作用：
    构建命令行参数，方便后续在不改代码的情况下切换模型或训练轮数。

    返回：
    - argparse.ArgumentParser: 已配置好的参数解析器。
    """

    parser = argparse.ArgumentParser(description="海参检测模型训练脚本")
    parser.add_argument(
        "--data",
        default="data.yaml",
        help="数据集配置文件路径，默认读取当前目录下的 data.yaml。",
    )
    parser.add_argument(
        "--model",
        default="",
        help="手动指定预训练权重；不传时由脚本根据当前数据规模自动选择。",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=150,
        help="训练轮数上限。小样本场景建议给足轮数，再用早停控制过拟合。",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=0,
        help="输入图像尺寸；传 0 表示由脚本按目标尺度自动选择。",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="批大小；传 0 表示由脚本根据设备自动设置。",
    )
    parser.add_argument(
        "--device",
        default="",
        help="训练设备，例如 0、0,1 或 cpu；不传时自动选择。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="数据加载线程数。Windows 下过高反而容易拖慢启动，默认 4。",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=30,
        help="早停耐心值，验证集指标长期不提升时提前结束训练。",
    )
    parser.add_argument(
        "--run-name",
        default=DEFAULT_RUN_NAME,
        help="本次实验名称，会写入 runs/detect/<run-name>。",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只检查数据集与训练配置，不真正启动训练。",
    )
    return parser


def resolve_path(path_text: str) -> Path:
    """
    作用：
    将命令行中的路径统一解析成绝对路径，避免从其他目录运行时路径失效。

    参数：
    - path_text: 用户输入的路径字符串。

    返回：
    - Path: 解析后的绝对路径对象。
    """

    raw_path = Path(path_text)
    if raw_path.is_absolute():
        return raw_path
    return (SCRIPT_DIR / raw_path).resolve()


def resolve_dataset_entry(base_dir: Path, entry: Any) -> Path:
    """
    作用：
    解析 data.yaml 中的数据集路径项。

    参数：
    - base_dir: data.yaml 所在目录或数据集根目录。
    - entry: data.yaml 里的路径配置，可能是相对路径也可能是绝对路径。

    返回：
    - Path: 解析后的绝对路径。
    """

    entry_path = Path(str(entry))
    if entry_path.is_absolute():
        return entry_path
    return (base_dir / entry_path).resolve()


def parse_box_area(label_path: Path) -> list[float]:
    """
    作用：
    读取 YOLO 标注文件中的归一化框面积，用于判断目标是否偏小。

    参数：
    - label_path: 单张图片对应的标签文件路径。

    返回：
    - list[float]: 当前标签文件内所有目标框的相对面积列表。
    """

    areas: list[float] = []
    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 5:
            raise ValueError(f"标签格式错误，文件 {label_path} 中存在不完整行：{line}")

        box_width = float(parts[3])
        box_height = float(parts[4])
        areas.append(box_width * box_height)

    return areas


def extract_name_prefix(file_path: Path) -> str:
    """
    作用：
    提取文件名中的稳定前缀，用于粗略判断数据是否主要来自同一段连续抽帧。

    参数：
    - file_path: 图片文件路径。

    返回：
    - str: 归一化后的文件名前缀；如果无法拆分，则返回完整 stem。
    """

    stem = file_path.stem
    parts = stem.split("_")

    # 常见的视频抽帧文件名通常以数字序号结尾，这里去掉尾部编号，只保留前缀。
    if len(parts) >= 2 and parts[-1].isdigit():
        return "_".join(parts[:-1])

    return stem


def collect_split_stats(image_dir: Path, label_dir: Path) -> SplitStats:
    """
    作用：
    统计单个数据划分中的图片数量、标签数量和目标框面积分布。

    参数：
    - image_dir: 当前划分的图片目录。
    - label_dir: 当前划分的标签目录。

    返回：
    - SplitStats: 当前划分的统计结果。
    """

    image_paths = sorted([path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES])
    label_paths = sorted(label_dir.glob("*.txt"))

    box_areas: list[float] = []
    positive_label_count = 0
    for label_path in label_paths:
        current_box_areas = parse_box_area(label_path)
        box_areas.extend(current_box_areas)

        # 空标签文件在 YOLO 数据集中通常表示“当前图片没有目标”，
        # 这类样本应该算负样本，不能简单因为存在 txt 文件就当成正样本。
        if current_box_areas:
            positive_label_count += 1

    # 数据还很少时，直接给出 0 值比抛异常更实用，后续由统一检查逻辑判断是否允许训练。
    average_box_area = sum(box_areas) / len(box_areas) if box_areas else 0.0
    min_box_area = min(box_areas) if box_areas else 0.0
    max_box_area = max(box_areas) if box_areas else 0.0
    negative_image_count = max(len(image_paths) - positive_label_count, 0)

    # 如果绝大多数文件都共享同一前缀，基本可以判断是同一来源的连续抽帧，独立样本量会被高估。
    prefix_counter = Counter(extract_name_prefix(path) for path in image_paths)
    dominant_name_prefix = ""
    dominant_name_prefix_ratio = 0.0
    if prefix_counter and image_paths:
        dominant_name_prefix, dominant_count = prefix_counter.most_common(1)[0]
        dominant_name_prefix_ratio = dominant_count / len(image_paths)

    return SplitStats(
        image_count=len(image_paths),
        label_count=len(label_paths),
        negative_image_count=negative_image_count,
        box_count=len(box_areas),
        average_box_area=average_box_area,
        min_box_area=min_box_area,
        max_box_area=max_box_area,
        dominant_name_prefix=dominant_name_prefix,
        dominant_name_prefix_ratio=dominant_name_prefix_ratio,
    )


def load_dataset_stats(data_yaml_path: Path) -> DatasetStats:
    """
    作用：
    读取并检查 data.yaml，输出训练集和验证集的核心统计信息。

    参数：
    - data_yaml_path: data.yaml 的绝对路径。

    返回：
    - DatasetStats: 汇总后的数据集统计结果。
    """

    if not data_yaml_path.exists():
        raise FileNotFoundError(f"找不到数据配置文件：{data_yaml_path}")

    config = yaml.safe_load(data_yaml_path.read_text(encoding="utf-8")) or {}
    if "path" not in config or "train" not in config or "val" not in config:
        raise ValueError("data.yaml 必须至少包含 path、train、val 三个字段。")

    dataset_root = resolve_dataset_entry(data_yaml_path.parent, config["path"])
    train_image_dir = resolve_dataset_entry(dataset_root, config["train"])
    val_image_dir = resolve_dataset_entry(dataset_root, config["val"])

    # YOLO 目录通常是 images/train 对应 labels/train，这里按这一约定自动推导标签目录。
    train_label_dir = resolve_dataset_entry(dataset_root, str(config["train"]).replace("images", "labels", 1))
    val_label_dir = resolve_dataset_entry(dataset_root, str(config["val"]).replace("images", "labels", 1))

    for required_dir in [dataset_root, train_image_dir, val_image_dir, train_label_dir, val_label_dir]:
        if not required_dir.exists():
            raise FileNotFoundError(f"数据目录不存在：{required_dir}")

    names = config.get("names", [])
    if isinstance(names, dict):
        class_names = [str(names[index]) for index in sorted(names.keys())]
    else:
        class_names = [str(name) for name in names]

    class_count = int(config.get("nc", len(class_names)))
    if class_count != len(class_names):
        raise ValueError("data.yaml 中的 nc 与 names 数量不一致，请先修正数据配置。")

    train_stats = collect_split_stats(train_image_dir, train_label_dir)
    val_stats = collect_split_stats(val_image_dir, val_label_dir)

    if train_stats.image_count == 0 or val_stats.image_count == 0:
        raise ValueError("训练集或验证集为空，当前数据集不能启动训练。")
    if train_stats.box_count == 0:
        raise ValueError("训练集中没有有效标注框，当前数据集无法学习目标检测。")

    return DatasetStats(
        data_yaml_path=data_yaml_path,
        dataset_root=dataset_root,
        class_count=class_count,
        class_names=class_names,
        train_stats=train_stats,
        val_stats=val_stats,
    )


def choose_model_name(stats: DatasetStats, manual_model: str) -> tuple[str, str]:
    """
    作用：
    根据当前项目背景和样本规模选择默认预训练模型。

    参数：
    - stats: 数据集统计信息。
    - manual_model: 用户手动指定的权重名或路径。

    返回：
    - tuple[str, str]: 最终使用的模型权重名或路径，以及对应的选择理由。
    """

    if manual_model.strip():
        return manual_model.strip(), "已按命令行参数使用手动指定权重。"

    # 当前项目是单类别视觉伺服前端，现阶段只做陆上验证。
    # 模型选择优先顺序不是“绝对精度最大”，而是：
    # 1. 小样本下不过度放大过拟合；
    # 2. 后续接入控制闭环时仍保留实时余量；
    # 3. 数据真正变多之前，不盲目上大模型。
    is_highly_correlated_video_frames = stats.train_stats.dominant_name_prefix_ratio >= 0.6
    if stats.train_stats.image_count < 500 or stats.total_boxes < 1500 or is_highly_correlated_video_frames:
        return (
            "yolo26n.pt",
            "当前数据仍属于小样本阶段，且样本独立性偏弱，默认选择更轻的 YOLO26n 更稳妥。",
        )

    if stats.train_stats.image_count < 1500 or stats.total_boxes < 5000:
        return (
            "yolo26s.pt",
            "当前数据已超过演示级别，但还没达到可以稳定支撑中型模型的规模，优先使用 YOLO26s。",
        )

    # 对这个项目来说，m 版已经是较合理的上限。
    # l/x 更适合大数据和更充足算力，不适合作为当前控制系统的默认训练入口。
    return (
        "yolo26m.pt",
        "当前样本规模已经足够支撑更高上限，默认提升到 YOLO26m，但仍保留后续闭环部署的可控性。",
    )


def choose_image_size(stats: DatasetStats, manual_imgsz: int) -> int:
    """
    作用：
    根据目标尺度选择更合适的训练输入尺寸。

    参数：
    - stats: 数据集统计信息。
    - manual_imgsz: 用户手动指定的图像尺寸。

    返回：
    - int: 最终使用的训练输入尺寸。
    """

    if manual_imgsz > 0:
        return manual_imgsz

    # 当前标注框平均面积约为图像的 1% 左右，最小框更小。
    # 为了让末端视觉伺服后续拿到更稳定的目标中心，默认比 640 稍大一些。
    if stats.train_stats.min_box_area < 0.0035:
        return 832

    return 640


def choose_device(manual_device: str) -> str | int:
    """
    作用：
    统一设备选择逻辑，优先使用 GPU，没有 GPU 再退回 CPU。

    参数：
    - manual_device: 用户传入的设备参数。

    返回：
    - str | int: Ultralytics 可识别的设备标识。
    """

    if manual_device.strip():
        value = manual_device.strip()
        return int(value) if value.isdigit() else value

    return 0 if torch.cuda.is_available() else "cpu"


def choose_batch_size(device: str | int, manual_batch: int) -> int:
    """
    作用：
    根据设备类型给出更稳妥的默认批大小，减少首次训练时显存不足的概率。

    参数：
    - device: 最终使用的训练设备。
    - manual_batch: 用户手动指定的批大小。

    返回：
    - int: 最终使用的批大小。
    """

    if manual_batch > 0:
        return manual_batch

    # CPU 训练本来就慢，批量过大会进一步拖慢；GPU 下给一个中等保守值。
    if device == "cpu":
        return 4
    return 8


def print_environment(device: str | int) -> None:
    """
    作用：
    打印当前硬件环境，方便定位训练慢或设备识别失败的问题。

    参数：
    - device: 当前选择的训练设备。
    """

    print("========== 训练环境 ==========")
    print(f"PyTorch CUDA 可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"当前 GPU: {torch.cuda.get_device_name(0)}")
    print(f"训练设备: {device}")
    print("==============================")


def print_dataset_summary(stats: DatasetStats) -> None:
    """
    作用：
    打印数据集概要和风险提示，帮助判断当前样本量是否足以支撑稳定识别。

    参数：
    - stats: 数据集统计信息。
    """

    print("========== 数据集检查 ==========")
    print(f"data.yaml: {stats.data_yaml_path}")
    print(f"数据集根目录: {stats.dataset_root}")
    print(f"类别数: {stats.class_count}")
    print(f"类别名: {stats.class_names}")
    print(
        "训练集: "
        f"{stats.train_stats.image_count} 张图, "
        f"{stats.train_stats.label_count} 个标签文件, "
        f"{stats.train_stats.box_count} 个目标框, "
        f"{stats.train_stats.negative_image_count} 张负样本"
    )
    print(
        "验证集: "
        f"{stats.val_stats.image_count} 张图, "
        f"{stats.val_stats.label_count} 个标签文件, "
        f"{stats.val_stats.box_count} 个目标框, "
        f"{stats.val_stats.negative_image_count} 张负样本"
    )
    print(
        "训练集目标框面积占比: "
        f"均值 {stats.train_stats.average_box_area:.4f}, "
        f"最小 {stats.train_stats.min_box_area:.4f}, "
        f"最大 {stats.train_stats.max_box_area:.4f}"
    )
    print(
        "训练集主文件名前缀占比: "
        f"{stats.train_stats.dominant_name_prefix or '无'} "
        f"({stats.train_stats.dominant_name_prefix_ratio:.0%})"
    )
    print("================================")

    # 这里直接给出小样本风险，不等到训练结果不好时再追问题。
    if stats.train_stats.image_count < 100:
        print("提示：当前训练图像少于 100 张，结果更像是可跑通验证，不适合直接认定为稳定识别。")
    if stats.total_boxes < 500:
        print("提示：当前总目标框数量偏少，模型容易记住背景或拍摄批次特征。")
    if stats.train_stats.negative_image_count == 0:
        print("提示：训练集中没有无目标负样本，后续陆上验证时更容易把背景或杂物误判成海参。")
    if stats.train_stats.dominant_name_prefix_ratio >= 0.7:
        print(
            "提示：训练集大部分文件名共享同一前缀，疑似同一段视频连续抽帧，"
            "表面样本数会高于真实独立样本数。"
        )

    minimum_image_low, minimum_image_high = LAND_MINIMUM_IMAGE_TARGET
    minimum_box_low, minimum_box_high = LAND_MINIMUM_BOX_TARGET
    stable_image_low, stable_image_high = LAND_STABLE_IMAGE_TARGET
    stable_box_low, stable_box_high = LAND_STABLE_BOX_TARGET
    print(
        "陆上验证数据建议: "
        f"可跑通版本约需 {minimum_image_low}-{minimum_image_high} 张独立图片、"
        f"{minimum_box_low}-{minimum_box_high} 个目标框；"
        f"较稳定版本建议 {stable_image_low}-{stable_image_high} 张独立图片、"
        f"{stable_box_low}-{stable_box_high} 个目标框。"
    )
    print(
        "当前进度估算: "
        f"图片达到稳定下限的 {stats.total_images / stable_image_low:.0%}，"
        f"目标框达到稳定下限的 {stats.total_boxes / stable_box_low:.0%}。"
    )


def build_train_kwargs(args: argparse.Namespace, stats: DatasetStats) -> dict[str, Any]:
    """
    作用：
    统一整理训练参数，避免主流程里散落大量配置细节。

    参数：
    - args: 命令行参数对象。
    - stats: 数据集统计信息。

    返回：
    - dict[str, Any]: 可直接传给 model.train 的训练参数。
    """

    model_name, model_reason = choose_model_name(stats, args.model)
    device = choose_device(args.device)
    imgsz = choose_image_size(stats, args.imgsz)
    batch = choose_batch_size(device, args.batch)

    return {
        "model_name": model_name,
        "model_reason": model_reason,
        "device": device,
        "train_kwargs": {
            "data": str(stats.data_yaml_path),
            "epochs": args.epochs,
            "imgsz": imgsz,
            "batch": batch,
            "device": device,
            "workers": args.workers,
            "optimizer": "auto",
            "amp": device != "cpu",
            "patience": args.patience,
            "project": str(SCRIPT_DIR / "runs" / "detect"),
            "name": args.run_name,
            "seed": 42,
            "deterministic": True,
            "pretrained": True,
            "close_mosaic": 10,
            "plots": True,
        },
    }


def main() -> None:
    """
    作用：
    脚本主入口，负责串起环境检查、数据检查和训练启动。
    """

    args = build_parser().parse_args()
    data_yaml_path = resolve_path(args.data)
    stats = load_dataset_stats(data_yaml_path)
    training_setup = build_train_kwargs(args, stats)

    print_environment(training_setup["device"])
    print_dataset_summary(stats)

    print("========== 训练配置 ==========")
    print(f"预训练权重: {training_setup['model_name']}")
    print(f"选型说明: {training_setup['model_reason']}")
    print(f"训练轮数上限: {training_setup['train_kwargs']['epochs']}")
    print(f"输入尺寸: {training_setup['train_kwargs']['imgsz']}")
    print(f"批大小: {training_setup['train_kwargs']['batch']}")
    print(f"输出目录: {training_setup['train_kwargs']['project']}")
    print(f"实验名称: {training_setup['train_kwargs']['name']}")
    print("==============================")

    # 官方模型名在本地不存在时，Ultralytics 会自动拉取对应预训练权重。
    # 这里显式提醒一次，避免用户误以为仓库里必须手动放置 .pt 文件。
    if training_setup["model_name"].startswith("yolo26") and not Path(training_setup["model_name"]).exists():
        print("说明：当前未检测到本地同名权重，Ultralytics 将在加载时自动下载官方预训练模型。")

    if args.check_only:
        print("已完成检查，未启动训练。")
        return

    # 先创建模型对象，再启动训练，便于在权重名写错时第一时间报错。
    print(f">> 正在加载预训练权重: {training_setup['model_name']}")
    model = YOLO(training_setup["model_name"])

    print(">> 启动训练引擎...")
    model.train(**training_setup["train_kwargs"])
    print(">> 训练完成。")


if __name__ == "__main__":
    main()
