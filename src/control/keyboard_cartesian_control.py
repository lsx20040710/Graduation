import time
import math
import sys

try:
    import keyboard
except ImportError:
    print("【错误】未找到 keyboard 库。请在终端执行 'pip install keyboard' 安装后再运行。")
    sys.exit(1)

# 从驱动模块与解算模块导入
from test_servo_driver import HA8U25M_Servo
from second_joint_kinematics import (
    L,  # 导入常量，第二关节总长度
    tip_position_to_joint,
    joint_to_tendon_delta,
    tendon_delta_to_motor_angle,
    motor_angle_to_tendon_delta,
    tendon_delta_to_joint,
    joint_to_tip_position
)

# ==========================================
# 总体配置
# ==========================================
COM_PORT = 'COM7'
SERVO_IDS = [4, 5, 6]

# ==========================================
# 操作空间增量控制参数 (Task Space Control)
# ==========================================
STEP_XY = 5.0      # 每次按键，末端在 X 或 Y 轴上移动的距离 (mm)
MAX_R = 150.0      # 限制末端在 X-Y 平面的最大偏置半径 (mm)，防止过度弯曲导致损坏
# 解释：150mm 对应的弯曲角大约是 40度左右，处于安全范围内

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
            print(f"【严重警告】舵机 ID {sid} 不在线，无法启动控制！")
            return
    print("舵机全部在线。")

    # 2. 初始回零 (Homing)
    print("正在执行自动回零（直立状态）...")
    for sid in SERVO_IDS:
        servo.set_multi_turn_angle_time(sid, 0.0, 1500)
    time.sleep(1.5)
    
    # 3. 初始化操作空间目标状态变量
    # 刚开始时处于直立状态，XY 偏置为 0，Z 为关节长度 L
    target_x = 0.0
    target_y = 0.0
    target_z = L

    # 新增：用于低通滤波（EMA）的平滑当前坐标
    # 目的：解决机构惯性大导致的控制晃动问题
    smooth_x = target_x
    smooth_y = target_y

    # 滤波系数 alpha (0 < alpha <= 1)
    # alpha 越小越平滑，但跟随越慢。0.1~0.2 比较适合大惯性柔性机构。
    ALPHA = 0.15

    print("\n==================================================")
    print("      操作空间 (X-Y 平面) 增量控制测试启动完毕！    ")
    print(" 坐标约定：+Y = 相机 +Y = 点一/1号舵机方向，+X 为俯视下相对点一顺时针90°")
    print(f" [↑] / [↓] : 控制末端在 +Y / -Y 方向移动 ({STEP_XY} mm/次)")
    print(f" [←] / [→] : 控制末端在 -X / +X 方向移动 ({STEP_XY} mm/次)")
    print(" [ESC] : 退出程序并释放舵机")
    print("==================================================\n")

    try:
        while True:
            if keyboard.is_pressed('esc'):
                print("\n收到退出指令，释放舵机扭矩并退出...")
                for sid in SERVO_IDS:
                    servo.release_lock(sid)
                break
            
            changed = False
            
            # 检测按键，直接修改操作空间坐标（此时修改的只是理论目标点）
            if keyboard.is_pressed('up'):
                target_y += STEP_XY
            if keyboard.is_pressed('down'):
                target_y -= STEP_XY
            if keyboard.is_pressed('right'):
                target_x += STEP_XY
            if keyboard.is_pressed('left'):
                target_x -= STEP_XY
                
            # -----------------------
            # 1. 操作空间的数值约束与安全限位 (针对目标点 target)
            # -----------------------
            r_target = math.sqrt(target_x**2 + target_y**2)
            if r_target > MAX_R:
                scale = MAX_R / r_target
                target_x *= scale
                target_y *= scale
                
            # -----------------------
            # 新增：一阶低通滤波 (Exponential Moving Average)
            # 每循环一次，平滑坐标向目标坐标靠近一小步
            # -----------------------
            smooth_x = ALPHA * target_x + (1 - ALPHA) * smooth_x
            smooth_y = ALPHA * target_y + (1 - ALPHA) * smooth_y

            # 只有当平滑坐标尚未达到目标，或者有按键按下时，才下发控制
            # 这里设置一个微小的死区(0.1mm)避免无效的微小通信
            if abs(smooth_x - target_x) > 0.1 or abs(smooth_y - target_y) > 0.1 or keyboard.is_pressed('up') or keyboard.is_pressed('down') or keyboard.is_pressed('left') or keyboard.is_pressed('right'):

                # -----------------------
                # 2. 映射：操作空间 -> 关节空间 -> 驱动空间 (使用滤波后的 smooth 坐标!)
                # -----------------------
                theta_rad, phi_rad = tip_position_to_joint(smooth_x, smooth_y, target_z)
                
                dl4, dl5, dl6 = joint_to_tendon_delta(theta_rad, phi_rad)
                q4, q5, q6 = tendon_delta_to_motor_angle(dl4, dl5, dl6)
                
                deg4 = math.degrees(q4)
                deg5 = math.degrees(q5)
                deg6 = math.degrees(q6)
                
                # 下发指令，time_ms 从100改为稍微长一点如150，配合滤波进一步减弱抖动
                servo.set_multi_turn_angle_time(4, deg4, 150)
                servo.set_multi_turn_angle_time(5, deg5, 150)
                servo.set_multi_turn_angle_time(6, deg6, 150)
                
                # -----------------------
                # 3. 反向回读与解算 (验证闭环真实执行情况)
                # -----------------------
                st4 = servo.read_full_status(4)
                st5 = servo.read_full_status(5)
                st6 = servo.read_full_status(6)
                
                if st4 and st5 and st6:
                    real_q4 = math.radians(st4['angle_deg'])
                    real_q5 = math.radians(st5['angle_deg'])
                    real_q6 = math.radians(st6['angle_deg'])
                    
                    real_dl4, real_dl5, real_dl6 = motor_angle_to_tendon_delta(real_q4, real_q5, real_q6)
                    real_theta, real_phi = tendon_delta_to_joint(real_dl4, real_dl5, real_dl6)
                    real_x, real_y, real_z = joint_to_tip_position(real_theta, real_phi)
                    
                    print(f"\r[目标] X:{target_x:5.1f} Y:{target_y:5.1f} | [平滑] X:{smooth_x:5.1f} Y:{smooth_y:5.1f} | [反算] X:{real_x:5.1f} Y:{real_y:5.1f}   ", end="", flush=True)
                
                time.sleep(0.05) # 约 20Hz 的控制频率
            else:
                # 已经到达目标且无按键，休眠
                time.sleep(0.02)
                
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，释放舵机...")
        for sid in SERVO_IDS:
            servo.release_lock(sid)

if __name__ == '__main__':
    main()
