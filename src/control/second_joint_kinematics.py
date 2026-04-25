import math
import numpy as np

# ==========================================
# 第二关节物理参数定义
# ==========================================
L = 426.0       # 第二关节总有效长度 (mm)
R = 40.0        # 驱动绳孔位半径 (mm)
R_W = 6.5       # 绕线轮半径 (mm)

# ==========================================
# 驱动绳极角位置定义 (数学逆时针正方向, 弧度)
# 基坐标系 +x 轴沿支撑线1方向
# ==========================================
ALPHA_4 = 40.0 * math.pi / 180.0     # 绳4：40度 = 2π/9 rad
ALPHA_5 = -80.0 * math.pi / 180.0    # 绳5：-80度 = -4π/9 rad
ALPHA_6 = 160.0 * math.pi / 180.0    # 绳6：160度 = 8π/9 rad

# ==========================================
# 柔性机构补偿参数 (非对称收放策略)
# ==========================================
# 针对物理骨架受压变形导致的背面驱动绳严重松弛问题：
# 我们在收紧(dl>0)时按理论值执行，在放松(dl<0)时打折执行，从而强制背面绳索保持张紧力。
# 取值范围 (0.0 ~ 1.0)。1.0 代表不打折（纯理论），0.5 代表只释放理论一半的长度。
RELEASE_RATIO = 0.2  # 建议根据松弛情况在 0.3 ~ 0.8 之间调整


def motor_angle_to_tendon_delta(q4, q5, q6):
    """
    将电机旋转角度转换为驱动绳长度变化量。
    说明：q > 0 表示顺时针旋转（收紧），dl > 0 表示绳缩短。
    
    :param q4, q5, q6: 舵机 4,5,6 的旋转角度 (rad)
    :return: (dl4, dl5, dl6) 绳长变化量 (mm)
    """
    dl4 = R_W * q4
    dl5 = R_W * q5
    dl6 = R_W * q6
    return dl4, dl5, dl6

def tendon_delta_to_motor_angle(dl4, dl5, dl6):
    """
    将驱动绳长度变化量反算为电机目标角度。
    
    :param dl4, dl5, dl6: 绳长变化量 (mm)
    :return: (q4, q5, q6) 舵机 4,5,6 的目标旋转角度 (rad)
    """
    q4 = dl4 / R_W
    q5 = dl5 / R_W
    q6 = dl6 / R_W
    return q4, q5, q6

def joint_to_tendon_delta(theta, phi):
    """
    正向映射：关节变量 -> 绳长变化量
    包含结构变形导致的非对称松弛补偿。
    
    :param theta: 关节弯曲角 (rad)
    :param phi: 弯曲平面方向角 (rad)
    :return: (dl4, dl5, dl6) 绳长变化量 (mm)
    """
    dl4_raw = R * theta * math.cos(phi - ALPHA_4)
    dl5_raw = R * theta * math.cos(phi - ALPHA_5)
    dl6_raw = R * theta * math.cos(phi - ALPHA_6)
    
    # 实施非对称松放策略：拉紧(dl>0)时正常执行，释放(dl<0)时打折执行
    dl4 = dl4_raw if dl4_raw > 0 else dl4_raw * RELEASE_RATIO
    dl5 = dl5_raw if dl5_raw > 0 else dl5_raw * RELEASE_RATIO
    dl6 = dl6_raw if dl6_raw > 0 else dl6_raw * RELEASE_RATIO
    
    return dl4, dl5, dl6

def tendon_delta_to_joint(dl4, dl5, dl6):
    """
    逆向映射：绳长变化量 -> 关节变量
    
    :param dl4, dl5, dl6: 绳长变化量 (mm)
    :return: (theta, phi) 关节弯曲角与弯曲平面方向角 (rad)
    """
    # 逆向消除非对称松放策略的影响，还原回纯几何理论值以便计算姿态
    def undo_comp(dl):
        return dl if dl > 0 else dl / RELEASE_RATIO
        
    dl4_raw = undo_comp(dl4)
    dl5_raw = undo_comp(dl5)
    dl6_raw = undo_comp(dl6)
    
    # 按照等角分布推导的解析式，先求得中间变量 kx, ky
    kx = (2.0 / 3.0) * (dl4_raw * math.cos(ALPHA_4) + dl5_raw * math.cos(ALPHA_5) + dl6_raw * math.cos(ALPHA_6))
    ky = (2.0 / 3.0) * (dl4_raw * math.sin(ALPHA_4) + dl5_raw * math.sin(ALPHA_5) + dl6_raw * math.sin(ALPHA_6))
    
    theta = math.sqrt(kx**2 + ky**2) / R
    phi = math.atan2(ky, kx)
    return theta, phi

def joint_to_tip_position(theta, phi):
    """
    正向映射：关节变量 -> 末端三维位置
    
    :param theta: 关节弯曲角 (rad)
    :param phi: 弯曲平面方向角 (rad)
    :return: (x, y, z) 末端位置坐标 (mm)
    """
    # 添加防呆数值保护，当theta非常小时使用小角近似，避免出现 0 作为分母
    if theta < 1e-6:
        x = (L / 2.0) * theta * math.cos(phi)
        y = (L / 2.0) * theta * math.sin(phi)
        z = L
    else:
        x = (L / theta) * math.cos(phi) * (1 - math.cos(theta))
        y = (L / theta) * math.sin(phi) * (1 - math.cos(theta))
        z = (L / theta) * math.sin(theta)
    return x, y, z

def tip_position_to_joint(x, y, z):
    """
    逆向映射：末端三维位置 -> 关节变量
    仅依赖期望的 (x, y, z) 反解弯曲角与方向，适用于简单的位置随动控制。
    
    :param x, y, z: 期望的末端坐标 (mm)
    :return: (theta, phi) 关节弯曲角与弯曲平面方向角 (rad)
    """
    r_xy = math.sqrt(x**2 + y**2)
    phi = math.atan2(y, x)
    theta = 2.0 * math.atan2(r_xy, z)
    return theta, phi

def joint_to_rotation(theta, phi):
    """
    正向映射：关节变量 -> 末端姿态旋转矩阵 R
    采用 Rz(phi) * Ry(theta) * Rz(-phi) 定义
    
    :param theta: 关节弯曲角 (rad)
    :param phi: 弯曲平面方向角 (rad)
    :return: 3x3 旋转矩阵 (numpy.ndarray)
    """
    c_phi = math.cos(phi)
    s_phi = math.sin(phi)
    c_theta = math.cos(theta)
    s_theta = math.sin(theta)
    
    # 根据数学推导展开的矩阵元素
    R11 = c_phi**2 * c_theta + s_phi**2
    R12 = c_phi * s_phi * c_theta - c_phi * s_phi
    R13 = c_phi * s_theta
    
    R21 = c_phi * s_phi * c_theta - c_phi * s_phi
    R22 = s_phi**2 * c_theta + c_phi**2
    R23 = s_phi * s_theta
    
    R31 = -c_phi * s_theta
    R32 = -s_phi * s_theta
    R33 = c_theta
    
    return np.array([
        [R11, R12, R13],
        [R21, R22, R23],
        [R31, R32, R33]
    ])

def joint_to_pose(theta, phi):
    """
    正向映射：关节变量 -> 末端齐次位姿矩阵 T
    
    :param theta: 关节弯曲角 (rad)
    :param phi: 弯曲平面方向角 (rad)
    :return: 4x4 齐次位姿矩阵 (numpy.ndarray)
    """
    R_mat = joint_to_rotation(theta, phi)
    x, y, z = joint_to_tip_position(theta, phi)
    
    T = np.eye(4)
    T[0:3, 0:3] = R_mat
    T[0, 3] = x
    T[1, 3] = y
    T[2, 3] = z
    return T


if __name__ == '__main__':
    # 简单的模块自测：验证正向和逆向计算的闭环一致性
    print("=== 第二关节运动学模块测试 ===")
    
    # 假设一个目标位姿：末端向 X=50, Y=50 偏置
    target_x, target_y, target_z = 50.0, 50.0, 420.0
    print(f"1. 期望末端位置: x={target_x}, y={target_y}, z={target_z}")
    
    # 反解关节角
    theta, phi = tip_position_to_joint(target_x, target_y, target_z)
    print(f"2. 反解得到关节变量: theta={math.degrees(theta):.2f}°, phi={math.degrees(phi):.2f}°")
    
    # 正解回去验证位置
    calc_x, calc_y, calc_z = joint_to_tip_position(theta, phi)
    print(f"3. 正向重算末端位置: x={calc_x:.2f}, y={calc_y:.2f}, z={calc_z:.2f}")
    
    # 求所需的绳长变化
    dl4, dl5, dl6 = joint_to_tendon_delta(theta, phi)
    print(f"4. 需要的绳长变化(mm): dl4={dl4:.2f}, dl5={dl5:.2f}, dl6={dl6:.2f}")
    
    # 求舵机目标角度 (转化为度数方便直观查看)
    q4, q5, q6 = tendon_delta_to_motor_angle(dl4, dl5, dl6)
    print(f"5. 对应舵机旋转角(度): q4={math.degrees(q4):.2f}°, q5={math.degrees(q5):.2f}°, q6={math.degrees(q6):.2f}°")
    
    # 从绳长逆解回关节变量进行验证
    chk_theta, chk_phi = tendon_delta_to_joint(dl4, dl5, dl6)
    print(f"6. 从绳长逆算关节角: theta={math.degrees(chk_theta):.2f}°, phi={math.degrees(chk_phi):.2f}°")
    print("   (与步骤2的结果进行对比，看是否吻合。)")
