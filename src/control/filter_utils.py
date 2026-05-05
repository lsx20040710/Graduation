class EMAFilter:
    """
    一阶低通滤波器（指数移动平均滤波 Exponential Moving Average）
    用于平滑控制信号，减少由于大惯性和过快控制引起的机构抖动。
    
    公式: y_t = alpha * x_t + (1 - alpha) * y_{t-1}
    其中 alpha 为平滑系数 (0 < alpha <= 1)。
    - alpha 越小，平滑效果越强，但响应越慢。
    - alpha 越大，跟随越快，但对抖动的抑制越弱。
    针对具有较大惯性矩的柔性软体臂，推荐使用 0.1 ~ 0.3 之间的值。
    """
    def __init__(self, alpha=0.15, initial_value=0.0):
        self.alpha = alpha
        self.current_value = initial_value

    def update(self, new_value):
        """
        输入新的目标值，返回平滑后的当前值
        """
        self.current_value = self.alpha * new_value + (1 - self.alpha) * self.current_value
        return self.current_value
        
    def reset(self, initial_value=0.0):
        """
        重置滤波器状态（例如发生突变需要重新对齐时使用）
        """
        self.current_value = initial_value

class AngularEMAFilter(EMAFilter):
    """
    用于角度（如 -180 到 180 度）的特殊滤波器，处理环形跨越的问题
    """
    def update(self, new_value):
        # 计算角度差，将其限制在 [-180, 180] 内
        diff = new_value - self.current_value
        if diff > 180.0:
            diff -= 360.0
        elif diff < -180.0:
            diff += 360.0
            
        self.current_value = self.current_value + self.alpha * diff
        
        # 将当前值保持在 (-180, 180] 范围内
        if self.current_value > 180.0:
            self.current_value -= 360.0
        elif self.current_value <= -180.0:
            self.current_value += 360.0
            
        return self.current_value
