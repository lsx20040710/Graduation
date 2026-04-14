"""
文件作用：
将原始图片目录和 YOLO 标签目录划分为训练集与验证集，并复制到目标数据集目录。

主要内容：
1. 支持通过命令行指定图片输入目录；
2. 支持通过命令行指定标签输入目录；
3. 支持通过命令行指定训练输出目录和验证集比例；
4. 保留默认目录结构，但不再把路径写死在代码里。
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


# 当前项目主要使用 jpg 抽帧图像，同时也兼容常见图片后缀。
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def resolve_path(path_text: str, base_dir: Path) -> Path:
    """
    作用：
    将相对路径解析为基于脚本目录的绝对路径，避免从不同终端目录运行时出错。

    输入：
    - path_text: 命令行传入的路径字符串；
    - base_dir: 当前脚本所在目录。

    返回：
    - Path: 解析后的绝对路径。
    """
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def parse_args(script_dir: Path) -> argparse.Namespace:
    """
    作用：
    解析命令行参数，使图片目录、标签目录和输出目录都可以按项目实际情况调整。

    输入：
    - script_dir: 当前脚本目录，用于构造默认路径。

    返回：
    - argparse.Namespace: 参数对象。
    """
    parser = argparse.ArgumentParser(description="划分 YOLO 数据集并复制到 train/val 目录结构。")
    parser.add_argument(
        "--image-dir",
        default=str(script_dir / "raw_data" / "images"),
        help="原始图片目录。",
    )
    parser.add_argument(
        "--label-dir",
        default=str(script_dir / "raw_data" / "yolo_txts"),
        help="YOLO TXT 标签目录。",
    )
    parser.add_argument(
        "--target-root",
        default=str(script_dir / "datasets" / "my_dataset"),
        help="训练数据集输出根目录。",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.2,
        help="验证集比例，取值范围在 0 到 1 之间。",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子，用于保证每次划分结果可复现。",
    )
    return parser.parse_args()


def collect_images(image_dir: Path) -> list[Path]:
    """
    作用：
    收集指定目录下的所有图片文件，并按文件名排序后返回。

    输入：
    - image_dir: 原始图片目录。

    返回：
    - list[Path]: 图片路径列表。
    """
    image_paths = [
        image_path
        for image_path in image_dir.iterdir()
        if image_path.is_file() and image_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    return sorted(image_paths)


def prepare_target_dirs(target_root: Path) -> dict[str, Path]:
    """
    作用：
    创建标准 YOLO 训练目录结构，避免复制阶段反复判断目录是否存在。

    输入：
    - target_root: 数据集输出根目录。

    返回：
    - dict[str, Path]: 训练集和验证集对应的图片、标签目录映射。
    """
    dirs = {
        "train_img_dir": target_root / "images" / "train",
        "val_img_dir": target_root / "images" / "val",
        "train_label_dir": target_root / "labels" / "train",
        "val_label_dir": target_root / "labels" / "val",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def copy_files(
    image_paths: list[Path], target_image_dir: Path, target_label_dir: Path, label_dir: Path
) -> None:
    """
    作用：
    复制图片及其同名标签到指定目标目录。

    输入：
    - image_paths: 本批次待复制的图片列表；
    - target_image_dir: 图片目标目录；
    - target_label_dir: 标签目标目录；
    - label_dir: 原始 YOLO 标签目录。
    """
    for image_path in image_paths:
        label_path = label_dir / f"{image_path.stem}.txt"

        # 图片和标签分开复制，便于后续直接符合 Ultralytics 的目录习惯。
        shutil.copy2(image_path, target_image_dir / image_path.name)
        if label_path.exists():
            shutil.copy2(label_path, target_label_dir / label_path.name)


def main() -> None:
    """
    作用：
    组织数据集划分流程，包括路径检查、随机划分、文件复制和结果输出。
    """
    script_dir = Path(__file__).resolve().parent
    args = parse_args(script_dir)

    image_dir = resolve_path(args.image_dir, script_dir)
    label_dir = resolve_path(args.label_dir, script_dir)
    target_root = resolve_path(args.target_root, script_dir)

    if not image_dir.exists() or not image_dir.is_dir():
        raise FileNotFoundError(f"图片目录不存在：{image_dir}")
    if not label_dir.exists() or not label_dir.is_dir():
        raise FileNotFoundError(f"标签目录不存在：{label_dir}")
    if not 0 < args.val_ratio < 1:
        raise ValueError("val_ratio 必须在 0 和 1 之间。")

    image_paths = collect_images(image_dir)
    if not image_paths:
        print(f"[错误] 在 {image_dir} 中没有找到任何图片文件。")
        return

    random.seed(args.seed)
    random.shuffle(image_paths)

    split_index = int(len(image_paths) * (1 - args.val_ratio))
    train_files = image_paths[:split_index]
    val_files = image_paths[split_index:]
    dirs = prepare_target_dirs(target_root)

    print(f"正在复制 {len(train_files)} 个文件到训练集...")
    copy_files(train_files, dirs["train_img_dir"], dirs["train_label_dir"], label_dir)

    print(f"正在复制 {len(val_files)} 个文件到验证集...")
    copy_files(val_files, dirs["val_img_dir"], dirs["val_label_dir"], label_dir)

    print("\n数据集划分完成！")
    print(f"图片目录：{image_dir}")
    print(f"标签目录：{label_dir}")
    print(f"训练集：{len(train_files)} | 验证集：{len(val_files)}")
    print(f"输出目录：{target_root}")


if __name__ == "__main__":
    main()
