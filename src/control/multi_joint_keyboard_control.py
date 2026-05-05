import time
import math
import sys

try:
    import keyboard
except ImportError:
    print("【错误】未找到 keyboard 库。请在终端执行 'pip install keyboard' 安装后再运行。")
    sys.exit(1)

# 导入驱动、运动学与滤波模块
from test_servo_driver import HA8U25M_Servo
from filter_utils import EMAFilter, AngularEMAFilter
from multi_joint_kinematics import (
    J1_L, J2_L,
    joint2_to_tendon_delta,
    tendon_delta_to_joint2,
    tip_position_to_joint1,
    joint1_to_tip_position,
    joint1_to_tendon_delta_coupled,
    tendon_delta_to_joint1_coupled,
    tendon_delta_to_motor_angle,
    motor_angle_to_tendon_delta
)

# ==========================================
# 总体配置
# ==========================================
COM_PORT = 'COM7'
SERVO_IDS = [1, 2, 3, 4, 5, 6]  # 控制全部 6 个舵机

# ==========================================
# 控制参数配置
# ==========================================
# 第一关节 (末端追踪，操作空间控制)
STEP_XY_1 = 5.0      # (mm)
MAX_R_1 = 150.0      # 限制第一关节 XY 偏移半径 (mm)

# 第二关节 (基座微调，关节空间控制)
STEP_THETA_2 = 1.0   # (度)
STEP_PHI_2 = 2.0     # (度)
MAX_THETA_2 = 60.0   # (度)
MIN_THETA_2 = 0.0    # (度)

# 滤波器参数 (可根据实际惯性微调)
ALPHA_J1_XY = 0.15
ALPHA_J2_ANG = 0.15

def main():
    print(f"正在连接串口 {COM_PORT} ...")
    try:
        servo = HA8U25M_Servo(port=COM_PORT, baudrate=115200)
    except Exception as e:
        print(f"无法打开串口 {COM_PORT}: {e}")
        return

    # 1. 扫描在线舵机
    print(f"检查所需舵机 {SERVO_IDS} 是否在线...")
    online_ids = servo.scan_servos(max_id=10)
    for sid in SERVO_IDS:
        if sid not in online_ids:
            print(f"【严重警告】舵机 ID {sid} 不在线，无法启动全臂控制！")
            return
    print("舵机全部在线。")

    # 2. 初始回零 (Homing)
    print("正在执行自动回零（直立状态）...")
    for sid in SERVO_IDS:
        servo.set_multi_turn_angle_time(sid, 0.0, 1500)
    time.sleep(1.5)
    
    # 3. 初始化目标状态变量与滤波器
    # --- 第一关节 (操作空间) ---
    target_x_1 = 0.0
    target_y_1 = 0.0
    ema_x_1 = EMAFilter(alpha=ALPHA_J1_XY, initial_value=0.0)
    ema_y_1 = EMAFilter(alpha=ALPHA_J1_XY, initial_value=0.0)

    # --- 第二关节 (关节空间) ---
    target_theta_2_deg = 0.0
    target_phi_2_deg = 0.0
    ema_theta_2 = EMAFilter(alpha=ALPHA_J2_ANG, initial_value=0.0)
    ema_phi_2 = AngularEMAFilter(alpha=ALPHA_J2_ANG, initial_value=0.0)

    print("\n=================================================================")
    print("                全臂联合控制测试 (带补偿与滤波) 启动完毕！           ")
    print(" --------------------------------------------------------------- ")
    print(" 【第一关节 (末端/视觉追踪测试)】 - 笛卡尔坐标 X-Y 控制")
    print("   坐标约定：+Y = 相机 +Y = 点一/1号舵机方向，+X 为俯视下相对点一顺时针90°")
    print(f"   [W] / [S] : +Y / -Y  ({STEP_XY_1} mm/次)")
    print(f"   [A] / [D] : -X / +X  ({STEP_XY_1} mm/次)")
    print(" --------------------------------------------------------------- ")
    print(" 【第二关节 (基座/人工姿态微调)】 - 极坐标 Theta-Phi 控制")
    print("   坐标约定：Phi=90° 对应点一/1号舵机方向")
    print(f"   [↑] / [↓] : 弯曲角 Theta 增/减 ({STEP_THETA_2} 度/次)")
    print(f"   [←] / [→] : 旋转角 Phi 左/右转 ({STEP_PHI_2} 度/次)")
    print(" --------------------------------------------------------------- ")
    print(" [ESC] : 退出程序并释放所有舵机")
    print("=================================================================\n")

    try:
        while True:
            if keyboard.is_pressed('esc'):
                print("\n收到退出指令，释放舵机扭矩并退出...")
                for sid in SERVO_IDS:
                    servo.release_lock(sid)
                break
            
            # -------------------------------------------------
            # 1. 键盘输入读取与目标值更新
            # -------------------------------------------------
            # 第一关节控制
            if keyboard.is_pressed('w'): target_y_1 += STEP_XY_1
            if keyboard.is_pressed('s'): target_y_1 -= STEP_XY_1
            if keyboard.is_pressed('d'): target_x_1 += STEP_XY_1
            if keyboard.is_pressed('a'): target_x_1 -= STEP_XY_1
            
            # 第一关节安全限位
            r_target_1 = math.sqrt(target_x_1**2 + target_y_1**2)
            if r_target_1 > MAX_R_1:
                scale = MAX_R_1 / r_target_1
                target_x_1 *= scale
                target_y_1 *= scale

            # 第二关节控制
            if keyboard.is_pressed('up'): target_theta_2_deg += STEP_THETA_2
            if keyboard.is_pressed('down'): target_theta_2_deg -= STEP_THETA_2
            if keyboard.is_pressed('left'): target_phi_2_deg += STEP_PHI_2
            if keyboard.is_pressed('right'): target_phi_2_deg -= STEP_PHI_2

            # 第二关节安全限位与规范化
            target_theta_2_deg = max(MIN_THETA_2, min(target_theta_2_deg, MAX_THETA_2))
            if target_phi_2_deg > 180.0: target_phi_2_deg -= 360.0
            elif target_phi_2_deg <= -180.0: target_phi_2_deg += 360.0

            # -------------------------------------------------
            # 2. 对目标值进行 EMA 平滑滤波
            # -------------------------------------------------
            smooth_x_1 = ema_x_1.update(target_x_1)
            smooth_y_1 = ema_y_1.update(target_y_1)
            
            smooth_theta_2_deg = ema_theta_2.update(target_theta_2_deg)
            smooth_phi_2_deg = ema_phi_2.update(target_phi_2_deg)
            
            # 将角度转为弧度供运动学解算使用
            smooth_theta_2_rad = math.radians(smooth_theta_2_deg)
            smooth_phi_2_rad = math.radians(smooth_phi_2_deg)

            # -------------------------------------------------
            # 3. 联合运动学解算 (带补偿)
            # -------------------------------------------------
            # a. 先算第二关节 (不受第一关节影响)
            dl4, dl5, dl6 = joint2_to_tendon_delta(smooth_theta_2_rad, smooth_phi_2_rad)
            q4, q5, q6 = tendon_delta_to_motor_angle(dl4, dl5, dl6)

            # b. 算第一关节的操作空间映射
            smooth_theta_1_rad, smooth_phi_1_rad = tip_position_to_joint1(smooth_x_1, smooth_y_1, J1_L)
            
            # c. 第一关节解算绳长 (核心！代入第二关节的状态进行补偿)
            dl1, dl2, dl3 = joint1_to_tendon_delta_coupled(
                smooth_theta_1_rad, smooth_phi_1_rad, 
                smooth_theta_2_rad, smooth_phi_2_rad
            )
            q1, q2, q3 = tendon_delta_to_motor_angle(dl1, dl2, dl3)

            # -------------------------------------------------
            # 4. 指令下发
            # -------------------------------------------------
            # 将所有舵机角转为度数
            degs = [math.degrees(q) for q in [q1, q2, q3, q4, q5, q6]]
            
            # 平滑发送 (time_ms 根据循环频率调节)
            for sid, deg in zip(SERVO_IDS, degs):
                servo.set_multi_turn_angle_time(sid, deg, 150)
            
            # -------------------------------------------------
            # 5. 反向回读状态与打印反馈 (这里为了简化终端打印，暂时只读关键状态或直接打印目标)
            # (串口频宽有限，如果每循环读 6 个舵机状态可能卡顿。可以选读，或只打印下发状态)
            # -------------------------------------------------
            print(f"\r[J1平滑XY] {smooth_x_1:5.1f}, {smooth_y_1:5.1f} | [J2平滑TP] {smooth_theta_2_deg:5.1f}°, {smooth_phi_2_deg:6.1f}°  ", end="", flush=True)

            time.sleep(0.05) # 约 20Hz 控制循环
                
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，释放舵机...")
        for sid in SERVO_IDS:
            servo.release_lock(sid)

if __name__ == '__main__':
    main()
