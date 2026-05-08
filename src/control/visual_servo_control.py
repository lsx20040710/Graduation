import sys
import os
import time
import math
import cv2
from pathlib import Path
import traceback

# 解决 Windows 环境下可能的 OpenMP 重复初始化问题
if os.name == "nt":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

try:
    import keyboard
except ImportError:
    print("【错误】未找到 keyboard 库。")
    sys.exit(1)

# 将必要的目录加入包路径
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR.parent))

# ！！！直接引用你已经写好的完美识别模块！！！
try:
    from Identification_code.infer_yolo26 import find_latest_weight, run_servo_tracking_loop
except ImportError as e:
    print(f"【错误】无法引入你的 infer_yolo26.py 模块: {e}")
    sys.exit(1)

try:
    from ultralytics import YOLO
except ImportError:
    print("【错误】未找到 ultralytics 库，请 pip install ultralytics。")
    sys.exit(1)

# 尝试引入去畸变函数
try:
    from calibration.preview_raw_camera import load_fisheye_maps
except ImportError as e:
    load_fisheye_maps = None

# 从我们的控制包引入底层控制库
from test_servo_driver import HA8U25M_Servo
from filter_utils import EMAFilter, AngularEMAFilter
from multi_joint_kinematics import (
    J1_L, J2_L,
    joint2_to_tendon_delta,
    tip_position_to_joint1,
    joint1_to_tendon_delta_coupled,
    tendon_delta_to_motor_angle
)

# ==========================================
# 系统全局配置参数
# ==========================================
# 论文数据采集开关（如需在退出时自动录像并保存曲线，将其改为 True 即可，不影响您统一调试参数）
DATA_COLLECTION_MODE = True

COM_PORT = 'COM7'
SERVO_IDS = [1, 2, 3, 4, 5, 6]
CAMERA_IDX = 1

# 视觉伺服 PID 控制器增益 (增量式 PID)
# 由于当前逻辑是 target += dx，这本身是一个积分过程。
# K_I 相当于我们之前写的纯累加增益（控制稳态收敛）。
# K_P 相当于增加了阻尼，能对误差的“变化趋势”提前做出反应，是打破“画圈震荡”的关键。
K_P_X = -0.015  # 比例增益 (X反向)
K_I_X = -0.015  # 积分增益 (X反向，稍微调小以求稳定)
K_D_X = 0.0     # 微分增益 (暂设为0，如有高频微抖可适当加 0.005)

K_P_Y = 0.015   # 比例增益 (Y同向)
K_I_Y = 0.015   # 积分增益 (Y同向)
K_D_Y = 0.0     # 微分增益

# 机器人安全限位
MAX_R_1 = 250.0      # 第一关节最大 XY 偏移半径 (mm)
STEP_THETA_2 = 1.0   # 第二关节手动步长 (度)
STEP_PHI_2 = 2.0     # 第二关节手动步长 (度)
MAX_THETA_2 = 40.0   # 第二关节最大弯曲角 (度)
MIN_THETA_2 = 0.0    # 第二关节最小弯曲角 (度)

DEADZONE_PIXELS = 20 # 目标在中心 20 像素以内时不发生控制累计
MAX_STEP_XY = 10.0   # 每帧最大累计误差步长 (mm)

ALPHA_J1_XY = 0.40  # 提高为 0.4，降低算法侧带来的滤波迟滞，防画圈
ALPHA_J2_ANG = 0.15

# ==========================================
# 全局状态变量 (给回调函数使用)
# ==========================================
target_x_1, target_y_1 = 0.0, 0.0
ema_x_1 = EMAFilter(alpha=ALPHA_J1_XY, initial_value=0.0)
ema_y_1 = EMAFilter(alpha=ALPHA_J1_XY, initial_value=0.0)

target_theta_2_deg, target_phi_2_deg = 0.0, 0.0
ema_theta_2 = EMAFilter(alpha=ALPHA_J2_ANG, initial_value=0.0)
ema_phi_2 = AngularEMAFilter(alpha=ALPHA_J2_ANG, initial_value=0.0)

# 用于增量式 PID 的历史误差记录
prev_err_x, prev_err_y = 0.0, 0.0
prev2_err_x, prev2_err_y = 0.0, 0.0

servo = None


def visual_servo_callback(err_x, err_y, annotated_frame):
    """
    这个函数会被 infer_yolo26 里面的循环每帧调用一次！
    err_x, err_y 是像素误差。如果是 None 说明没看到海参。
    """
    global target_x_1, target_y_1, target_theta_2_deg, target_phi_2_deg, servo
    global prev_err_x, prev_err_y, prev2_err_x, prev2_err_y

    # ====== 视觉反馈化作位置增量 (增量式 PID 控制) ======
    if err_x is not None and err_y is not None:
        # 1. 死区处理：如果误差在死区内，强制视作无误差
        if abs(err_x) < DEADZONE_PIXELS: err_x = 0.0
        if abs(err_y) < DEADZONE_PIXELS: err_y = 0.0
        
        # 2. 增量式 PID 核心计算
        # dx = P * (本次误差 - 上次误差) + I * (本次误差) + D * (本次误差 - 2*上次误差 + 上上次误差)
        dx = K_P_X * (err_x - prev_err_x) + K_I_X * err_x + K_D_X * (err_x - 2 * prev_err_x + prev2_err_x)
        dy = K_P_Y * (err_y - prev_err_y) + K_I_Y * err_y + K_D_Y * (err_y - 2 * prev_err_y + prev2_err_y)
        
        # 3. 更新历史误差字典
        prev2_err_x, prev2_err_y = prev_err_x, prev_err_y
        prev_err_x, prev_err_y = err_x, err_y
        
        # 4. 速度/步长限幅
        dx = max(-MAX_STEP_XY, min(MAX_STEP_XY, dx))
        dy = max(-MAX_STEP_XY, min(MAX_STEP_XY, dy))

        target_x_1 += dx
        target_y_1 += dy
        
        r_target_1 = math.sqrt(target_x_1**2 + target_y_1**2)
        if r_target_1 > MAX_R_1:
            scale = MAX_R_1 / r_target_1
            target_x_1 *= scale
            target_y_1 *= scale

    # ====== 键盘人工微调第二关节 ======
    if keyboard.is_pressed('up'): target_theta_2_deg += STEP_THETA_2
    if keyboard.is_pressed('down'): target_theta_2_deg -= STEP_THETA_2
    if keyboard.is_pressed('left'): target_phi_2_deg += STEP_PHI_2
    if keyboard.is_pressed('right'): target_phi_2_deg -= STEP_PHI_2

    target_theta_2_deg = max(MIN_THETA_2, min(target_theta_2_deg, MAX_THETA_2))
    if target_phi_2_deg > 180.0: target_phi_2_deg -= 360.0
    elif target_phi_2_deg <= -180.0: target_phi_2_deg += 360.0

    # ====== 滤波器平滑 ======
    smooth_x_1 = ema_x_1.update(target_x_1)
    smooth_y_1 = ema_y_1.update(target_y_1)
    smooth_theta_2_deg = ema_theta_2.update(target_theta_2_deg)
    smooth_phi_2_deg = ema_phi_2.update(target_phi_2_deg)

    smooth_theta_2_rad = math.radians(smooth_theta_2_deg)
    smooth_phi_2_rad = math.radians(smooth_phi_2_deg)

    # ====== 联合运动学解算 ======
    dl4, dl5, dl6 = joint2_to_tendon_delta(smooth_theta_2_rad, smooth_phi_2_rad)
    q4, q5, q6 = tendon_delta_to_motor_angle(dl4, dl5, dl6)

    smooth_theta_1_rad, smooth_phi_1_rad = tip_position_to_joint1(smooth_x_1, smooth_y_1, J1_L)
    
    dl1, dl2, dl3 = joint1_to_tendon_delta_coupled(
        smooth_theta_1_rad, smooth_phi_1_rad, 
        smooth_theta_2_rad, smooth_phi_2_rad
    )
    q1, q2, q3 = tendon_delta_to_motor_angle(dl1, dl2, dl3)

    # ====== 舵机指令下发 ======
    if servo is not None:
        degs = [math.degrees(q) for q in [q1, q2, q3, q4, q5, q6]]
        for sid, deg in zip(SERVO_IDS, degs):
            servo.set_multi_turn_angle_time(sid, deg, 150)


def main():
    global servo
    print("==================================================")
    print("       视觉识别驱动的全臂联合伺服控制系统 启动        ")
    print("==================================================")
    
    # ！！！直接调用 infer_yolo26 里面的权重搜寻函数！！！
    ident_dir = SCRIPT_DIR.parent / 'Identification_code'
    model_path = find_latest_weight(ident_dir)
    if not model_path:
        print(f"【错误】在 {ident_dir} 下找不到任何 .pt 网络权重模型！请检查你训练好的权重位置。")
        return
        
    print(f"> 正在加载你训练的专属模型: {model_path} ...")
    model = YOLO(str(model_path))
    
    cap = None
    try:
        # --- 相机初始化 ---
        print(f"> 正在打开摄像头 {CAMERA_IDX} ...")
        cap = cv2.VideoCapture(CAMERA_IDX)
        if not cap.isOpened():
            print(f"【错误】无法打开摄像头 {CAMERA_IDX}")
            return
            
        target_w, target_h = 1920, 1080
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"> 相机实际分配分辨率: {actual_w}x{actual_h}")
        
        json_path = SCRIPT_DIR.parent / 'calibration' / 'output' / 'camera_calibration.json'
        map1, map2 = None, None
        if json_path.exists() and load_fisheye_maps is not None:
            if actual_w == target_w and actual_h == target_h:
                map1, map2 = load_fisheye_maps(str(json_path), (target_w, target_h))
                print("> 去畸变矩阵加载成功！")

        # --- 舵机初始化 ---
        print(f"> 正在连接舵机驱动板 {COM_PORT} ...")
        servo = HA8U25M_Servo(port=COM_PORT, baudrate=115200)
            
        online_ids = servo.scan_servos(max_id=10)
        for sid in SERVO_IDS:
            if sid not in online_ids:
                print(f"【严重警告】舵机 {sid} 不在线！")
                return
                
        print("> 舵机全部在线，执行回零初始化...")
        for sid in SERVO_IDS:
            servo.set_multi_turn_angle_time(sid, 0.0, 1500)
        time.sleep(1.5)

        print("\n>>> 系统就绪！")
        print(" - YOLO已经接管第一关节，正在追踪海参！")
        print(" - 第二关节由键盘【上/下/左/右】方向键进行手动微调！")
        
        # ！！！直接调用你写好的跟踪循环，并注入我们的控制回调函数！！！
        run_servo_tracking_loop(model, cap, is_camera=True, map1=map1, map2=map2, fps_delay=1, 
                                servo_callback=visual_servo_callback,
                                record_video=DATA_COLLECTION_MODE,
                                plot_curve=DATA_COLLECTION_MODE)

    except Exception as e:
        print("\n运行中发生异常:")
        traceback.print_exc()
    finally:
        print("\n正在执行安全退出程序...")
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        
        if servo is not None:
            print("> 正在使所有关节缓慢回归静息(直立)位置...")
            try:
                # 给定 2000ms 缓慢回正，防止突然断电软体臂瞬间弹起
                for sid in SERVO_IDS:
                    servo.set_multi_turn_angle_time(sid, 0.0, 2000)
                time.sleep(2.2) # 稍微多等 0.2 秒确保走到位
            except Exception as e:
                print(f"回正过程出现异常: {e}")
                
            print("> 正在彻底释放舵机电气锁定...")
            for sid in SERVO_IDS:
                try:
                    servo.release_lock(sid)
                except:
                    pass

if __name__ == '__main__':
    main()
