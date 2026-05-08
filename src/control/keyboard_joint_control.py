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
MAX_THETA_DEG = 45.0
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

    # 新增：用于低通滤波（EMA）的平滑状态变量
    smooth_theta_deg = target_theta_deg
    smooth_phi_deg = target_phi_deg

    # 滤波系数 alpha (0 < alpha <= 1)
    ALPHA = 0.15

    print("\n==================================")
    print("        控制初始化完毕！        ")
    print(" [↑] / [↓] : 增大/减小 弯曲角 Theta (0~60°)")
    print(" [←] / [→] : 逆/顺时针 调整弯曲平面方向 Phi (-180~180°)")
    print(" 坐标约定：Phi=90° 对应点一/1号舵机方向，也就是当前相机 +Y")
    print(" [ESC] : 退出程序")
    print("==================================\n")

    try:
        while True:
            if keyboard.is_pressed('esc'):
                print("\n收到退出指令，准备退出...")
                break
            
            changed = False
            
            # 检测按键
            if keyboard.is_pressed('up'):
                target_theta_deg += STEP_THETA
            if keyboard.is_pressed('down'):
                target_theta_deg -= STEP_THETA
            if keyboard.is_pressed('left'):
                # 根据数学约定，逆时针为正
                target_phi_deg += STEP_PHI  
            if keyboard.is_pressed('right'):
                target_phi_deg -= STEP_PHI
                
            # -----------------------
            # 数值约束与安全限位 (针对目标)
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
            # 新增：一阶低通滤波 (处理 Phi 的翻转需要特别注意就近原则，但我们简单平滑即可)
            # -----------------------
            # 为了防止跨越 180 -> -180 的突变导致滤波器抽风，先计算角度差
            diff_phi = target_phi_deg - smooth_phi_deg
            if diff_phi > 180.0:
                diff_phi -= 360.0
            elif diff_phi < -180.0:
                diff_phi += 360.0
                
            smooth_theta_deg = ALPHA * target_theta_deg + (1 - ALPHA) * smooth_theta_deg
            smooth_phi_deg = smooth_phi_deg + ALPHA * diff_phi
            
            # 将平滑后的 phi 也规范化
            if smooth_phi_deg > 180.0:
                smooth_phi_deg -= 360.0
            elif smooth_phi_deg <= -180.0:
                smooth_phi_deg += 360.0

            # -----------------------
            # 只有当平滑目标未到达或有按键按下时，才执行下发
            # -----------------------
            if abs(smooth_theta_deg - target_theta_deg) > 0.1 or abs(diff_phi) > 0.1 or keyboard.is_pressed('up') or keyboard.is_pressed('down') or keyboard.is_pressed('left') or keyboard.is_pressed('right'):
                
                # 正向运动学解算下发 (使用滤波后的 smooth 变量)
                theta_rad = math.radians(smooth_theta_deg)
                phi_rad = math.radians(smooth_phi_deg)
                
                dl4, dl5, dl6 = joint_to_tendon_delta(theta_rad, phi_rad)
                q4, q5, q6 = tendon_delta_to_motor_angle(dl4, dl5, dl6)
                
                deg4 = math.degrees(q4)
                deg5 = math.degrees(q5)
                deg6 = math.degrees(q6)
                
                # 下发指令，time_ms 从100改为稍微长一点如150，配合滤波进一步减弱抖动
                servo.set_multi_turn_angle_time(4, deg4, 150)
                servo.set_multi_turn_angle_time(5, deg5, 150)
                servo.set_multi_turn_angle_time(6, deg6, 150)
                
                # 反向运动学回读与解算
                st4 = servo.read_full_status(4)
                st5 = servo.read_full_status(5)
                st6 = servo.read_full_status(6)
                
                if st4 and st5 and st6:
                    real_q4 = math.radians(st4['angle_deg'])
                    real_q5 = math.radians(st5['angle_deg'])
                    real_q6 = math.radians(st6['angle_deg'])
                    
                    real_dl4, real_dl5, real_dl6 = motor_angle_to_tendon_delta(real_q4, real_q5, real_q6)
                    real_theta, real_phi = tendon_delta_to_joint(real_dl4, real_dl5, real_dl6)
                    
                    print(f"\r[目标] T:{target_theta_deg:5.1f} P:{target_phi_deg:6.1f} | [平滑] T:{smooth_theta_deg:5.1f} P:{smooth_phi_deg:6.1f} | [反算] T:{math.degrees(real_theta):5.1f} P:{math.degrees(real_phi):6.1f}   ", end="", flush=True)
                
                time.sleep(0.05)
            else:
                time.sleep(0.02)
                
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，准备退出...")
    except Exception as e:
        print(f"\n发生异常: {e}")
    finally:
        print("\n正在使所有关节缓慢回归静息(直立)位置...")
        try:
            for sid in SERVO_IDS:
                servo.set_multi_turn_angle_time(sid, 0.0, 2000)
            time.sleep(2.2)
        except:
            pass
        print("释放舵机...")
        for sid in SERVO_IDS:
            try:
                servo.release_lock(sid)
            except:
                pass

if __name__ == '__main__':
    main()
