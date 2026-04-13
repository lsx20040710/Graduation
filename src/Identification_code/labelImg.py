"""
文件作用：
从本地视频中按固定间隔抽取图像帧，并将结果保存到脚本同目录下的
VOCdevkit/VOC2007/JPEGImages 文件夹中，便于后续使用 LabelImg 进行 VOC 标注。

主要内容：
1. 通过图形界面交互式选择本地视频文件；
2. 支持输入抽帧间隔，控制每隔多少帧保存一张图片；
3. 自动按相对路径创建 JPEGImages 目录，避免写死绝对路径。
"""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import cv2


def select_video_file():
    """
    作用：
    弹出文件选择框，让用户手动选择待抽帧的视频文件。

    返回：
    - str: 选中的视频文件绝对路径；
    - None: 用户取消选择时返回 None。
    """
    # 创建并隐藏 Tk 根窗口，只保留文件选择对话框。
    root = tk.Tk()
    root.withdraw()
    root.update()

    # 限制常见视频格式，减少误选非视频文件的概率。
    video_path = filedialog.askopenfilename(
        title="请选择需要抽帧的视频文件",
        filetypes=[
            ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
            ("所有文件", "*.*"),
        ],
    )

    # 对话框使用完成后主动销毁根窗口，避免残留空白窗口。
    root.destroy()

    if not video_path:
        return None
    return video_path


def read_frame_interval(default_interval=15):
    """
    作用：
    从命令行读取抽帧间隔，允许用户根据视频内容密度灵活调整采样频率。

    输入：
    - default_interval: 未输入时使用的默认抽帧间隔。

    返回：
    - int: 合法的正整数抽帧间隔。
    """
    user_input = input(f"请输入抽帧间隔（每隔多少帧保存一张，默认 {default_interval}）：").strip()

    # 用户直接回车时，沿用默认值，减少重复输入。
    if not user_input:
        return default_interval

    try:
        frame_interval = int(user_input)
        if frame_interval <= 0:
            raise ValueError
        return frame_interval
    except ValueError:
        # 输入非法时回退默认值，保证脚本仍可继续执行。
        print(f"输入无效，已自动使用默认抽帧间隔 {default_interval}。")
        return default_interval


def build_output_dir():
    """
    作用：
    构造图像输出目录，目录位置始终相对于当前脚本文件，
    这样即使整个文件夹被移动，保存逻辑仍然成立。

    返回：
    - Path: 抽帧图像的保存目录。
    """
    # 以脚本所在目录作为基准，而不是当前终端工作目录，避免从别处运行时路径错乱。
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "VOCdevkit" / "VOC2007" / "JPEGImages"

    # 自动创建缺失目录，避免首次运行时报路径不存在错误。
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def extract_frames(video_path, output_dir, frame_interval):
    """
    作用：
    按给定抽帧间隔读取视频，并将图像保存到指定目录。

    输入：
    - video_path: 本地视频文件路径。
    - output_dir: 图像保存目录。
    - frame_interval: 每隔多少帧保存一张图片。

    输出：
    - int: 实际保存的图片数量。
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频文件：{video_path}")

    frame_count = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            # 读取失败通常表示视频结束，直接退出循环。
            break

        if frame_count % frame_interval == 0:
            # 使用顺序编号命名图片，便于后续标注和数据集管理。
            image_name = output_dir / f"video_frame_{saved_count:05d}.jpg"
            cv2.imwrite(str(image_name), frame)
            saved_count += 1

        frame_count += 1

    # 释放视频句柄，避免文件被占用。
    cap.release()
    return saved_count

def main():
    """
    作用：
    组织脚本执行流程，依次完成视频选择、参数读取、目录准备和抽帧保存。
    """
    print("开始选择视频文件...")
    video_path = select_video_file()
    if not video_path:
        print("未选择视频文件，程序已退出。")
        return

    frame_interval = read_frame_interval(default_interval=15)
    output_dir = build_output_dir()

    print(f"已选择视频：{video_path}")
    print(f"抽帧间隔：每隔 {frame_interval} 帧保存一张")
    print(f"图片保存目录：{output_dir}")

    try:
        saved_count = extract_frames(video_path, output_dir, frame_interval)
        print(f"抽帧完成！共提取了 {saved_count} 张图片到 {output_dir}")
    except Exception as exc:
        # 统一输出异常信息，便于定位视频无法读取或保存失败等问题。
        print(f"抽帧失败：{exc}")


if __name__ == "__main__":
    main()
