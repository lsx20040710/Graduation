"""
海参目标检测与追踪推理脚本（视觉伺服初探版）
- 保留轻便的图形界面交互
- 与去畸变核心逻辑(preview_raw_camera.py)联动，获得物理级无失真画面
- 加入卡尔曼滤波帧间目标 Tracking，锁定 ID 避免画面闪烁
- 直接渲染相机屏幕中心基准线和目标中心点，实时导出坐标偏置 (errX, errY) 准备对接串口伺服
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


# ================= 2. 核心跟踪推理链路 =================

def run_file_inference(model, file_path):
    """运用 Ultralytics 原生的 track 接口完成文件（图片/视频）稳定推理追踪"""
    print(f"\n>> 正在分析文件: {file_path}")
    
    # 图片文件直接使用原生自带接口即可，因为它不需要动态准星
    if str(file_path).lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
        model.track(source=str(file_path), show=True, save=True, persist=True, tracker="bytetrack.yaml", project=str(SCRIPT_DIR / "runs" / "predict"))
        print(">> 图片分析完成！如果没报错的话结果已自动保存。")
        return

    # 视频流则和摄像头一样提取出来，接入自绘视觉伺服十字准星的逻辑
    cap = cv2.VideoCapture(str(file_path))
    if not cap.isOpened():
        print(f"无法读取视频文件: {file_path}")
        return
    run_servo_tracking_loop(model, cap, is_camera=False, fps_delay=30)  # 为了视频不快进增加一个默认延迟


def run_camera_inference(model):
    """
    针对摄像头的底层控制预演链路：
    将相机硬件画面提取后 -> 标定矩阵去畸变 -> Track获取稳定跟踪框 -> 结算与画面中心的误差 -> 生成指令基础
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
        
    target_w, target_h = 1920, 1080
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

    json_path = SCRIPT_DIR.parent / 'calibration' / 'output' / 'camera_calibration.json'
    map1, map2 = None, None
    if json_path.exists() and load_fisheye_maps is not None:
        print(f"\n[系统提醒] 已载入视觉特征标定数据 {json_path.name}")
        map1, map2 = load_fisheye_maps(str(json_path), (target_w, target_h))
    else:
        print("\n[系统提醒] 尚未完成硬件内参标定或数据不互通，退化为原始畸变视野...")

    run_servo_tracking_loop(model, cap, is_camera=True, map1=map1, map2=map2, fps_delay=1)

def run_servo_tracking_loop(model, cap, is_camera=True, map1=None, map2=None, fps_delay=1):
    """提取的通用识别控制循环（支持视频流和摄像头流）"""
    
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
            frame = cv2.remap(frame, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

        # 缓存当前画面的物理中心 (基准点)
        frame_h, frame_w = frame.shape[:2]
        center_x, center_y = frame_w // 2, frame_h // 2

        # ====== 步骤2：目标稳定检测与帧间 Tracking ======
        # persist=True 保障帧间卡尔曼滤波关联，能够极大缓解因水下浑浊造成某一帧漏检或框急剧跳动
        results = model.track(source=frame, conf=0.3, persist=True, tracker="bytetrack.yaml", verbose=False)
        annotated_frame = results[0].plot()

        # ====== 步骤3：在画面中心打上参考准星靶心 ======
        # 画绿色的相机中心十字准星
        cv2.line(annotated_frame, (center_x - 30, center_y), (center_x + 30, center_y), (0, 255, 0), 2)
        cv2.line(annotated_frame, (center_x, center_y - 30), (center_x, center_y + 30), (0, 255, 0), 2)

        # ====== 步骤4：找出离中心最近或最稳定的目标，提取并绘制 Error ======
        if results[0].boxes is not None and len(results[0].boxes) > 0:
            # 找到首个（置信度高或追踪最稳）的锁定海参靶标
            box = results[0].boxes[0]
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            
            # 计算目标的质心位置
            obj_cx = int((x1 + x2) / 2)
            obj_cy = int((y1 + y2) / 2)
            
            # 视觉伺服中最重要的解：计算图像平面中的偏移量 e = [ex, ey]
            # y 轴向上为正方向计算：
            err_x = obj_cx - center_x
            err_y = center_y - obj_cy
            
            # 画一个显眼的红色圆点在海参肚子正中央
            cv2.circle(annotated_frame, (obj_cx, obj_cy), 8, (0, 0, 255), -1)
            # 在中心和海参之间拉一条红线，直观表现出相差的距离向量
            cv2.line(annotated_frame, (center_x, center_y), (obj_cx, obj_cy), (0, 0, 255), 3)
            
            # 在准星旁边印出数据
            err_text = f"Target Error -> dx: {err_x} px, dy: {err_y} px"
            cv2.putText(annotated_frame, err_text, (center_x + 10, center_y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # ====== 杂项：FPS状态渲染 ======
        frame_count += 1
        curr_time = time.time()
        if curr_time - prev_time >= 0.5:
            fps_display = frame_count / (curr_time - prev_time)
            prev_time = curr_time
            frame_count = 0

        status_text = "Undistorted Tracking" if map1 is not None else ("Raw Fisheye Tracking" if is_camera else "Video Tracking")
        status_color = (0, 200, 0) if map1 is not None else ((0, 100, 255) if is_camera else (255, 100, 0))
        cv2.putText(annotated_frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
        cv2.putText(annotated_frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        
        cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
        cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        cv2.imshow("YOLO Visual Servo Local View", annotated_frame)
        
        # 针对视频如果过快，延缓帧数；对摄像头则设为最小1ms
        if cv2.waitKey(int(fps_delay)) & 0xFF in [ord('q'), 27]:
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