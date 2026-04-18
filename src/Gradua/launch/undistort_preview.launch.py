from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def guess_default_calibration_file() -> str:
    """尽量从当前工作区中找到默认标定文件。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "src" / "calibration" / "output" / "camera_calibration.json"
        if candidate.is_file():
            return str(candidate)
    return ""


def generate_launch_description() -> LaunchDescription:
    """暴露逐步排查去畸变链路所需的最小参数集合。"""
    return LaunchDescription(
        [
            DeclareLaunchArgument("image_topic", default_value="/camera/image_raw"),
            DeclareLaunchArgument(
                "calibration_file",
                default_value=guess_default_calibration_file(),
            ),
            DeclareLaunchArgument("alpha", default_value="0.0"),
            DeclareLaunchArgument("window_name", default_value="rectified_preview"),
            DeclareLaunchArgument("preview_rate_hz", default_value="15.0"),
            DeclareLaunchArgument("preview_mode", default_value="rectified"),
            DeclareLaunchArgument("draw_overlay", default_value="true"),
            DeclareLaunchArgument("log_every_n_frames", default_value="30"),
            DeclareLaunchArgument("bypass_rectify", default_value="false"),
            Node(
                package="gradua",
                executable="undistort_preview",
                name="undistort_preview",
                output="screen",
                parameters=[
                    {
                        "image_topic": LaunchConfiguration("image_topic"),
                        "calibration_file": LaunchConfiguration("calibration_file"),
                        "alpha": LaunchConfiguration("alpha"),
                        "window_name": LaunchConfiguration("window_name"),
                        "preview_rate_hz": LaunchConfiguration("preview_rate_hz"),
                        "preview_mode": LaunchConfiguration("preview_mode"),
                        "draw_overlay": LaunchConfiguration("draw_overlay"),
                        "log_every_n_frames": LaunchConfiguration("log_every_n_frames"),
                        "bypass_rectify": LaunchConfiguration("bypass_rectify"),
                    }
                ],
            ),
        ]
    )
