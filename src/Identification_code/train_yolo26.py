# train_yolo26.py
from ultralytics import YOLO
import torch

def main():
    # 1. 硬件自检与隔离
    print(f"CUDA 是否可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"当前使用的 GPU: {torch.cuda.get_device_name(0)}")

    # 2. 预处理模型拉取
    print(">> 正在拉取 YOLO26m 预训练权重...")
    model = YOLO("yolo26m.pt") 

    # 3. 启动端到端训练流水线
    print(">> 启动训练引擎...")
    results = model.train(
        data="data.yaml",       # 
        epochs=50,              # 50 轮看拟合趋势
        imgsz=640,              # 输入图像缩放尺寸
        batch=16,               # 
        device=0,               # 
        workers=4,              # 
        optimizer="auto",       # YOLO26 会自动探测并调用最新的 MuSGD 优化器
        amp=True,               # 
        project="yolo26_runs",  # 训练日志与权重保存的根目录
        name="project"   # 本次实验名称
    )

if __name__ == '__main__':
    main()
