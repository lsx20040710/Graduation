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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

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


# 低检测阈值先把候选目标交给 ByteTrack，后续由锁定 ID 和短时保持来抑制画框闪烁
TRACK_CONFIDENCE = 0.30
MAX_LOST_FRAMES = 5


@dataclass
class TrackedTargetState:
    """
    保存当前视觉伺服锁定目标的帧间状态。
    track_id 来自 ByteTrack，用于跨帧锁定同一海参；短时漏检时继续保留上一帧框和误差，避免显示和伺服输入瞬间归零。
    """
    max_lost_frames: int = MAX_LOST_FRAMES
    track_id: Optional[int] = None
    bbox: Optional[Tuple[int, int, int, int]] = None
    center: Optional[Tuple[int, int]] = None
    err_x: Optional[float] = None
    err_y: Optional[float] = None
    confidence: float = 0.0
    lost_frames: int = 0

    def has_target(self):
        """返回当前是否还有可用于绘制或控制的目标状态。"""
        return self.bbox is not None and self.center is not None

    def update(self, detection, image_center):
        """用当前帧检测框刷新锁定目标，并计算相对相机中心的图像误差。"""
        self.track_id = detection["track_id"]
        self.bbox = detection["bbox"]
        self.center = detection["center"]
        self.confidence = detection["confidence"]
        self.lost_frames = 0
        self.err_x = float(self.center[0] - image_center[0])
        self.err_y = float(image_center[1] - self.center[1])

    def mark_lost(self):
        """当前帧没有匹配到原 ID 时只增加丢失计数，不立刻清空上一帧目标。"""
        if self.has_target():
            self.lost_frames += 1

    def can_hold(self):
        """短时漏检期间允许沿用上一帧目标，超过阈值后释放目标。"""
        return self.has_target() and self.lost_frames <= self.max_lost_frames

    def reset(self):
        """连续漏检超过阈值后清空锁定对象，下一次重新按画面中心选择目标。"""
        self.track_id = None
        self.bbox = None
        self.center = None
        self.err_x = None
        self.err_y = None
        self.confidence = 0.0
        self.lost_frames = 0


# ================= 1. UI 交互：保留简练的选择系统 =================

def create_tk_root():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root

def find_latest_weight(search_root=SCRIPT_DIR):
    # 优先从训练输出目录寻找 best.pt，这是针对当前海参特定训练的专有模型
    candidate_paths = list(search_root.glob("runs/**/weights/best.pt"))
    if not candidate_paths:
        # 如果没有 best.pt，退而寻找 runs 里的任意 .pt (例如 last.pt)
        candidate_paths = list(search_root.glob("runs/**/*.pt"))
        if not candidate_paths:
            # 实在没有，再找根目录下的原生预训练模型 (如 yolo26m.pt 等通用模型)
            candidate_paths = list(search_root.glob("*.pt"))
            if not candidate_paths:
                return None
    
    # 按照文件修改时间，在同优先级下取最新的
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

def _extract_track_id(box):
    """从 Ultralytics 的单个检测框中提取 ByteTrack ID；没有 ID 时返回 None。"""
    if box.id is None:
        return None
    return int(box.id.cpu().numpy().item())


def _extract_confidence(box):
    """读取检测置信度，便于调试低阈值 Tracking 是否持续接收到目标。"""
    if box.conf is None:
        return 0.0
    return float(box.conf.cpu().numpy().item())


def _collect_detections(result):
    """把 YOLO Boxes 转成轻量字典，后续目标锁定逻辑只依赖中心点、框、ID 和置信度。"""
    detections = []
    if result.boxes is None or len(result.boxes) == 0:
        return detections

    for box in result.boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        bbox = (int(x1), int(y1), int(x2), int(y2))
        center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
        detections.append({
            "track_id": _extract_track_id(box),
            "bbox": bbox,
            "center": center,
            "confidence": _extract_confidence(box),
        })
    return detections


def _distance_sq(point_a, point_b):
    """使用距离平方比较目标远近，避免每帧额外开方计算。"""
    return (point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2


def _select_detection_for_target(target_state, detections, image_center):
    """
    选择本帧要更新的目标。
    已有 track_id 时必须匹配同一 ID；没有 ID 时才退化为按上一帧中心或画面中心选择。
    """
    if not detections:
        return None

    if target_state.track_id is not None:
        for detection in detections:
            if detection["track_id"] == target_state.track_id:
                return detection
        return None

    reference_center = target_state.center if target_state.has_target() else image_center
    return min(detections, key=lambda item: _distance_sq(item["center"], reference_center))


def _draw_tracked_target(frame, target_state, image_center):
    """手动画锁定目标，短时保持状态用黄色显示，当前帧真实匹配状态用红色显示。"""
    if not target_state.can_hold():
        return False

    x1, y1, x2, y2 = target_state.bbox
    obj_cx, obj_cy = target_state.center
    is_live = target_state.lost_frames == 0
    color = (0, 0, 255) if is_live else (0, 255, 255)
    label = "LOCKED" if is_live else "HOLD"
    track_label = target_state.track_id if target_state.track_id is not None else "none"

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    cv2.circle(frame, (obj_cx, obj_cy), 8, color, -1)
    cv2.line(frame, image_center, (obj_cx, obj_cy), color, 3)

    err_x = target_state.err_x if target_state.err_x is not None else 0.0
    err_y = target_state.err_y if target_state.err_y is not None else 0.0
    cv2.putText(frame, f"{label} ID:{track_label} lost:{target_state.lost_frames} conf:{target_state.confidence:.2f}",
                (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
    cv2.putText(frame, f"{label} ID:{track_label} lost:{target_state.lost_frames} conf:{target_state.confidence:.2f}",
                (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(frame, f"Target Error -> dx: {err_x:.1f} px, dy: {err_y:.1f} px",
                (image_center[0] + 10, image_center[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
    cv2.putText(frame, f"Target Error -> dx: {err_x:.1f} px, dy: {err_y:.1f} px",
                (image_center[0] + 10, image_center[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return True

def run_file_inference(model, file_path):
    """运用 Ultralytics 原生的 track 接口完成文件（图片/视频）稳定推理追踪"""
    print(f"\n>> 正在分析文件: {file_path}")
    
    # 图片文件直接使用原生自带接口即可，因为它不需要动态准星
    if str(file_path).lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
        model.track(source=str(file_path), conf=TRACK_CONFIDENCE, show=True, save=True, persist=True, tracker="bytetrack.yaml", project=str(SCRIPT_DIR / "runs" / "predict"))
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

def run_servo_tracking_loop(model, cap, is_camera=True, map1=None, map2=None, fps_delay=1, servo_callback=None, record_video=False, plot_curve=False):
    """提取的通用识别控制循环（支持视频流和摄像头流，支持回调视觉误差供伺服控制使用）"""
    
    print("\n>> 视觉伺服窗口已开启，请将焦点定在画面按 'q' 或 'Esc' 中止。")
    
    # 允许自由拉伸窗口尺寸，并给定一个不那么占地方的初始分辨率
    cv2.namedWindow("YOLO Visual Servo Local View", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("YOLO Visual Servo Local View", 1280, 720)
    
    prev_time = time.time()
    fps_display = 0.0
    frame_count = 0
    
    # 初始化录制功能
    video_writer = None
    if record_video:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        record_dir = SCRIPT_DIR / "runs" / "records"
        record_dir.mkdir(parents=True, exist_ok=True)
        vid_path = str(record_dir / f"servo_track_{timestamp}.avi")
        # 由于我们这里不知道画面的最终实际宽高，我们在第一帧再初始化 writer
        
    # 初始化数据记录功能
    time_history = []
    err_x_history = []
    err_y_history = []
    start_time = time.time()
    last_debug_time = 0.0
    target_state = TrackedTargetState()

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
        image_center = (center_x, center_y)

        # ====== 步骤2：目标稳定检测与帧间 Tracking ======
        # 先以较低阈值保留候选框给 ByteTrack，再由 target_state 锁定 ID 和短时保持来决定最终显示目标
        results = model.track(source=frame, conf=TRACK_CONFIDENCE, persist=True, tracker="bytetrack.yaml", verbose=False)
        annotated_frame = frame.copy()
        detections = _collect_detections(results[0])
        matched_detection = _select_detection_for_target(target_state, detections, image_center)

        if matched_detection is not None:
            target_state.update(matched_detection, image_center)
        else:
            target_state.mark_lost()
            if not target_state.can_hold():
                target_state.reset()

        # ====== 步骤3：在画面中心打上参考准星靶心 ======
        # 画绿色的相机中心十字准星
        cv2.line(annotated_frame, (center_x - 30, center_y), (center_x + 30, center_y), (0, 255, 0), 2)
        cv2.line(annotated_frame, (center_x, center_y - 30), (center_x, center_y + 30), (0, 255, 0), 2)

        # ====== 步骤4：绘制锁定目标，并提取当前可输出给伺服的 Error ======
        err_x, err_y = 0.0, 0.0
        target_found = _draw_tracked_target(annotated_frame, target_state, image_center)
        if target_found:
            err_x = target_state.err_x
            err_y = target_state.err_y

        # 如果传入了伺服控制回调函数，则把偏差发过去执行机械臂随动控制
        if servo_callback is not None:
            servo_callback(err_x if target_found else None, err_y if target_found else None, annotated_frame)

        # ====== 杂项：FPS状态渲染 ======
        frame_count += 1
        curr_time = time.time()
        if curr_time - prev_time >= 0.5:
            fps_display = frame_count / (curr_time - prev_time)
            prev_time = curr_time
            frame_count = 0

        if curr_time - last_debug_time >= 1.0:
            if target_state.has_target():
                print(f"[追踪状态] track_id={target_state.track_id}, lost_frames={target_state.lost_frames}, err_x={target_state.err_x:.1f}, err_y={target_state.err_y:.1f}")
            else:
                print("[追踪状态] track_id=None, lost_frames=0, err_x=None, err_y=None")
            last_debug_time = curr_time

        status_text = "Undistorted Tracking" if map1 is not None else ("Raw Fisheye Tracking" if is_camera else "Video Tracking")
        status_color = (0, 200, 0) if map1 is not None else ((0, 100, 255) if is_camera else (255, 100, 0))
        cv2.putText(annotated_frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
        cv2.putText(annotated_frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        
        cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
        cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        # 录制视频
        if record_video:
            if video_writer is None:
                h, w = annotated_frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                video_writer = cv2.VideoWriter(vid_path, fourcc, 30.0, (w, h))
            video_writer.write(annotated_frame)
            
        # 记录误差用于绘制曲线
        if plot_curve and target_found:
            time_history.append(time.time() - start_time)
            err_x_history.append(err_x)
            err_y_history.append(err_y)

        cv2.imshow("YOLO Visual Servo Local View", annotated_frame)
        
        # 针对视频如果过快，延缓帧数；对摄像头则设为最小1ms
        if cv2.waitKey(int(fps_delay)) & 0xFF in [ord('q'), 27]:
            break

    if video_writer is not None:
        video_writer.release()
        print(f">> 视频已保存至: {vid_path}")

    if plot_curve and len(time_history) > 0:
        try:
            import matplotlib.pyplot as plt
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            plot_dir = SCRIPT_DIR / "runs" / "records"
            plot_dir.mkdir(parents=True, exist_ok=True)
            plot_path = str(plot_dir / f"servo_error_{timestamp}.png")
            
            # 保存原始数据到 CSV
            csv_path = str(plot_dir / f"servo_data_{timestamp}.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Time(s),ErrorX(px),ErrorY(px)\n")
                for t, ex, ey in zip(time_history, err_x_history, err_y_history):
                    f.write(f"{t:.4f},{ex:.2f},{ey:.2f}\n")
            print(f">> 原始伺服误差数据已保存至: {csv_path} (可用于二次裁剪绘图)")
            
            plt.figure(figsize=(10, 6))
            plt.plot(time_history, err_x_history, label='Error X (px)', color='r', alpha=0.8)
            plt.plot(time_history, err_y_history, label='Error Y (px)', color='b', alpha=0.8)
            plt.axhline(0, color='black', linestyle='--', linewidth=1)
            plt.title('Visual Servo Tracking Error Response', fontsize=14)
            plt.xlabel('Time (s)', fontsize=12)
            plt.ylabel('Pixel Error (px)', fontsize=12)
            plt.legend(loc='upper right')
            plt.grid(True, linestyle=':', alpha=0.7)
            plt.tight_layout()
            plt.savefig(plot_path, dpi=300)
            print(f">> 响应曲线已保存至: {plot_path}")

            # 画二维轨迹图
            plot_traj_path = str(plot_dir / f"servo_traj_{timestamp}.png")
            plt.figure(figsize=(8, 8))
            plt.plot(err_x_history, err_y_history, marker='o', markersize=4, linestyle='-', color='purple', alpha=0.6, label='Trajectory')
            plt.plot(err_x_history[0], err_y_history[0], 'go', markersize=10, label='Start') # 起点
            plt.plot(err_x_history[-1], err_y_history[-1], 'ro', markersize=10, label='End') # 终点
            plt.plot(0, 0, 'k+', markersize=15, markeredgewidth=2, label='Target Center') # 靶心
            plt.title('2D Image-Plane Trajectory', fontsize=14)
            plt.xlabel('Error X (px)', fontsize=12)
            plt.ylabel('Error Y (px)', fontsize=12)
            plt.axhline(0, color='black', linestyle='--', linewidth=1)
            plt.axvline(0, color='black', linestyle='--', linewidth=1)
            plt.legend(loc='best')
            plt.grid(True, linestyle=':', alpha=0.7)
            plt.axis('equal') # 保证 X 和 Y 的比例尺相同
            plt.tight_layout()
            plt.savefig(plot_traj_path, dpi=300)
            print(f">> 2D二维轨迹图已保存至: {plot_traj_path}")

        except ImportError:
            print("【警告】未安装 matplotlib 库，无法绘制保存响应曲线！请先运行: pip install matplotlib")

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
