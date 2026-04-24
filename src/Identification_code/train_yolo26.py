"""
文件作用：
海参目标检测模型训练脚本（简练优化版）。
基于 ultralytics 框架，面向视觉伺服项目的小样本单类别数据集，主要目标为轻量、高效、易扩展。
"""

import argparse
import os
import torch
from pathlib import Path
from ultralytics import YOLO

# 解决 Windows 环境下可能的 OpenMP 重复初始化问题
if os.name == "nt":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

def parse_args():
    parser = argparse.ArgumentParser(description="海参检测模型训练简练版脚本")
    parser.add_argument("--data", default="data.yaml", help="数据集配置文件路径 (必须存在)")
    parser.add_argument("--model", default="yolo26n.pt", help="预训练权重(如 yolo26n.pt, yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=150, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=640, help="输入图像尺寸")
    parser.add_argument("--batch", type=int, default=16, help="批大小")
    parser.add_argument("--device", default="", help="训练设备如 0, 0,1 或 cpu。不填将自动选择")
    parser.add_argument("--workers", type=int, default=4, help="数据加载线程数 (Windows建议不超4)")
    parser.add_argument("--run-name", default="yolo26_runs", help="本次实验名称")
    return parser.parse_args()

def main():
    args = parse_args()

    # 1. 设备检查与分配
    device = args.device if args.device else (0 if torch.cuda.is_available() else "cpu")
    
    print("========== 训练配置 ==========")
    print(f"数据配置: {args.data}")
    print(f"选用模型: {args.model}")
    print(f"训练设备: {device}")
    print("==============================")

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"错误: 找不到数据集配置文件 {data_path.resolve()}")
        return

    # 2. 初始化模型
    try:
        # 支持本地传入 yolo26n.pt 或在线拉取
        model = YOLO(args.model)
    except Exception as e:
        print(f"预训练权重加载失败! 错误信息: {e}")
        return

    # 3. 启动训练
    print(f">> 启动模型训练...")
    # 核心训练参数全部通过 args 透传且使用官方 API 管理
    model.train(
        data=str(data_path.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=args.workers,
        name=args.run_name,
        patience=30,           # 早停防止过拟合
        plots=True,            # 输出验证集图表，方便观察性能
    )
    print(">> 训练阶段结束。")

if __name__ == "__main__":
    main()

