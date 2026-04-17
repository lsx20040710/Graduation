from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def guess_default_calibration_file() -> str:
    """尽量从当前仓库中找到 calibration 导出的默认 JSON 文件。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "src" / "calibration" / "output" / "camera_calibration.json"
        if candidate.is_file():
            return str(candidate)
    return ""


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument("image_topic", default_value="/image_raw"),
            DeclareLaunchArgument(
                "calibration_file",
                default_value=guess_default_calibration_file(),
            ),
            DeclareLaunchArgument("alpha", default_value="0.0"),
            DeclareLaunchArgument("window_name", default_value="rectified_preview"),
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
                    }
                ],
            ),
        ]
    )
