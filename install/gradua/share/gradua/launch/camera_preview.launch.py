from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    # launch 文件只负责把常用运行参数暴露出来，节点逻辑仍在 Python 节点内部。
    return LaunchDescription(
        [
            # 相机设备与采集参数。
            DeclareLaunchArgument("camera_index", default_value="0"),
            # auto 模式下会按当前操作系统选择更合适的默认后端，并在失败时回退。
            DeclareLaunchArgument("backend", default_value="auto"),
            DeclareLaunchArgument("resolution", default_value=""),
            DeclareLaunchArgument("width", default_value="640"),
            DeclareLaunchArgument("height", default_value="480"),
            DeclareLaunchArgument("fps", default_value="30.0"),
            DeclareLaunchArgument("fourcc", default_value="MJPG"),
            DeclareLaunchArgument("buffer_size", default_value="1"),
            DeclareLaunchArgument("enable_image_publish", default_value="true"),
            DeclareLaunchArgument("image_topic", default_value="/camera/image_raw"),
            DeclareLaunchArgument("frame_id", default_value="camera"),
            # 图像发布频率只建议在 10 / 15 / 30 Hz 中选择。
            DeclareLaunchArgument("publish_rate_hz", default_value="15"),
            DeclareLaunchArgument("enable_preview", default_value="true"),
            DeclareLaunchArgument("show_fps", default_value="true"),
            # 节点保持最小功能：直连相机、发布原始图像，并按参数决定是否显示预览窗口。
            Node(
                package="gradua",
                executable="camera_preview",
                name="camera_preview",
                output="screen",
                parameters=[
                    {
                        "camera_index": LaunchConfiguration("camera_index"),
                        "backend": LaunchConfiguration("backend"),
                        "resolution": LaunchConfiguration("resolution"),
                        "width": LaunchConfiguration("width"),
                        "height": LaunchConfiguration("height"),
                        "fps": LaunchConfiguration("fps"),
                        "fourcc": LaunchConfiguration("fourcc"),
                        "buffer_size": LaunchConfiguration("buffer_size"),
                        "enable_image_publish": LaunchConfiguration("enable_image_publish"),
                        "image_topic": LaunchConfiguration("image_topic"),
                        "frame_id": LaunchConfiguration("frame_id"),
                        "publish_rate_hz": LaunchConfiguration("publish_rate_hz"),
                        "enable_preview": LaunchConfiguration("enable_preview"),
                        "show_fps": LaunchConfiguration("show_fps"),
                    }
                ],
            ),
        ]
    )
