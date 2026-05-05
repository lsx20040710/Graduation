import math
import numpy as np

# ==========================================
# 硬件与结构配置参数
# ==========================================
R_W = 6.5       # 绕线轮半径 (mm)

# 柔性机构补偿参数 (非对称收放策略)
# 针对物理骨架受压变形导致的背面驱动绳严重松弛问题
RELEASE_RATIO = 0.2  

# ------------------------------------------
# 第一关节 (末端操作关节)
# 对应绳 1, 2, 3，由于它从底部穿到顶部，因此受第一关节和第二关节的双重影响
# ------------------------------------------
J1_L = 426.0    # 关节总有效长度 (mm)
J1_R = 20.0     # 内侧过线孔半径 (mm)

# 代码坐标系：+y 轴沿点一/1号舵机方向；机械俯视顺时针角 beta 转数学角 alpha。
# 点一、点二、点三的 beta 分别是 0°、120°、240°，对应 alpha 为 90°、-30°、-150°。
def _clockwise_to_math_angle(beta_deg):
    """
    将机械俯视顺时针角转换为代码使用的数学角。
    输入 beta_deg 以点一方向为 0°，输出 rad，并归一化到 (-180°, 180°]。
    """
    alpha_deg = 90.0 - beta_deg
    while alpha_deg <= -180.0:
        alpha_deg += 360.0
    while alpha_deg > 180.0:
        alpha_deg -= 360.0
    return math.radians(alpha_deg)


# 绳 1, 2, 3 的安装极角，对应点一、点二、点三
J1_ALPHAS = [
    _clockwise_to_math_angle(0.0),
    _clockwise_to_math_angle(120.0),
    _clockwise_to_math_angle(240.0)
]

# ------------------------------------------
# 第二关节 (基座关节)
# 对应绳 4, 5, 6，它只穿过第二关节自身，不受第一关节影响
# ------------------------------------------
J2_L = 426.0    # 关节总有效长度 (mm)
J2_R = 40.0     # 外侧过线孔半径 (mm)

# 绳 4, 5, 6 的安装极角，对应点四、点五、点六
J2_ALPHAS = [
    _clockwise_to_math_angle(40.0),
    _clockwise_to_math_angle(160.0),
    _clockwise_to_math_angle(280.0)
]

# ==========================================
# 舵机角度 与 绳长变化量 相互转换 (通用)
# ==========================================
def motor_angle_to_tendon_delta(q_a, q_b, q_c):
    """
    将电机旋转角度转换为驱动绳长度变化量。
    q > 0 表示顺时针旋转（收紧），dl > 0 表示绳缩短。
    """
    dl_a = R_W * q_a
    dl_b = R_W * q_b
    dl_c = R_W * q_c
    return dl_a, dl_b, dl_c

def tendon_delta_to_motor_angle(dl_a, dl_b, dl_c):
    """
    将驱动绳长度变化量反算为电机目标角度。
    """
    q_a = dl_a / R_W
    q_b = dl_b / R_W
    q_c = dl_c / R_W
    return q_a, q_b, q_c

# ==========================================
# 第二关节 (基座) 独立运动学
# ==========================================
def joint2_to_tendon_delta(theta2, phi2):
    """
    正向映射：关节 2 变量 -> 绳 4, 5, 6 绳长变化量
    """
    dl4_raw = J2_R * theta2 * math.cos(phi2 - J2_ALPHAS[0])
    dl5_raw = J2_R * theta2 * math.cos(phi2 - J2_ALPHAS[1])
    dl6_raw = J2_R * theta2 * math.cos(phi2 - J2_ALPHAS[2])
    
    # 实施非对称松放策略
    dl4 = dl4_raw if dl4_raw > 0 else dl4_raw * RELEASE_RATIO
    dl5 = dl5_raw if dl5_raw > 0 else dl5_raw * RELEASE_RATIO
    dl6 = dl6_raw if dl6_raw > 0 else dl6_raw * RELEASE_RATIO
    
    return dl4, dl5, dl6

def tendon_delta_to_joint2(dl4, dl5, dl6):
    """
    逆向映射：绳 4, 5, 6 绳长变化量 -> 关节 2 变量
    """
    def undo_comp(dl):
        return dl if dl > 0 else dl / RELEASE_RATIO
        
    dl4_raw = undo_comp(dl4)
    dl5_raw = undo_comp(dl5)
    dl6_raw = undo_comp(dl6)
    
    kx = (2.0 / 3.0) * (dl4_raw * math.cos(J2_ALPHAS[0]) + dl5_raw * math.cos(J2_ALPHAS[1]) + dl6_raw * math.cos(J2_ALPHAS[2]))
    ky = (2.0 / 3.0) * (dl4_raw * math.sin(J2_ALPHAS[0]) + dl5_raw * math.sin(J2_ALPHAS[1]) + dl6_raw * math.sin(J2_ALPHAS[2]))
    
    theta2 = math.sqrt(kx**2 + ky**2) / J2_R
    phi2 = math.atan2(ky, kx)
    return theta2, phi2

# ==========================================
# 第一关节 (末端) 耦合运动学
# ==========================================
def joint1_to_tendon_delta_coupled(theta1, phi1, theta2, phi2):
    """
    正向耦合映射：关节 1 和 关节 2 变量 -> 绳 1, 2, 3 绳长变化量
    因为绳 1,2,3 穿过两个关节，所以受双重影响。
    """
    # 绳长总变化 = 第一关节自身的拉扯 + 第二关节弯曲导致的连带拉扯
    dl1_raw = (J1_R * theta1 * math.cos(phi1 - J1_ALPHAS[0])) + (J1_R * theta2 * math.cos(phi2 - J1_ALPHAS[0]))
    dl2_raw = (J1_R * theta1 * math.cos(phi1 - J1_ALPHAS[1])) + (J1_R * theta2 * math.cos(phi2 - J1_ALPHAS[1]))
    dl3_raw = (J1_R * theta1 * math.cos(phi1 - J1_ALPHAS[2])) + (J1_R * theta2 * math.cos(phi2 - J1_ALPHAS[2]))
    
    # 实施非对称松放策略 (在总体变形后应用)
    dl1 = dl1_raw if dl1_raw > 0 else dl1_raw * RELEASE_RATIO
    dl2 = dl2_raw if dl2_raw > 0 else dl2_raw * RELEASE_RATIO
    dl3 = dl3_raw if dl3_raw > 0 else dl3_raw * RELEASE_RATIO
    
    return dl1, dl2, dl3

def tendon_delta_to_joint1_coupled(dl1, dl2, dl3, theta2, phi2):
    """
    逆向解耦映射：绳 1, 2, 3 绳长变化量 + 已知的关节 2 变量 -> 关节 1 变量
    用于从舵机状态反算当前第一关节的真实姿态。
    """
    def undo_comp(dl):
        return dl if dl > 0 else dl / RELEASE_RATIO
        
    dl1_total = undo_comp(dl1)
    dl2_total = undo_comp(dl2)
    dl3_total = undo_comp(dl3)
    
    # 减去由于第二关节弯曲造成的拉伸补偿量，剩下就是第一关节自己的真实弯曲量
    dl1_j1 = dl1_total - J1_R * theta2 * math.cos(phi2 - J1_ALPHAS[0])
    dl2_j1 = dl2_total - J1_R * theta2 * math.cos(phi2 - J1_ALPHAS[1])
    dl3_j1 = dl3_total - J1_R * theta2 * math.cos(phi2 - J1_ALPHAS[2])
    
    kx = (2.0 / 3.0) * (dl1_j1 * math.cos(J1_ALPHAS[0]) + dl2_j1 * math.cos(J1_ALPHAS[1]) + dl3_j1 * math.cos(J1_ALPHAS[2]))
    ky = (2.0 / 3.0) * (dl1_j1 * math.sin(J1_ALPHAS[0]) + dl2_j1 * math.sin(J1_ALPHAS[1]) + dl3_j1 * math.sin(J1_ALPHAS[2]))
    
    theta1 = math.sqrt(kx**2 + ky**2) / J1_R
    phi1 = math.atan2(ky, kx)
    return theta1, phi1

# ==========================================
# 第一关节操作空间辅助函数 (视觉伺服控制使用)
# ==========================================
def tip_position_to_joint1(x, y, z=J1_L):
    """
    逆向映射：期望的第一关节末端三维位置 (x,y,z) -> 第一关节变量 (theta1, phi1)
    """
    r_xy = math.sqrt(x**2 + y**2)
    phi1 = math.atan2(y, x)
    theta1 = 2.0 * math.atan2(r_xy, z)
    return theta1, phi1

def joint1_to_tip_position(theta1, phi1):
    """
    正向映射：第一关节变量 -> 末端三维相对位置
    """
    if theta1 < 1e-6:
        x = (J1_L / 2.0) * theta1 * math.cos(phi1)
        y = (J1_L / 2.0) * theta1 * math.sin(phi1)
        z = J1_L
    else:
        x = (J1_L / theta1) * math.cos(phi1) * (1 - math.cos(theta1))
        y = (J1_L / theta1) * math.sin(phi1) * (1 - math.cos(theta1))
        z = (J1_L / theta1) * math.sin(theta1)
    return x, y, z

if __name__ == '__main__':
    # 模块耦合解算自测
    print("=== 多关节耦合运动学模块测试 ===")
    t2, p2 = math.radians(20), math.radians(45)
    t1, p1 = math.radians(10), math.radians(-30)
    
    print(f"[设定期望值] J2(基座) T:{math.degrees(t2):.1f}° P:{math.degrees(p2):.1f}° | J1(末端) T:{math.degrees(t1):.1f}° P:{math.degrees(p1):.1f}°")
    
    # 正解计算绳长
    dl4, dl5, dl6 = joint2_to_tendon_delta(t2, p2)
    dl1, dl2, dl3 = joint1_to_tendon_delta_coupled(t1, p1, t2, p2)
    
    print(f"[正解计算出绳长] J2绳4,5,6: {dl4:.2f}, {dl5:.2f}, {dl6:.2f}")
    print(f"[正解计算出绳长] J1绳1,2,3: {dl1:.2f}, {dl2:.2f}, {dl3:.2f}")
    
    # 逆解验证闭环
    chk_t2, chk_p2 = tendon_delta_to_joint2(dl4, dl5, dl6)
    chk_t1, chk_p1 = tendon_delta_to_joint1_coupled(dl1, dl2, dl3, chk_t2, chk_p2)
    
    print(f"[逆解回算结果] J2 T:{math.degrees(chk_t2):.1f}° P:{math.degrees(chk_p2):.1f}° | J1 T:{math.degrees(chk_t1):.1f}° P:{math.degrees(chk_p1):.1f}°")
    print("闭环验证通过！")
