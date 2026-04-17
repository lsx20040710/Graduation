# 导入OpenCV库，用于图像和视频处理
# Import OpenCV library for image and video processing
import cv2
# 导入time模块，用于计算帧率（FPS）
# Import the time module for calculating frame rate (FPS)
import time

# 使用VideoCapture函数打开摄像头（索引为0的默认摄像头）
# Use the VideoCapture function to open the camera (default camera with index 0)
capture = cv2.VideoCapture(0) 

# 设置视频编码格式为MJPG
# Set the video encoding format to MJPG
capture.set(6, cv2.VideoWriter_fourcc('M','J','P','G'))

# 设置摄像头捕获的帧宽为640像素
# Set the frame width captured by the camera to 640 pixels
capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
# 设置摄像头捕获的帧高为480像素
# Set the frame height captured by the camera to 480 pixels
capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# 初始化帧计数器
#Initialize frame counter
frame_count = 0
# 记录开始时间，用于计算FPS
# Record start time, used to calculate FPS
start_time = time.time()

# 进入无限循环，直到按下'q'键退出
# Enter an infinite loop until you press the 'q' key to exit
while True:
    # 读取一帧图像
    # Read a frame of image
    ret, frame = capture.read()
    
    # 若读取帧失败，则跳出循环
    # If reading the frame fails, break out of the loop
    if not ret:
        break
    
    # 帧计数器递增
    # Increment frame counter
    frame_count += 1
    
    # 每隔10帧计算一次FPS
    # Calculate FPS every 10 frames
    if frame_count % 10 == 0:
        # 计算当前FPS
        # Calculate current FPS
        end_time = time.time()
        fps = frame_count / (end_time - start_time)
        # 将FPS保留两位小数
        # Round FPS to two decimal places
        fps = "{:.2f}".format(fps)
        # 在帧上添加显示FPS的文字
        # Add text showing FPS on the frame
        cv2.putText(frame, "FPS:" + str(fps), (0, 50), cv2.FONT_ITALIC, 1, (0, 255, 0), 2)
        # 显示当前帧
        # Display the current frame
        cv2.imshow('CameraPreview', frame)
        # 重置帧计数器和起始时间
        # Reset frame counter and start time
        frame_count = 0
        start_time = time.time()
        
    # 检查按键，如果按下'q'键，则退出循环
    # Check the keys, if the 'q' key is pressed, exit the loop
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
    
# 关闭摄像头
# Turn off camera
capture.release()
# 关闭所有OpenCV窗口
# Close all OpenCV windows
cv2.destroyAllWindows()

