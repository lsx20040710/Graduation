# 第二关节单关节映射公式整理

## 1. 当前实际对象

当前只装配 **第二关节**，因此本文件只描述第二关节的单关节模型。

- 关节总有效长度：`L = 426 mm`
- 驱动绳数量：`3`
- 驱动绳对应：`绳4、绳5、绳6`
- 驱动绳孔位半径：`R = 40 mm`
- 绕线轮半径：`r_w = 6.5 mm`
- 当前第二关节驱动绳限位位置：`426 mm`
- 后续装上第一关节后，第二关节限位位置变为：`429 mm`
- 现阶段控制验证只按 `426 mm` 计算

---

## 2. 坐标系与角度约定

## 2.1 基坐标系 `B`

定义第二关节基坐标系 `B={O,x,y,z}`：

- 原点 `O`：第二关节基座圆盘中心
- `+z` 轴：沿第二关节初始未弯曲时的中心轴线，从基座指向末端
- `+x` 轴：**沿支撑线1方向**
- `+y` 轴：按右手定则确定

> 这样定义的原因：你的摄像头动坐标初始状态要和支撑线1方向对齐，因此 `+x` 直接选为支撑线1方向。

## 2.2 编程中的角度正方向

为避免和机械结构俯视定义混淆，**代码中统一使用数学角度定义**：

- 在 `xy` 平面内，从 `+x` 轴开始，**逆时针为正**
- 关节弯曲方向角记为 `φ`
- 关节弯曲大小记为 `θ`

范围建议：

- `θ >= 0`
- `φ = atan2(ky, kx)`，自然落在 `(-π, π]`

---

## 3. 第二关节三根驱动绳在本坐标系下的角位置

原始结构定义中：

- 支撑线1方向：`80°`（俯视、顺时针定义）
- 点四：`40°`
- 点五：`160°`
- 点六：`280°`

现在把 **支撑线1** 定义为 `+x` 轴，并改成 **逆时针为正** 的数学角度后，三根绳的角位置为：

- 绳4：`α4 = +40° = 2π/9`
- 绳5：`α5 = -80° = -4π/9`
- 绳6：`α6 = +160° = 8π/9`

数值：

```text
α4 =  0.6981317008 rad
α5 = -1.3962634016 rad
α6 =  2.7925268032 rad
```

对应三角函数：

```text
cos α4 =  0.7660444431
sin α4 =  0.6427876097

cos α5 =  0.1736481777
sin α5 = -0.9848077530

cos α6 = -0.9396926208
sin α6 =  0.3420201433
```

---

## 4. 变量定义

## 4.1 关节变量

- `θ` = 单关节弯曲角，单位 `rad`
- `φ` = 弯曲平面方向角，单位 `rad`

## 4.2 绳长变化量

统一定义：

- `Δl_i > 0`：第 `i` 根绳 **缩短 / 收紧**
- `Δl_i < 0`：第 `i` 根绳 **增长 / 放松**

这里 `i ∈ {4,5,6}`。

## 4.3 电机/绕线轮角度

统一定义：

- `q_i > 0`：绕线轮 **顺时针旋转**
- `q_i < 0`：绕线轮 **逆时针旋转**

并根据你的机械说明：

- **顺时针 = 收紧**
- **逆时针 = 放松**

因此：

```math
Δl_i = r_w q_i
```

其中：

- `q_i` 用 `rad`
- `r_w = 6.5 mm`

若角度用度数 `deg`：

```math
Δl_i = r_w \cdot q_{i,\deg} \cdot \frac{\pi}{180}
```

反算：

```math
q_i = \frac{Δl_i}{r_w}
```

```math
q_{i,\deg} = \frac{Δl_i}{r_w}\cdot\frac{180}{\pi}
```

> 若代码里采用“电机正方向”与这里相反，只需整体乘 `-1` 修正。

---

## 5. 单关节常曲率模型

采用常曲率近似：

- 第二关节中心线近似为一段圆弧
- 关节长度固定为 `L = 426 mm`

圆弧半径：

```math
\rho = \frac{L}{\theta}
```

其中 `θ → 0` 时不能直接用上式，应使用极限或小角近似，见后文。

---

## 6. 正向映射：关节变量 → 绳长变化量

对任意一根半径为 `R`、角位置为 `α_i` 的驱动绳，定义：

```math
Δl_i = R \theta \cos(\phi - \alpha_i)
```

这里：

- `R = 40 mm`
- `α_i` 为该绳在基坐标系中的角位置

因此第二关节三根绳：

```math
Δl_4 = 40 \,\theta \cos(\phi - \alpha_4)
```

```math
Δl_5 = 40 \,\theta \cos(\phi - \alpha_5)
```

```math
Δl_6 = 40 \,\theta \cos(\phi - \alpha_6)
```

代入角度：

```math
Δl_4 = 40 \,\theta \cos\left(\phi - \frac{2\pi}{9}\right)
```

```math
Δl_5 = 40 \,\theta \cos\left(\phi + \frac{4\pi}{9}\right)
```

```math
Δl_6 = 40 \,\theta \cos\left(\phi - \frac{8\pi}{9}\right)
```

---

## 7. 逆向映射：绳长变化量 → 关节变量

## 7.1 推荐写法：先解中间变量 `kx, ky`

定义：

```math
k_x = R\theta \cos\phi
```

```math
k_y = R\theta \sin\phi
```

则每根绳满足：

```math
Δl_i = k_x \cos\alpha_i + k_y \sin\alpha_i
```

写成矩阵：

```math
\begin{bmatrix}
Δl_4\\
Δl_5\\
Δl_6
\end{bmatrix}
=
\begin{bmatrix}
\cos\alpha_4 & \sin\alpha_4\\
\cos\alpha_5 & \sin\alpha_5\\
\cos\alpha_6 & \sin\alpha_6
\end{bmatrix}
\begin{bmatrix}
k_x\\
k_y
\end{bmatrix}
```

记：

```math
A=
\begin{bmatrix}
\cos\alpha_4 & \sin\alpha_4\\
\cos\alpha_5 & \sin\alpha_5\\
\cos\alpha_6 & \sin\alpha_6
\end{bmatrix}
```

因为三绳等角分布，所以可直接写成闭式：

```math
k_x = \frac{2}{3}\left(Δl_4\cos\alpha_4 + Δl_5\cos\alpha_5 + Δl_6\cos\alpha_6\right)
```

```math
k_y = \frac{2}{3}\left(Δl_4\sin\alpha_4 + Δl_5\sin\alpha_5 + Δl_6\sin\alpha_6\right)
```

代入数值后：

```math
k_x = \frac{2}{3}\left(
0.7660444431\,Δl_4 +
0.1736481777\,Δl_5 -
0.9396926208\,Δl_6
\right)
```

```math
k_y = \frac{2}{3}\left(
0.6427876097\,Δl_4 -
0.9848077530\,Δl_5 +
0.3420201433\,Δl_6
\right)
```

然后：

```math
\theta = \frac{\sqrt{k_x^2+k_y^2}}{R}
```

```math
\phi = \operatorname{atan2}(k_y, k_x)
```

其中 `R = 40 mm`。

## 7.2 代码中推荐

**不要**用普通 `arctan(y/x)`，要用：

```math
\phi = \operatorname{atan2}(k_y, k_x)
```

原因：

- `atan2` 能自动区分象限
- `kx=0` 时不会出除零问题
- 更适合控制代码

---

## 8. 正向映射：关节变量 → 末端位置

在基坐标系 `B` 中，末端点位置：

```math
x = \frac{L}{\theta}\cos\phi \left(1-\cos\theta\right)
```

```math
y = \frac{L}{\theta}\sin\phi \left(1-\cos\theta\right)
```

```math
z = \frac{L}{\theta}\sin\theta
```

其中：

- `L = 426 mm`

> 注意：这里 `z = (L/θ) sinθ` 才是正确式子。不要使用论文中出现过的带 `sinφ` 的错误排版版本。

---

## 9. 正向映射：关节变量 → 末端姿态矩阵

定义：

- 先绕 `z` 轴转 `φ`
- 再绕局部 `y` 轴弯曲 `θ`
- 再绕局部 `z` 轴转 `-φ`

则末端朝向矩阵：

```math
R = R_z(\phi)\,R_y(\theta)\,R_z(-\phi)
```

展开后：

```math
R =
\begin{bmatrix}
\cos^2\phi\cos\theta+\sin^2\phi &
\cos\phi\sin\phi\cos\theta-\cos\phi\sin\phi &
\cos\phi\sin\theta\\[4pt]
\cos\phi\sin\phi\cos\theta-\cos\phi\sin\phi &
\sin^2\phi\cos\theta+\cos^2\phi &
\sin\phi\sin\theta\\[4pt]
-\cos\phi\sin\theta &
-\sin\phi\sin\theta &
\cos\theta
\end{bmatrix}
```

---

## 10. 齐次位姿矩阵

末端位姿矩阵：

```math
T =
\begin{bmatrix}
R_{11} & R_{12} & R_{13} & x\\
R_{21} & R_{22} & R_{23} & y\\
R_{31} & R_{32} & R_{33} & z\\
0 & 0 & 0 & 1
\end{bmatrix}
```

直接写成：

```math
T =
\begin{bmatrix}
\cos^2\phi\cos\theta+\sin^2\phi &
\cos\phi\sin\phi\cos\theta-\cos\phi\sin\phi &
\cos\phi\sin\theta &
\frac{L}{\theta}\cos\phi(1-\cos\theta)\\[6pt]
\cos\phi\sin\phi\cos\theta-\cos\phi\sin\phi &
\sin^2\phi\cos\theta+\cos^2\phi &
\sin\phi\sin\theta &
\frac{L}{\theta}\sin\phi(1-\cos\theta)\\[6pt]
-\cos\phi\sin\theta &
-\sin\phi\sin\theta &
\cos\theta &
\frac{L}{\theta}\sin\theta\\[6pt]
0&0&0&1
\end{bmatrix}
```

---

## 11. 逆向映射：末端位置 → 关节变量（只用位置）

若已知末端位置 `(x,y,z)`，则：

```math
r_{xy} = \sqrt{x^2+y^2}
```

```math
\phi = \operatorname{atan2}(y,x)
```

```math
\theta = 2\operatorname{atan2}(r_{xy}, z)
```

然后再代回第 6 节求三根绳的目标变化量。

> 这一组只用位置，不依赖姿态矩阵，适合简单位置控制或调试。

---

## 12. 小角度近似（推荐用于控制初期）

当 `θ` 很小，即关节轻微摆动时：

```math
1-\cos\theta \approx \frac{\theta^2}{2}
```

```math
\sin\theta \approx \theta
```

代入位置公式后得到：

```math
x \approx \frac{L}{2}\theta\cos\phi
```

```math
y \approx \frac{L}{2}\theta\sin\phi
```

```math
z \approx L
```

再结合：

```math
k_x = R\theta\cos\phi
```

```math
k_y = R\theta\sin\phi
```

得到小角线性关系：

```math
x \approx \frac{L}{2R} k_x
```

```math
y \approx \frac{L}{2R} k_y
```

由于：

- `L = 426 mm`
- `R = 40 mm`

所以：

```math
\frac{L}{2R} = \frac{426}{80} = 5.325
```

即：

```math
x \approx 5.325\,k_x
```

```math
y \approx 5.325\,k_y
```

这个关系适合做初期闭环调试，因为它是近似线性的。

---

## 13. 电机角度 ↔ 绳长变化量 ↔ 关节变量 ↔ 位姿 的完整链条

## 13.1 电机角度到绳长变化量

```math
Δl_i = r_w q_i
```

## 13.2 绳长变化量到关节变量

```math
k_x = \frac{2}{3}\sum_i Δl_i\cos\alpha_i
```

```math
k_y = \frac{2}{3}\sum_i Δl_i\sin\alpha_i
```

```math
\theta = \frac{\sqrt{k_x^2+k_y^2}}{R}
```

```math
\phi = \operatorname{atan2}(k_y, k_x)
```

## 13.3 关节变量到末端位置

```math
x = \frac{L}{\theta}\cos\phi (1-\cos\theta)
```

```math
y = \frac{L}{\theta}\sin\phi (1-\cos\theta)
```

```math
z = \frac{L}{\theta}\sin\theta
```

## 13.4 关节变量到末端姿态

```math
R = R_z(\phi)R_y(\theta)R_z(-\phi)
```

## 13.5 末端位姿矩阵

```math
T=
\begin{bmatrix}
R & p\\
0 & 1
\end{bmatrix}
```

其中：

```math
p = [x,y,z]^T
```

---

## 14. 程序实现建议

## 14.1 强烈建议统一内部符号

代码内部统一使用：

- `Δl > 0` = 收紧 / 缩短
- `q > 0` = 顺时针
- `φ` = 数学坐标系逆时针为正
- 长度单位统一 `mm`
- 角度内部统一 `rad`

## 14.2 推荐零位定义

定义零位状态：

- `q4 = q5 = q6 = 0`
- `Δl4 = Δl5 = Δl6 = 0`
- `θ = 0`
- 第二关节竖直
- 摄像头动坐标初始与本文件定义的 `B={x,y,z}` 对齐

## 14.3 推荐数值保护

当 `θ < 1e-6` 时：

- 不直接用 `L/θ`
- 改用小角近似：
  - `x ≈ (L/2) θ cosφ`
  - `y ≈ (L/2) θ sinφ`
  - `z ≈ L`

## 14.4 推荐接口划分

建议写成以下函数：

```python
motor_angle_to_tendon_delta(q4, q5, q6) -> (dl4, dl5, dl6)
```

```python
tendon_delta_to_joint(dl4, dl5, dl6) -> (theta, phi)
```

```python
joint_to_tip_position(theta, phi) -> (x, y, z)
```

```python
joint_to_rotation(theta, phi) -> R
```

```python
joint_to_pose(theta, phi) -> T
```

```python
tip_position_to_joint(x, y, z) -> (theta, phi)
```

```python
joint_to_tendon_delta(theta, phi) -> (dl4, dl5, dl6)
```

```python
tendon_delta_to_motor_angle(dl4, dl5, dl6) -> (q4, q5, q6)
```

---

## 15. 最终建议：本项目当前阶段最该使用的最小闭环链

当前阶段只有第二关节，因此最小可用链条应为：

```math
(q_4,q_5,q_6)
\rightarrow
(Δl_4,Δl_5,Δl_6)
\rightarrow
(\theta,\phi)
\rightarrow
(x,y,z)
```

若要做视觉居中控制，可先不做复杂空间轨迹，只做增量闭环：

```math
(u-u_0,\ v-v_0)
\rightarrow
(\delta q_4,\delta q_5,\delta q_6)
```

其中控制律最初可以不依赖完整视觉伺服模型，只先做经验符号校准：

- 图像目标偏左 / 偏右 → 调整 `x` 方向弯曲
- 图像目标偏上 / 偏下 → 调整 `y` 方向弯曲

等单关节解算与控制稳定后，再加入更正式的图像雅可比模型。

---

## 16. 需要特别记住的结论

1. 当前只按 **第二关节单关节模型** 编程，长度取 `426 mm`
2. 坐标系 `+x` 轴 = **支撑线1方向**
3. 绳4、绳5、绳6的本地角位置分别为：

```text
α4 =  2π/9
α5 = -4π/9
α6 =  8π/9
```

4. 正号约定：

```text
Δl_i > 0  = 收紧 / 缩短
q_i  > 0  = 顺时针旋转 = 收紧
```

5. 核心解算式：

```math
Δl_i = R\theta\cos(\phi-\alpha_i)
```

```math
k_x = \frac{2}{3}\sum_i Δl_i\cos\alpha_i
```

```math
k_y = \frac{2}{3}\sum_i Δl_i\sin\alpha_i
```

```math
\theta = \frac{\sqrt{k_x^2+k_y^2}}{R}
```

```math
\phi = \operatorname{atan2}(k_y, k_x)
```

```math
x = \frac{L}{\theta}\cos\phi(1-\cos\theta)
```

```math
y = \frac{L}{\theta}\sin\phi(1-\cos\theta)
```

```math
z = \frac{L}{\theta}\sin\theta
```
