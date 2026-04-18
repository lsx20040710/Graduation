import cv2
import time
import json
import os
import numpy as np

def load_fisheye_maps(json_path, size):
    """读取标定JSON文件并预计算映射表(比实时逐帧undistort快得多)"""
    if not os.path.exists(json_path):
        return None, None
        
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    K = np.array(data["camera_matrix"])
    D = np.array(data["distortion_coeffs"])
    # 鱼眼模型中，投影矩阵的左边 3x3 部分为无畸变画面的新内参
    K_new = np.array(data["projection_matrix"])[:3, :3]
    R = np.array(data["rectification_matrix"])
    
    # 提前计算好每个像素的偏移映射图 (CV_16SC2 格式对于 remap 性能更优)
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D, R, K_new, size, cv2.CV_16SC2)
    return map1, map2


def main():
    print("============= 摄像头预览与正畸配置 =============")
    
    cam_input = input("1. 请输入摄像头设备索引 (默认 1): ").strip()
    camera_idx = int(cam_input) if cam_input.isdigit() else 1
    
    print("2. 请选择分辨率:\n   [1] 640x480\n   [2] 1280x720\n   [3] 1920x1080")
    res_input = input("请输入选项 (默认 3): ").strip()
    
    width, height = 1920, 1080
    if res_input == "1": width, height = 640, 480
    elif res_input == "2": width, height = 1280, 720
        
    fps_input = input("3. 请输入期望帧率 [15 / 30] (默认 30): ").strip()
    target_fps = int(fps_input) if fps_input in ["15", "30"] else 30

    # 尝试加载标定文件
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', 'camera_calibration.json')
    map1, map2 = None, None
    undistort_enabled = False
    
    # 只有在 1080p 时才允许使用该标定文件的数据
    if os.path.exists(json_path) and (width, height) == (1920, 1080):
        print("\n[加载] 检测到 1080p 标定文件，正在初始化硬件加速正畸映射...")
        map1, map2 = load_fisheye_maps(json_path, (width, height))
        undistort_enabled = True
    elif os.path.exists(json_path):
        print("\n[注意] 检测到标定文件，但您选择的分辨率非标定分辨率(1080p)，正畸已被禁用。")

    print("\n正在打开摄像头 ...")
    cap = cv2.VideoCapture(camera_idx)

    if not cap.isOpened():
        print(f"错误: 无法打开摄像头 {camera_idx}。")
        return

    # 强制设置 MJPG, 宽高, 及帧率
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, target_fps)

    print("-" * 40)
    print("操作提示：")
    print(" - 按下 'u' 键 : 开启 / 关闭画面正畸")
    print(" - 按下 'q' 或 'ESC' 键 : 退出预览")
    print("-" * 40)

    prev_time = time.time()
    fps_display = 0.0
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # 处理按键事件
        key = cv2.waitKey(1) & 0xFF
        if key in [ord('q'), 27]:
            break
        elif key == ord('u') and map1 is not None:
            undistort_enabled = not undistort_enabled

        # 如果开启正畸，则执行 remap 映射
        if map1 is not None and undistort_enabled:
            # INTER_LINEAR (双线性插值) 是画质和速度的良好折中，BORDER_CONSTANT 使画面外的区域变黑
            display_frame = cv2.remap(frame, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            state_text = "Undistortion: ON "
            state_color = (0, 255, 0) # 绿色表示激活
        else:
            display_frame = frame
            state_text = "Undistortion: OFF"
            state_color = (0, 0, 255) # 红色表示原图

        # 帧率计算 (每 0.5 秒更新一次显示)
        frame_count += 1
        curr_time = time.time()
        if curr_time - prev_time >= 0.5:
            fps_display = frame_count / (curr_time - prev_time)
            prev_time = curr_time
            frame_count = 0

        # 在画面直接绘制关键信息并加黑边防遮挡
        info_y1, info_y2 = 40, 80
        cv2.putText(display_frame, f"FPS: {fps_display:.1f}", (15, info_y1), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(display_frame, f"FPS: {fps_display:.1f}", (15, info_y1), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        
        cv2.putText(display_frame, state_text, (15, info_y2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(display_frame, state_text, (15, info_y2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, state_color, 2)

        cv2.imshow("RAW Camera Preview", display_frame)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
