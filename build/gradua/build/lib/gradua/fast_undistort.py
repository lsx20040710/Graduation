#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@说明: 极简架构下的高效正畸订阅节点 (基于预计算映射表)
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import json


def scale_camera_matrix(camera_matrix, source_size, target_size):
    """按当前运行分辨率缩放内参矩阵。"""
    src_w, src_h = source_size
    dst_w, dst_h = target_size
    sx = float(dst_w) / float(src_w)
    sy = float(dst_h) / float(src_h)

    scaled = camera_matrix.copy().astype(np.float64)
    scaled[0, 0] *= sx
    scaled[0, 2] *= sx
    scaled[1, 1] *= sy
    scaled[1, 2] *= sy
    return scaled


class FastUndistortSubscriber(Node):
    def __init__(self, name):
        super().__init__(name)
        
        # 1. 创建订阅者 (保持极简)
        self.sub = self.create_subscription(
            Image, 'image_raw', self.listener_callback, 10)
        self.cv_bridge = CvBridge()
        
        # 2. 初始化映射表变量 (极其重要：千万不能在回调函数里局部声明)
        self.map_x = None
        self.map_y = None
        self.map_size = None
        
        # 3. 加载标定参数
        # TODO: 请务必把这里的路径换成你自己的 JSON 文件绝对路径！
        self.model, self.calibration_size, self.camera_matrix, self.dist_coeffs = self.load_calibration_data(
            '/home/lsx/Graduation/src/calibration/output/camera_calibration.json'
        )

    def load_calibration_data(self, path):
        """读取 JSON 文件中的模型、分辨率、内参和畸变系数。"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            model = str(data['model']).strip().lower()
            image_size = (int(data['image_width']), int(data['image_height']))
            mtx = np.array(data['camera_matrix'], dtype=np.float64)
            dist = np.array(data['distortion_coeffs'], dtype=np.float64).reshape(-1, 1)
            self.get_logger().info('成功加载标定参数！')
            return model, image_size, mtx, dist
        except Exception as e:
            self.get_logger().error(f'读取标定文件失败: {e}')
            return 'standard', (1, 1), np.eye(3), np.zeros((5, 1))

    def build_undistort_map(self, image_size):
        """根据标定模型和当前分辨率生成映射表。"""
        w, h = image_size
        scaled_camera_matrix = scale_camera_matrix(
            self.camera_matrix,
            self.calibration_size,
            image_size,
        )

        if self.model == 'fisheye':
            # fisheye 标定必须走 fisheye 专用接口，否则画面会明显拉扯变形。
            new_camera_matrix = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
                scaled_camera_matrix,
                self.dist_coeffs,
                (w, h),
                np.eye(3),
                balance=0.0,
            )
            self.map_x, self.map_y = cv2.fisheye.initUndistortRectifyMap(
                scaled_camera_matrix,
                self.dist_coeffs,
                np.eye(3),
                new_camera_matrix,
                (w, h),
                cv2.CV_16SC2,
            )
        else:
            newcameramtx, _ = cv2.getOptimalNewCameraMatrix(
                scaled_camera_matrix,
                self.dist_coeffs,
                (w, h),
                0,
                (w, h),
            )
            self.map_x, self.map_y = cv2.initUndistortRectifyMap(
                scaled_camera_matrix,
                self.dist_coeffs,
                None,
                newcameramtx,
                (w, h),
                cv2.CV_16SC2,
            )

        self.map_size = image_size

    def listener_callback(self, data):
        # 将 ROS 的图像消息转化成 OpenCV 图像
        image = self.cv_bridge.imgmsg_to_cv2(data, 'bgr8')
        
        # --- 核心工程优化区 ---
        # 只在接收到第一帧时，根据画面的实际长宽来计算映射表
        h, w = image.shape[:2]
        current_size = (w, h)
        if self.map_x is None or self.map_size != current_size:
            h, w = image.shape[:2]
            self.get_logger().info(f'检测到分辨率 {w}x{h}，正在生成硬件查找表...')
            self.build_undistort_map(current_size)
            self.get_logger().info('查找表生成完毕，开启高速正畸！')
            
        # 每一帧只做极低开销的像素映射搬运
        undistorted_img = cv2.remap(image, self.map_x, self.map_y, cv2.INTER_LINEAR)
        # ----------------------

        # 使用 OpenCV 显示处理后的图像效果
        cv2.imshow("Fast Undistort", undistorted_img)
        # 将延时从 10ms 改为 1ms，最大限度释放当前线程，避免阻塞 ROS 底层收包
        cv2.waitKey(1) 

def main(args=None):
    rclpy.init(args=args)
    node = FastUndistortSubscriber("fast_undistort_sub")
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
