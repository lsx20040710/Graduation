import serial
import struct
import time

class HA8U25M_Servo:
    """
    华馨京 HA8-U25-M 舵机 Python UART 交互驱动脚本。
    集成了扫描、指定速度模式、阻尼模式以及全状态数据读取等核心功能。
    """
    def __init__(self, port, baudrate=115200, timeout=0.05):
        """
        初始化串口连接。timeout 设小一点以提升扫描效率。
        """
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(0.1)
        
    def _send_command(self, cmd_id, data):
        """底层帧发送函数（含 Checksum 校验码计算）"""
        length = len(data)
        packet = bytearray([0x12, 0x4C, cmd_id, length]) + bytearray(data)
        packet.append(sum(packet) % 256)
        self.ser.write(packet)
        self.ser.flush()

    def enable_damping(self, servo_id, power_mw=1000):
        """
        开启阻尼模式 (指令 0x09)
        """
        data = struct.pack('<BH', servo_id, int(power_mw))
        self._send_command(0x09, data)
        print(f"-> 已向 ID {servo_id} 下发阻尼模式控制指令 (PowerLimit={power_mw}mW)。")

    def release_lock(self, servo_id):
        """
        卸力释放/失锁模式 (停止指令 0x18)
        当 mode=0x00 且 power=0 时，舵机将完全释放电机电流，呈现自由状态。
        """
        # payload: id(1 Byte) + mode(1 Byte, 0x00为释放) + power(2 Bytes, 0)
        data = struct.pack('<BBH', servo_id, 0x00, 0)
        self._send_command(0x18, data)
        print(f"-> 已向 ID {servo_id} 下发电气卸力释放指令，当前由纯机械摩擦力主导。")

    def set_multi_turn_angle_time(self, servo_id, angle_deg, time_ms, power=0):
        """位置控制 (基于时间) (指令 0x0D)"""
        position = int(angle_deg * 10)
        data = struct.pack('<BiHHH', servo_id, position, int(time_ms), int(power), 0)
        self._send_command(0x0D, data)
        print(f"-> [时间控制下发] 目标 {angle_deg}° 时间 {time_ms}ms")

    def set_multi_turn_angle_speed(self, servo_id, angle_deg, speed_deg_s, accel_ms=100, decel_ms=100, power=0):
        """
        位置控制 (基于速度) (指令 0x0F)
        :param speed_deg_s: 目标速度 (度/秒)
        :param accel_ms: 匀加速毫秒数 (>=20ms生效)
        :param decel_ms: 匀减速毫秒数 (>=20ms生效)
        """
        position = int(angle_deg * 10)
        speed_units = int(speed_deg_s * 10)  # 换算至 0.1°/s 单位
        data = struct.pack('<BiHHHH', servo_id, position, speed_units, int(accel_ms), int(decel_ms), int(power))
        self._send_command(0x0F, data)
        print(f"-> [速度控制下发] 目标 {angle_deg}° 速度 {speed_deg_s}°/s")

    def read_full_status(self, servo_id):
        """
        数据监控查询 (指令 0x16)
        读取电压、电流、功率、位置等全部信息。
        """
        self.ser.reset_input_buffer()
        data = struct.pack('<B', servo_id)
        self._send_command(0x16, data)
        
        # 响应包总长度为 21 字节:
        # 0x05 0x1C 0x16 0x10 [id] [vol2] [cur2] [pwr2] [temp2] [status1] [pos4] [turns2] [checksum1]
        res = self.ser.read(21)
        if len(res) == 21 and res[0:3] == b'\x05\x1c\x16':
            if sum(res[:-1]) % 256 == res[-1]:
                # 提取有效载荷解包
                vol, cur, pwr, temp, stat, pos, turns = struct.unpack('<HHHHBih', res[5:20])
                return {
                    'voltage_mv': vol,
                    'current_ma': cur,
                    'power_mw': pwr,
                    'status': stat,
                    'angle_deg': pos / 10.0,
                    'turns': turns
                }
        return None

    def scan_servos(self, max_id=10):
        """
        扫描总线上的舵机 (通常 ID 分布在较小的数字内)
        """
        online_ids = []
        for i in range(max_id + 1):
            status = self.read_full_status(i)
            if status is not None:
                online_ids.append(i)
        return online_ids


def main():
    port = 'COM7'
    try:
        servo = HA8U25M_Servo(port=port, baudrate=115200)
    except Exception as e:
        print(f"无法打开串口 {port}: {e}")
        return

    print("===============================")
    print("开始扫描总线上的舵机 (ID 0-10) ...")
    active_ids = servo.scan_servos(max_id=10)
    
    if not active_ids:
        print("未扫描到任何在线舵机，请检查接线和供电，然后退出程序。")
        return
        
    print(f"扫描成功！发现当前在线的舵机 ID 为: {active_ids}")
    
    # 选择舵机
    while True:
        try:
            target_id_str = input(f"请输入你想操作的舵机 ID （在 {active_ids} 中选择）：")
            target_id = int(target_id_str)
            if target_id in active_ids:
                break
            else:
                print("无效的 ID，只能选择在线的舵机。")
        except ValueError:
            print("请输入一个有效数字。")
            
    print(f"\n已选中 ID: {target_id}")

    # 简单交互循环
    while True:
        print("\n===============================")
        print("请选择你要执行的测试功能：")
        print(" 1 - 查看当前舵机全部状态 (实时位置、电流、功率)")
        print(" 2 - 驱动到达指定位置 (基于时间)")
        print(" 3 - 驱动到达指定位置 (基于速度)")
        print(" 4 - 开启阻尼模式")
        print(" 5 - 卸力释放 (防机械死锁排查专用)")
        print(" q - 退出")
        print("===============================")
        choice = input("请输入选项: ").strip().lower()
        
        if choice == 'q':
            print("退出测试交互程序...")
            break
            
        elif choice == '1':
            status = servo.read_full_status(target_id)
            if status:
                print("【舵机状态返回】")
                print(f" -> 当  前  角  度: {status['angle_deg']}° (共计圈数: {status['turns']})")
                print(f" -> 实时消耗功率: {status['power_mw']} mW  (电压: {status['voltage_mv']/1000.0}V, 电流: {status['current_ma']}mA)")
                print(f" -> 底层错误状态码: {status['status']}")
            else:
                print("读取状态失败或超时。")
                
        elif choice == '2':
            try:
                angle = float(input("请输入目标角度 (如 90.0)："))
                time_val = int(input("请输入要求到达的时间(ms，如 1000)："))
                servo.set_multi_turn_angle_time(target_id, angle, time_val)
            except ValueError:
                print("输入参数不正确。")
                
        elif choice == '3':
            try:
                angle = float(input("请输入目标角度 (如 360.0)："))
                speed = float(input("请输入目标速度(度/秒，如 200)："))
                servo.set_multi_turn_angle_speed(target_id, angle, speed)
            except ValueError:
                print("输入参数不正确。")
                
        elif choice == '4':
            try:
                power_mw = input("请输入阻尼时允许的最大执行功率 mW (直接回车默认1000)：")
                power_mw = int(power_mw) if power_mw else 1000
                servo.enable_damping(target_id, power_mw=power_mw)
                print(f"请用手轻轻扭动 ID {target_id} 的输出轴，体验柔性阻尼效果。")
            except ValueError:
                print("输入参数不正确。")
                
        elif choice == '5':
            servo.release_lock(target_id)
            print("【排查测试】 此时电机内部完全不再通电产生扭矩。如果此时你依然无法用手转动，说明该电机的机械减速箱摩擦力（自锁效应）极大，而不是阻尼代码的问题。")

        else:
            print("无效选项，请重新输入。")

if __name__ == '__main__':
    main()
