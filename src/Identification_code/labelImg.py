import cv2
import os

# 1. 你的视频路径
video_path = "E:\\Desktop\\sea\\test_picture_video\\9d4a12d9a1eff4589e09ee6e27c9f80e.mp4" 
# 2. 图片保存路径（根据你的文档，必须保存在这个文件夹里）
output_dir = r"D:\\VOCdevkit\\VOC2007\\JPEGImages" 
os.makedirs(output_dir, exist_ok=True)

cap = cv2.VideoCapture(video_path)
frame_interval = 15  # 每隔15帧提取一张图片（可根据海参移动速度自行修改）
count = 0
saved_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    if count % frame_interval == 0:
        # 生成图片文件名并保存
        img_name = os.path.join(output_dir, f"video_frame_{saved_count:05d}.jpg")
        cv2.imwrite(img_name, frame)
        saved_count += 1
        
    count += 1

cap.release()
print(f"抽帧完成！共提取了 {saved_count} 张图片到 {output_dir}")