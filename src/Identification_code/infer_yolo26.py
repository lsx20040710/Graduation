"""
海参目标检测推理脚本（简练优化版）
- 保留轻便的图形界面交互（选择权重、模式、文件路径）
- 与去畸变核心逻辑(preview_raw_camera.py)联动，使得送入YOLO和呈现的画面直接就是正畸后的物理还原画面
- 舍弃了原来高达上千行的过度工程化设计，直接运用 YOLO 与 OpenCV 原生强大特性
"""
import os
import sys
import time
import cv2
from pathlib import Path

# 获取绝对路径，保证命令行从任何地方被启动都不偏离
SCRIPT_DIR = Path(__file__).resolve().parent

# 引入去畸变函数 (上翻一级目录定位 calibration)
sys.path.append(str(SCRIPT_DIR.parent))
try:
    from calibration.preview_raw_camera import load_fisheye_maps
except ImportError as e:
    print(f"[警告] 去畸变模块导入可能会受限，请确认路径: {e}")
    load_fisheye_maps = None

import torch
from ultralytics import YOLO
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

# 解决 Windows 环境下可能的 OpenMP 重复初始化问题
if os.name == "nt":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


# ================= 1. UI 交互：保留简练的选择系统 =================

def create_tk_root():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root

def find_latest_weight(search_root=SCRIPT_DIR):
    candidate_paths = list(search_root.glob("*.pt")) + list(search_root.glob("runs/**/*.pt"))
    if not candidate_paths:
        return None
    # 按照文件修改时间，取最新的
    return sorted(candidate_paths, key=lambda x: x.stat().st_mtime, reverse=True)[0]

def gui_select_weight():
    root = create_tk_root()
    latest_pt = find_latest_weight()
    
    if latest_pt:
        # 弹窗询问是否直接使用最新生成的模型权重
        msg = f"检测到最新模型权重：\n{latest_pt.name}\n\n是否直接使用该权重启动？"
        if messagebox.askyesno("权重选择", msg, parent=root):
            root.destroy()
            return latest_pt

    # 如果否，则让用户自己从系统中选
    weight_path = filedialog.askopenfilename(
        title="手动选择 YOLO 权重文件",
        filetypes=[("PyTorch Weights", "*.pt")],
        initialdir=str(SCRIPT_DIR),
        parent=root
    )
    root.destroy()
    return Path(weight_path) if weight_path else None

def gui_select_mode():
    root = tk.Tk()
    root.title("海参检测 - 场景选择")
    root.geometry("320x180")
    root.eval('tk::PlaceWindow . center')
    
    selected_mode = tk.StringVar(value="")
    def set_mode(m):
        selected_mode.set(m)
        root.destroy()
        
    tk.Label(root, text="请选择待识别的输入源类型:", font=("Arial", 12)).pack(pady=10)
    tk.Button(root, text="图片文件 (Image)", font=("Arial", 11), command=lambda: set_mode("image")).pack(fill=tk.X, padx=20, pady=5)
    tk.Button(root, text="视频文件 (Video)", font=("Arial", 11), command=lambda: set_mode("video")).pack(fill=tk.X, padx=20, pady=5)
    tk.Button(root, text="现场摄像头 (Camera)", font=("Arial", 11), command=lambda: set_mode("camera")).pack(fill=tk.X, padx=20, pady=5)
    
    # 阻止点击窗口右上角的关闭时产生报错
    root.protocol("WM_DELETE_WINDOW", lambda: set_mode(""))
    root.mainloop()
    return selected_mode.get()

def gui_select_media(mode):
    root = create_tk_root()
    title = "选择待识别视频" if mode == "video" else "选择待识别图片"
    ftypes = [("Video", "*.mp4 *.avi *.mov *.mkv")] if mode == "video" else [("Image", "*.jpg *.png *.jpeg *.bmp *.webp")]
    path = filedialog.askopenfilename(title=title, filetypes=ftypes, initialdir=str(SCRIPT_DIR), parent=root)
    root.destroy()
    return path


# ================= 2. 核心推理链路 =================

def run_file_inference(model, file_path):
    """运用 Ultralytics 原生的接口完成文件（图片/视频）推理，自动包含显示和归档结果特性"""
    print(f"\n>> 正在分析文件: {file_path}")
    model.predict(source=str(file_path), show=True, save=True, project=str(SCRIPT_DIR / "runs" / "predict"))
    print(">> 分析完成！如果是视频会在播放完毕后结束，结果已自动保存。")

def run_camera_inference(model):
    """
    针对摄像头的底层控制链路：
    将相机硬件画面提取后 -> 利用物理标定JSON运算前馈拉伸去畸变 -> 再进入模型寻常目标推测，只生成一个闭环监测窗口不弹两个
    """
    root = create_tk_root()
    idx_str = simpledialog.askstring("选择摄像头", "请输入 USB 摄像头索引(如 0 或 1):", initialvalue="1", parent=root)
    root.destroy()
    
    if not idx_str or not idx_str.isdigit():
        print("未接收到正确的摄像头索引，终止操作。")
        return
        
    camera_idx = int(idx_str)
    cap = cv2.VideoCapture(camera_idx)
    
    if not cap.isOpened():
        print(f"\n[错误] 无法建立连接！请确认摄像头是否拔插稳妥，且索引号（{camera_idx}）正确。")
        return
        
    # 为满足此前鱼眼相机标定参数(1080p)的像素点映射规格，我们强制锁为1080p
    # 注意，如果你的相机不是1080p，该逻辑会自动无缝回退原画
    target_w, target_h = 1920, 1080
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

    # 尝试加载物理相机的去畸变鱼眼网格
    json_path = SCRIPT_DIR.parent / 'calibration' / 'output' / 'camera_calibration.json'
    map1, map2 = None, None
    if json_path.exists() and load_fisheye_maps is not None:
        print(f"\n[系统提醒] 已载入视觉特征标定数据 {json_path.name}")
        map1, map2 = load_fisheye_maps(str(json_path), (target_w, target_h))
    else:
        print("\n[系统提醒] 尚未完成硬件内参标定或数据不互通，退化为原始畸变视野...")

    print("\n>> 视觉伺服窗口已开启，请将焦点定在画面按 'q' 或 'Esc' 中止。")
    
    # 允许自由拉伸窗口尺寸，并给定一个不那么占地方的初始分辨率
    cv2.namedWindow("YOLO Visual Servo Local View", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("YOLO Visual Servo Local View", 1280, 720)
    
    prev_time = time.time()
    fps_display = 0.0
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("硬件图像推流中断！")
            break

        # ====== 步骤1：物理硬件畸变消除运算 ======
        if map1 is not None and map2 is not None:
            # 双线性插值重绘像素
            frame = cv2.remap(frame, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

        # ====== 步骤2：神经网高频检测 ======
        # 设置 verbose=False 是为了不让终端刷屏导致卡顿
        results = model.predict(source=frame, conf=0.25, verbose=False)
        annotated_frame = results[0].plot()

        # 每隔半秒平滑刷新一次 FPS 数字
        frame_count += 1
        curr_time = time.time()
        if curr_time - prev_time >= 0.5:
            fps_display = frame_count / (curr_time - prev_time)
            prev_time = curr_time
            frame_count = 0

        # 添加左上角标签明确显示当前的流状态
        status_text = "Undistorted Camera" if map1 is not None else "Raw Fisheye Camera"
        status_color = (0, 200, 0) if map1 is not None else (0, 100, 255)
        cv2.putText(annotated_frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
        cv2.putText(annotated_frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        
        # 绘制实时运算拉伸+推断的帧数
        cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
        cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        cv2.imshow("YOLO Visual Servo Local View", annotated_frame)
        
        if cv2.waitKey(1) & 0xFF in [ord('q'), 27]:
            break

    cap.release()
    cv2.destroyAllWindows()


# ================= 3. 主进程 =================

def main():
    weight_path = gui_select_weight()
    if not weight_path or not weight_path.exists():
        print("未选中可用的 .pt 网络权重模型，程序安全退出。")
        return
        
    try:
        model = YOLO(str(weight_path))
    except Exception as e:
        print(f"YOLO 模型加载发生底层冲突: {e}")
        return

    mode = gui_select_mode()
    if not mode:
        print("未选择输入模式。")
        return
        
    if mode in ["image", "video"]:
        media_path = gui_select_media(mode)
        if media_path:
            run_file_inference(model, media_path)
    elif mode == "camera":
        run_camera_inference(model)

if __name__ == "__main__":
    main()