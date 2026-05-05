import numpy as np
import matplotlib.pyplot as plt
import os

# 配置中文字体，确保图表正常显示中文
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# 第一关节物理参数定义
# ==========================================
L = 426.0       # 第一关节总有效长度 (mm)
R = 20.0        # 第一关节驱动绳孔位半径 (mm) 2cm -> 20mm

# ==========================================
# 驱动绳极角位置定义 (数学逆时针正方向, 弧度)
# 基坐标系 +y 轴沿点一/1号舵机方向
# 俯视顺时针角 beta 转为代码数学角 alpha 的关系：alpha = 90° - beta。
# ==========================================
# 第一关节：点一0°、点二120°、点三240° (俯视顺时针)
ALPHA_1 = np.radians(90.0)       # 绳1：数学角 90°
ALPHA_2 = np.radians(-30.0)      # 绳2：数学角 -30°
ALPHA_3 = np.radians(-150.0)     # 绳3：数学角 -150°

def joint_to_tendon_delta(theta, phi):
    """
    正向映射：关节变量 -> 绳长变化量 (纯理想模型)
    dl > 0 代表缩短(收紧)，dl < 0 代表伸长(放松)
    """
    dl1 = R * theta * np.cos(phi - ALPHA_1)
    dl2 = R * theta * np.cos(phi - ALPHA_2)
    dl3 = R * theta * np.cos(phi - ALPHA_3)
    return dl1, dl2, dl3

def joint_to_tip_position(theta, phi):
    """
    正向映射：关节变量 -> 末端三维位置
    支持 numpy 数组运算
    """
    # 数值保护，防止除以 0
    theta_safe = np.where(theta < 1e-6, 1e-6, theta)
    x = (L / theta_safe) * np.cos(phi) * (1 - np.cos(theta_safe))
    y = (L / theta_safe) * np.sin(phi) * (1 - np.cos(theta_safe))
    z = (L / theta_safe) * np.sin(theta_safe)
    return x, y, z

def run_simulation():
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle('第一关节纯理想模型控制仿真：绳长变化规律 (L=426mm, R=20mm)', fontsize=16, fontweight='bold')

    # 生成从 0 到 60 度的弯曲角序列
    thetas = np.linspace(0, np.radians(60), 100)

    # ---------------------------------------------------------
    # 1. 笛卡尔操作空间控制：沿 X 轴和 Y 轴直线运动时的绳长关系
    # ---------------------------------------------------------
    
    # [1.1] 沿 X 轴移动 (Y=0)
    # X > 0 时, phi = 0
    x_pos, _, _ = joint_to_tip_position(thetas, 0)
    dl1_pos, dl2_pos, dl3_pos = joint_to_tendon_delta(thetas, 0)
    
    # X < 0 时, phi = pi
    x_neg, _, _ = joint_to_tip_position(thetas, np.pi)
    dl1_neg, dl2_neg, dl3_neg = joint_to_tendon_delta(thetas, np.pi)
    
    # 拼接并保持坐标轴从小到大
    x_all = np.concatenate([x_neg[::-1], x_pos])
    dl1_x = np.concatenate([dl1_neg[::-1], dl1_pos])
    dl2_x = np.concatenate([dl2_neg[::-1], dl2_pos])
    dl3_x = np.concatenate([dl3_neg[::-1], dl3_pos])
    
    ax1 = fig.add_subplot(2, 2, 1)
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=1.5, alpha=0.8, label='长度不变化基准线')
    ax1.plot(x_all, dl1_x, 'r-', linewidth=2, label='绳1 (90°)')
    ax1.plot(x_all, dl2_x, 'g-', linewidth=2, label='绳2 (-30°)')
    ax1.plot(x_all, dl3_x, 'b-', linewidth=2, label='绳3 (-150°)')
    ax1.set_xlabel('操作空间 X 坐标 (mm)', fontsize=12)
    ax1.set_ylabel(r'绳长变化量 $\Delta l$ (mm)', fontsize=12)
    ax1.set_title('(a) 操作空间控制：X方向位移与绳长变化量关系 (Y=0)', fontsize=13)
    ax1.grid(True, linestyle='--', alpha=0.7)
    ax1.legend()

    # [1.2] 沿 Y 轴移动 (X=0)
    # Y > 0 时, phi = pi/2
    _, y_pos, _ = joint_to_tip_position(thetas, np.pi/2)
    dl1_ypos, dl2_ypos, dl3_ypos = joint_to_tendon_delta(thetas, np.pi/2)
    
    # Y < 0 时, phi = -pi/2
    _, y_neg, _ = joint_to_tip_position(thetas, -np.pi/2)
    dl1_yneg, dl2_yneg, dl3_yneg = joint_to_tendon_delta(thetas, -np.pi/2)
    
    # 拼接
    y_all = np.concatenate([y_neg[::-1], y_pos])
    dl1_y = np.concatenate([dl1_yneg[::-1], dl1_ypos])
    dl2_y = np.concatenate([dl2_yneg[::-1], dl2_ypos])
    dl3_y = np.concatenate([dl3_yneg[::-1], dl3_ypos])
    
    ax2 = fig.add_subplot(2, 2, 2)
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=1.5, alpha=0.8, label='长度不变化基准线')
    ax2.plot(y_all, dl1_y, 'r-', linewidth=2, label='绳1 (90°)')
    ax2.plot(y_all, dl2_y, 'g-', linewidth=2, label='绳2 (-30°)')
    ax2.plot(y_all, dl3_y, 'b-', linewidth=2, label='绳3 (-150°)')
    ax2.set_xlabel('操作空间 Y 坐标 (mm)', fontsize=12)
    ax2.set_ylabel(r'绳长变化量 $\Delta l$ (mm)', fontsize=12)
    ax2.set_title('(b) 操作空间控制：Y方向位移与绳长变化量关系 (X=0)', fontsize=13)
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend()
    
    # ---------------------------------------------------------
    # 2. 关节空间控制：弯曲角 theta 和 旋转角 phi 变化时的绳长关系
    # ---------------------------------------------------------
    
    # [2.1] 随弯曲角 theta 变化 (固定 phi = 90度，即朝 +Y 方向弯曲)
    phi_fixed = np.pi / 2
    theta_deg = np.degrees(thetas)
    dl1_t, dl2_t, dl3_t = joint_to_tendon_delta(thetas, phi_fixed)
    
    ax3 = fig.add_subplot(2, 2, 3)
    ax3.axhline(y=0, color='gray', linestyle='--', linewidth=1.5, alpha=0.8, label='长度不变化基准线')
    ax3.plot(theta_deg, dl1_t, 'r-', linewidth=2, label='绳1 (90°)')
    ax3.plot(theta_deg, dl2_t, 'g-', linewidth=2, label='绳2 (-30°)')
    ax3.plot(theta_deg, dl3_t, 'b-', linewidth=2, label='绳3 (-150°)')
    ax3.set_xlabel('关节弯曲角度 $\\theta$ (度)', fontsize=12)
    ax3.set_ylabel(r'绳长变化量 $\Delta l$ (mm)', fontsize=12)
    ax3.set_title(r'(c) 关节控制：弯曲角与绳长变化关系 (固定 $\phi=90^\circ$向+Y弯曲)', fontsize=13)
    ax3.grid(True, linestyle='--', alpha=0.7)
    ax3.legend()
    
    # [2.2] 随旋转角 phi 变化 (固定 theta = 30度，模拟周向旋转扫掠)
    theta_fixed = np.radians(30)
    phis = np.linspace(-np.pi, np.pi, 200)
    phi_deg = np.degrees(phis)
    dl1_p, dl2_p, dl3_p = joint_to_tendon_delta(theta_fixed, phis)
    
    ax4 = fig.add_subplot(2, 2, 4)
    ax4.axhline(y=0, color='gray', linestyle='--', linewidth=1.5, alpha=0.8, label='长度不变化基准线')
    ax4.plot(phi_deg, dl1_p, 'r-', linewidth=2, label='绳1 (90°)')
    ax4.plot(phi_deg, dl2_p, 'g-', linewidth=2, label='绳2 (-30°)')
    ax4.plot(phi_deg, dl3_p, 'b-', linewidth=2, label='绳3 (-150°)')
    ax4.set_xlabel('弯曲方向旋转角度 $\\phi$ (度)', fontsize=12)
    ax4.set_ylabel(r'绳长变化量 $\Delta l$ (mm)', fontsize=12)
    ax4.set_title(r'(d) 关节控制：旋转角与绳长变化关系 (固定 $\theta=30^\circ$)', fontsize=13)
    ax4.set_xticks([-180, -90, 0, 90, 180])
    ax4.grid(True, linestyle='--', alpha=0.7)
    ax4.legend()

    # 调整布局与保存
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    
    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    save_path = os.path.join(script_dir, 'first_joint_simulation.png')
    plt.savefig(save_path, dpi=300)
    print(f"仿真完成，图片已保存至: {save_path}")
    
    # 尝试显示图表，如果非交互式环境也不会报错卡死
    try:
        plt.show()
    except:
        pass

if __name__ == '__main__':
    run_simulation()
