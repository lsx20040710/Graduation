import cv2
import datetime
import os
import numpy as np
from ultralytics import YOLO
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def _script_dir():
    return os.path.dirname(os.path.abspath(__file__))

def _ensure_output_dir():
    out_dir = os.path.join(_script_dir(), "output")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def _resolve_path(path):
    if path is None:
        return None
    path = str(path).strip()
    if not path:
        return None
    if os.path.isabs(path):
        return path
    return os.path.join(_script_dir(), path)

def three_channel_underwater_enhance(frame):
    """
    三通道水下色彩补偿与增强算法
    原理：针对水下红光衰减严重的物理特性，基于绿通道动态补偿红通道，并结合CLAHE去雾
    """
    # 1. 拆分 B, G, R 三个独立通道 (转为浮点数防溢出)
    b, g, r = cv2.split(frame.astype(np.float32))

    # 2. 计算各通道的全局平均亮度
    mean_r = np.mean(r)
    mean_g = np.mean(g)
    mean_b = np.mean(b)

    # 3. 【核心】三通道红色补偿机制
    alpha = 0.8 
    r_compensated = r + alpha * (mean_g - mean_r) * (1.0 - r / 255.0)

    # 将补偿后的像素值限制在合理的 0-255 范围内
    r_compensated = np.clip(r_compensated, 0, 255)
    
    # 4. 重新合并三通道
    compensated_img = cv2.merge((b, g, r_compensated)).astype(np.uint8)

    # 5. 转换到 LAB 色彩空间，对亮度通道 (L) 进行自适应直方图均衡化去雾
    lab = cv2.cvtColor(compensated_img, cv2.COLOR_BGR2LAB)
    l, a, b_chan = cv2.split(lab)
    
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    
    # 合并并转回最终的 BGR 画面
    enhanced_lab = cv2.merge((cl, a, b_chan))
    final_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    return final_img

def generate_report(source_type, total_count, output_dir=None, comparison_image_path=None, saved_video_path=None):
    """生成简单的巡检报告"""
    if output_dir is None:
        output_dir = _ensure_output_dir()
    else:
        os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"Inspection_Report_{filename_time}.txt"
    report_path = os.path.join(output_dir, report_filename)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=====================================\n")
        f.write("      水下海产智能巡检与盘点报告     \n")
        f.write("=====================================\n")
        f.write(f"巡检时间: {timestamp}\n")
        f.write(f"巡检模式: {source_type}\n")
        f.write(f"盘点海参总数: {total_count} 只\n")
        if comparison_image_path:
            f.write(f"增强对比图: {comparison_image_path}\n")
        if saved_video_path:
            f.write(f"巡检录像(带框): {saved_video_path}\n")
        f.write("=====================================\n")
        
    print(f"\n>> 巡检结束！已自动生成报告: {report_path}")
    return report_path

def _load_model(model_path):
    try:
        model = YOLO(model_path)
        print(f">> 成功加载检测引擎: {model_path}")
        return model
    except Exception as e:
        raise RuntimeError(f"权重加载失败，请确认路径。错误: {e}") from e

def _infer_image(model, image_path, conf=0.5):
    print(f">> 正在识别图片: {image_path}")
    frame = cv2.imread(image_path)
    if frame is None:
        raise RuntimeError("图片读取失败，请检查文件是否损坏。")

    enhanced_frame = three_channel_underwater_enhance(frame)
    results = model.predict(source=enhanced_frame, conf=conf, verbose=False)

    window_name = "Underwater Inspection - Image (Enhanced)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    comparison_window = "Enhancement Comparison - Before vs After"
    cv2.namedWindow(comparison_window, cv2.WINDOW_NORMAL)

    out_dir = _ensure_output_dir()
    filename_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    comparison_path = os.path.join(out_dir, f"Enhancement_Comparison_{filename_time}.jpg")

    left = frame
    right = enhanced_frame
    if left.shape[:2] != right.shape[:2]:
        right = cv2.resize(right, (left.shape[1], left.shape[0]))
    pad = 6
    gap = np.zeros((left.shape[0], pad, 3), dtype=np.uint8)
    comparison_img = cv2.hconcat([left, gap, right])
    cv2.putText(comparison_img, "Before", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
    cv2.putText(comparison_img, "After", (left.shape[1] + pad + 20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
    cv2.imwrite(comparison_path, comparison_img)
    cv2.imshow(comparison_window, comparison_img)

    max_count = 0
    for r in results:
        annotated_frame = r.plot()
        current_count = len(r.boxes)
        max_count = current_count
        cv2.putText(
            annotated_frame,
            f"Sea Cucumbers: {current_count}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            3,
        )
        cv2.imshow(window_name, annotated_frame)
        print(">> 增强识别完成。按任意键关闭图片并生成报告...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return max_count, comparison_path

def _open_capture(source, is_camera):
    if is_camera:
        cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap
    return cv2.VideoCapture(source)

def _infer_video_or_camera(model, source, source_type, conf=0.5):
    cap = _open_capture(source, is_camera=(source_type == "实时摄像头"))
    if not cap.isOpened():
        raise RuntimeError("无法打开媒体源！请检查硬件或文件。")

    # --- 新增：获取视频属性，初始化 VideoWriter ---
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps):
        fps = 25.0  # 如果是摄像头获取不到FPS，默认设定为25帧

    out_dir = _ensure_output_dir()
    filename_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # 根据模式动态命名视频文件
    prefix = "Video" if source_type == "离线视频" else "Camera"
    output_video_path = os.path.join(out_dir, f"Inference_{prefix}_{filename_time}.mp4")
    
    # 设置 MP4 编码器
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_writer = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))
    # ---------------------------------------------

    window_name = "Underwater Inspection - Video/Camera (Enhanced)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    max_count = 0
    print(">> 增强识别已启动！按键盘上的 'q' 键退出巡检。")

    while True:
        success, frame = cap.read()
        if not success:
            print(">> 视频流结束或中断。")
            break

        enhanced_frame = three_channel_underwater_enhance(frame)
        results = model.predict(source=enhanced_frame, conf=conf, stream=True, verbose=False)

        for r in results:
            annotated_frame = r.plot()
            current_count = len(r.boxes)
            if current_count > max_count:
                max_count = current_count

            speed_ms = sum(r.speed.values())
            actual_fps = 1000.0 / speed_ms if speed_ms > 0 else 0

            cv2.putText(
                annotated_frame,
                f"FPS: {actual_fps:.1f}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )
            cv2.putText(
                annotated_frame,
                f"Current Count: {current_count}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2,
            )
            cv2.putText(
                annotated_frame,
                f"Total Found: {max_count}",
                (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 165, 0),
                2,
            )

            # --- 新增：将带识别框的当前帧写入视频文件 ---
            out_writer.write(annotated_frame)

            # 弹窗播放
            cv2.imshow(window_name, annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    out_writer.release() # 记得释放写入器
    cv2.destroyAllWindows()
    
    # 返回盘点最大数量以及保存的视频路径
    return max_count, output_video_path

def run_inference(mode, source_path=None, camera_index=0, model_path=None, conf=0.5):
    if model_path is None:
        model_path = "runs/detect/yolo26_runs/project3/weights/best.pt"

    model_path = _resolve_path(model_path)
    if not model_path or not os.path.exists(model_path):
        raise RuntimeError(f"找不到权重文件: {model_path}")

    model = _load_model(model_path)
    output_dir = _ensure_output_dir()

    if mode == "图片":
        source_path = _resolve_path(source_path)
        if not source_path or not os.path.exists(source_path):
            raise RuntimeError("找不到图片文件。")
        max_count, comparison_path = _infer_image(model, source_path, conf=conf)
        generate_report("单张图片", max_count, output_dir=output_dir, comparison_image_path=comparison_path)
        return

    if mode == "视频":
        source_path = _resolve_path(source_path)
        if not source_path or not os.path.exists(source_path):
            raise RuntimeError("找不到视频文件。")
        # 接收返回的视频路径并传给生成报告函数
        max_count, saved_video_path = _infer_video_or_camera(model, source_path, "离线视频", conf=conf)
        generate_report("离线视频", max_count, output_dir=output_dir, saved_video_path=saved_video_path)
        return

    if mode == "摄像头":
        # 接收返回的视频路径并传给生成报告函数
        max_count, saved_video_path = _infer_video_or_camera(model, int(camera_index), "实时摄像头", conf=conf)
        generate_report("实时摄像头", max_count, output_dir=output_dir, saved_video_path=saved_video_path)
        return

    raise RuntimeError("无效的模式。")

def _enumerate_cameras(max_index=10):
    indices = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap is None or not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            continue
        ok, _ = cap.read()
        cap.release()
        if ok:
            indices.append(i)
    return indices

class _App:
    def __init__(self, root):
        self.root = root
        self.root.title("水下海产智能巡检与盘点助手")
        self.root.resizable(False, False)

        self.mode_var = tk.StringVar(value="图片")
        self.file_var = tk.StringVar(value="")
        self.camera_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value="runs/detect/yolo26_runs/project2/weights/best.pt")
        self.conf_var = tk.DoubleVar(value=0.5)
        self.status_var = tk.StringVar(value="就绪")

        main = ttk.Frame(root, padding=14)
        main.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main, text="模式").grid(row=0, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(
            main,
            textvariable=self.mode_var,
            values=["图片", "视频", "摄像头"],
            state="readonly",
            width=18,
        )
        self.mode_combo.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_ui_state())

        ttk.Label(main, text="权重").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.model_entry = ttk.Entry(main, textvariable=self.model_var, width=44)
        self.model_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        ttk.Button(main, text="选择", command=self._pick_model).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

        ttk.Label(main, text="文件").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.file_entry = ttk.Entry(main, textvariable=self.file_var, width=44)
        self.file_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        self.pick_btn = ttk.Button(main, text="选择", command=self._pick_file)
        self.pick_btn.grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

        ttk.Label(main, text="摄像头").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.camera_combo = ttk.Combobox(main, textvariable=self.camera_var, values=[], state="readonly", width=18)
        self.camera_combo.grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        ttk.Button(main, text="刷新", command=self._refresh_cameras).grid(row=3, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

        ttk.Label(main, text="置信度").grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.conf_spin = ttk.Spinbox(main, from_=0.01, to=0.99, increment=0.01, textvariable=self.conf_var, width=6)
        self.conf_spin.grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(10, 0))

        btns = ttk.Frame(main)
        btns.grid(row=5, column=0, columnspan=3, sticky="w", pady=(14, 0))
        self.start_btn = ttk.Button(btns, text="开始巡检", command=self._start)
        self.start_btn.grid(row=0, column=0, sticky="w")
        ttk.Button(btns, text="退出", command=self.root.destroy).grid(row=0, column=1, sticky="w", padx=(10, 0))

        ttk.Label(main, textvariable=self.status_var, foreground="#444").grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))

        self._refresh_cameras()
        self._refresh_ui_state()

    def _pick_model(self):
        path = filedialog.askopenfilename(
            title="选择 YOLO 权重文件",
            filetypes=[("PyTorch Weights", "*.pt"), ("All Files", "*.*")],
        )
        if path:
            self.model_var.set(path)

    def _pick_file(self):
        mode = self.mode_var.get()
        if mode == "图片":
            path = filedialog.askopenfilename(
                title="选择图片文件",
                filetypes=[("Images", "*.jpg;*.jpeg;*.png;*.bmp"), ("All Files", "*.*")],
            )
        else:
            path = filedialog.askopenfilename(
                title="选择视频文件",
                filetypes=[("Videos", "*.mp4;*.avi;*.mov;*.mkv"), ("All Files", "*.*")],
            )
        if path:
            self.file_var.set(path)

    def _refresh_cameras(self):
        self.status_var.set("正在扫描摄像头...")
        self.root.update_idletasks()
        indices = _enumerate_cameras(max_index=12)
        values = [str(i) for i in indices]
        self.camera_combo["values"] = values
        if values:
            if self.camera_var.get() not in values:
                self.camera_var.set(values[0])
        else:
            self.camera_var.set("")
        self.status_var.set("就绪")
        self._refresh_ui_state()

    def _refresh_ui_state(self):
        mode = self.mode_var.get()
        if mode in ("图片", "视频"):
            self.file_entry.state(["!disabled"])
            self.pick_btn.state(["!disabled"])
            self.camera_combo.state(["disabled"])
        else:
            self.file_entry.state(["disabled"])
            self.pick_btn.state(["disabled"])
            self.camera_combo.state(["!disabled"])

    def _set_running(self, running):
        if running:
            self.start_btn.state(["disabled"])
            self.mode_combo.state(["disabled"])
            self.pick_btn.state(["disabled"])
            self.camera_combo.state(["disabled"])
            self.model_entry.state(["disabled"])
            self.conf_spin.state(["disabled"])
        else:
            self.start_btn.state(["!disabled"])
            self.mode_combo.state(["readonly"])
            self.model_entry.state(["!disabled"])
            self.conf_spin.state(["!disabled"])
            self._refresh_ui_state()

    def _start(self):
        mode = self.mode_var.get()
        model_path = self.model_var.get().strip()
        conf = float(self.conf_var.get())

        if mode in ("图片", "视频"):
            source_path = self.file_var.get().strip()
            if not source_path:
                messagebox.showerror("错误", "请先选择文件。")
                return
        else:
            source_path = None

        if mode == "摄像头":
            if not self.camera_var.get().strip():
                messagebox.showerror("错误", "未找到可用摄像头，请先刷新。")
                return
            camera_index = int(self.camera_var.get())
        else:
            camera_index = 0

        self._set_running(True)
        self.status_var.set("运行中...（OpenCV 窗口内按 q 退出）")

        def worker():
            try:
                run_inference(
                    mode=mode,
                    source_path=source_path,
                    camera_index=camera_index,
                    model_path=model_path,
                    conf=conf,
                )
                self.root.after(0, lambda: self.status_var.set("已结束，报告已生成。"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("运行失败", str(e)))
                self.root.after(0, lambda: self.status_var.set("失败"))
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=worker, daemon=True).start()

def run_gui():
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    _App(root)
    root.mainloop()

if __name__ == '__main__':
    run_gui()