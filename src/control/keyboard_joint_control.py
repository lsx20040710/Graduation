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
    joint_to_tendon_delta,
    tendon_delta_to_motor_angle,
    motor_angle_to_tendon_delta,
    tendon_delta_to_joint
)

# ==========================================
# 总体配置
# ==========================================
COM_PORT = 'COM7'
SERVO_IDS = [4, 5, 6]

# 安全限位：因为 theta 是极坐标中的“半径（弯曲大小）”，物理上总是大于等于 0 的。
# 想要往反方向弯曲，是通过把 phi 旋转 180 度实现的，而不是把 theta 变成负的。
MAX_THETA_DEG = 60.0
MIN_THETA_DEG = 0.0

# 单次触发的步长 (度)
STEP_THETA = 1.0
STEP_PHI = 2.0

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
            print(f"【严重警告】舵机 ID {sid} 不在线，无法启动闭环控制！")
            return
    print("舵机全部在线。")

    # 2. 初始回零 (Homing)
    print("正在执行自动回零（直立状态）...")
    for sid in SERVO_IDS:
        # 下发 0 度，用 1500 毫秒平滑到达
        servo.set_multi_turn_angle_time(sid, 0.0, 1500)
    
    # 稍微等它们转完
    time.sleep(1.5)
    
    # 初始化我们的目标状态变量
    target_theta_deg = 0.0
    target_phi_deg = 0.0

    print("\n==================================")
    print("        控制初始化完毕！        ")
    print(" [↑] / [↓] : 增大/减小 弯曲角 Theta (0~60°)")
    print(" [←] / [→] : 顺/逆时针 调整弯曲平面方向 Phi (-180~180°)")
    print(" [ESC] : 退出程序")
    print("==================================\n")

    try:
        while True:
            if keyboard.is_pressed('esc'):
                print("\n收到退出指令，释放舵机扭矩并退出...")
                for sid in SERVO_IDS:
                    servo.release_lock(sid)
                break
            
            changed = False
            
            # 检测按键
            if keyboard.is_pressed('up'):
                target_theta_deg += STEP_THETA
                changed = True
            if keyboard.is_pressed('down'):
                target_theta_deg -= STEP_THETA
                changed = True
            if keyboard.is_pressed('left'):
                # 根据数学约定，逆时针为正
                target_phi_deg += STEP_PHI  
                changed = True
            if keyboard.is_pressed('right'):
                target_phi_deg -= STEP_PHI
                changed = True
                
            if changed:
                # -----------------------
                # 数值约束与安全限位
                # -----------------------
                if target_theta_deg > MAX_THETA_DEG:
                    target_theta_deg = MAX_THETA_DEG
                elif target_theta_deg < MIN_THETA_DEG:
                    target_theta_deg = MIN_THETA_DEG
                    
                # 将 phi 规范化到 (-180, 180] 之间
                if target_phi_deg > 180.0:
                    target_phi_deg -= 360.0
                elif target_phi_deg <= -180.0:
                    target_phi_deg += 360.0
                    
                # -----------------------
                # 正向运动学解算下发
                # -----------------------
                theta_rad = math.radians(target_theta_deg)
                phi_rad = math.radians(target_phi_deg)
                
                # 算绳长
                dl4, dl5, dl6 = joint_to_tendon_delta(theta_rad, phi_rad)
                # 算舵机目标角 (无极性翻转，正如之前测试的正角=顺时针=收紧)
                q4, q5, q6 = tendon_delta_to_motor_angle(dl4, dl5, dl6)
                
                # 转换为度
                deg4 = math.degrees(q4)
                deg5 = math.degrees(q5)
                deg6 = math.degrees(q6)
                
                # 下发指令，time_ms=100 实现平滑随动跟手
                servo.set_multi_turn_angle_time(4, deg4, 100)
                servo.set_multi_turn_angle_time(5, deg5, 100)
                servo.set_multi_turn_angle_time(6, deg6, 100)
                
                # -----------------------
                # 反向运动学回读与解算
                # -----------------------
                st4 = servo.read_full_status(4)
                st5 = servo.read_full_status(5)
                st6 = servo.read_full_status(6)
                
                if st4 and st5 and st6:
                    # 真实舵机当前角度(转弧度)
                    real_q4 = math.radians(st4['angle_deg'])
                    real_q5 = math.radians(st5['angle_deg'])
                    real_q6 = math.radians(st6['angle_deg'])
                    
                    # 转真实绳长
                    real_dl4, real_dl5, real_dl6 = motor_angle_to_tendon_delta(real_q4, real_q5, real_q6)
                    # 转真实关节角
                    real_theta, real_phi = tendon_delta_to_joint(real_dl4, real_dl5, real_dl6)
                    
                    # 打印覆盖输出 (注意：由于串口有延迟，这里读到的可能是舵机正在移动中的状态，这恰恰是真正的闭环实时状态)
                    print(f"\r[目标] T:{target_theta_deg:5.1f} P:{target_phi_deg:6.1f} | [真实反算] T:{math.degrees(real_theta):5.1f} P:{math.degrees(real_phi):6.1f}   ", end="", flush=True)
                
                # 为防止发包过快导致串口塞车，适当延时（相当于 20Hz 控制频率）
                time.sleep(0.05)
            else:
                # 没按键时降低CPU占用
                time.sleep(0.02)
                
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，释放舵机...")
        for sid in SERVO_IDS:
            servo.release_lock(sid)

if __name__ == '__main__':
    main()
