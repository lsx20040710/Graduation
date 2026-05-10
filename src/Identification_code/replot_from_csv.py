import pandas as pd
import matplotlib.pyplot as plt
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="截取视觉伺服CSV数据的有效片段并重新绘图（适用于毕业论文）")
    parser.add_argument("csv_path", type=str, help="输入的 CSV 文件路径，例如: servo_data_20260507_143637.csv")
    parser.add_argument("--start", type=float, default=0.0, help="保留数据的起始时间(秒)")
    parser.add_argument("--end", type=float, default=None, help="保留数据的结束时间(秒)，默认一直到结尾")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.csv_path):
        print(f"【错误】找不到文件: {args.csv_path}")
        return

    # 1. 读取 CSV 数据
    df = pd.read_csv(args.csv_path)
    print(f">> 成功读取数据，总行数: {len(df)}")
    print(f">> 原始时间范围: {df['Time(s)'].min():.2f}s 到 {df['Time(s)'].max():.2f}s")
    
    # 2. 截取有效数据段 (剔除掉杂乱信号)
    end_time = args.end if args.end is not None else df['Time(s)'].max()
    mask = (df['Time(s)'] >= args.start) & (df['Time(s)'] <= end_time)
    df_filtered = df[mask].copy()
    
    if df_filtered.empty:
        print("【错误】根据你设定的时间范围，截取后没有数据了！请检查 --start 和 --end。")
        return

    print(f">> 截取后剩余行数: {len(df_filtered)}")
    
    # 可选：如果希望横坐标强制从 0 开始，可以取消下面这行的注释
    # df_filtered['Time(s)'] -= df_filtered['Time(s)'].iloc[0]

    time_data = df_filtered['Time(s)'].values
    err_x = df_filtered['ErrorX(px)'].values
    err_y = df_filtered['ErrorY(px)'].values

    # 3. 重新绘制误差响应曲线
    base_name = os.path.splitext(os.path.basename(args.csv_path))[0]
    out_dir = os.path.dirname(args.csv_path) or '.'
    
    plot_path = os.path.join(out_dir, f"{base_name}_cropped_error.png")
    
    plt.figure(figsize=(10, 6))
    plt.plot(time_data, err_x, label='Error X (px)', color='r', alpha=0.8)
    plt.plot(time_data, err_y, label='Error Y (px)', color='b', alpha=0.8)
    plt.axhline(0, color='black', linestyle='--', linewidth=1)
    
    # 根据论文要求，坐标轴和标题最好简洁一点
    plt.title('Visual Servo Tracking Error Response', fontsize=14)
    plt.xlabel('Time (s)', fontsize=12)
    plt.ylabel('Pixel Error (px)', fontsize=12)
    plt.legend(loc='upper right')
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.tight_layout()
    plt.savefig(plot_path, dpi=300)
    print(f">> 裁剪后的响应曲线已保存至: {plot_path}")

    # 4. 重新绘制二维轨迹图
    plot_traj_path = os.path.join(out_dir, f"{base_name}_cropped_traj.png")
    plt.figure(figsize=(8, 8))
    plt.plot(err_x, err_y, marker='o', markersize=4, linestyle='-', color='purple', alpha=0.6, label='Trajectory')
    plt.plot(err_x[0], err_y[0], 'go', markersize=10, label='Start')
    plt.plot(err_x[-1], err_y[-1], 'ro', markersize=10, label='End')
    plt.plot(0, 0, 'k+', markersize=15, markeredgewidth=2, label='Target Center')
    plt.title('2D Image-Plane Trajectory', fontsize=14)
    plt.xlabel('Error X (px)', fontsize=12)
    plt.ylabel('Error Y (px)', fontsize=12)
    plt.axhline(0, color='black', linestyle='--', linewidth=1)
    plt.axvline(0, color='black', linestyle='--', linewidth=1)
    plt.legend(loc='best')
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(plot_traj_path, dpi=300)
    print(f">> 裁剪后的2D轨迹图已保存至: {plot_traj_path}")

if __name__ == "__main__":
    main()
