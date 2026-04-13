
import os
import glob
import random
import shutil

# --- 配置 ---
# 原始数据根目录
DATA_ROOT = 'raw_data'
# 新的数据集根目录
TARGET_ROOT = 'datasets/my_dataset'
# 验证集所占的比例
VAL_RATIO = 0.2

# --- 执行 ---
def main():
    # 确保目标文件夹存在
    train_img_dir = os.path.join(TARGET_ROOT, 'images', 'train')
    val_img_dir = os.path.join(TARGET_ROOT, 'images', 'val')
    train_label_dir = os.path.join(TARGET_ROOT, 'labels', 'train')
    val_label_dir = os.path.join(TARGET_ROOT, 'labels', 'val')

    os.makedirs(train_img_dir, exist_ok=True)
    os.makedirs(val_img_dir, exist_ok=True)
    os.makedirs(train_label_dir, exist_ok=True)
    os.makedirs(val_label_dir, exist_ok=True)

    # 获取所有图片
    img_paths = glob.glob(os.path.join(DATA_ROOT, 'images', '*.jpg'))
    random.shuffle(img_paths)

    # 计算分割点
    split_idx = int(len(img_paths) * (1 - VAL_RATIO))
    train_files = img_paths[:split_idx]
    val_files = img_paths[split_idx:]

    # 复制文件
    def copy_files(file_list, img_dir, label_dir):
        for img_path in file_list:
            basename = os.path.basename(img_path)
            name, _ = os.path.splitext(basename)
            
            # 复制图片
            shutil.copy(img_path, os.path.join(img_dir, basename))
            
            # 复制对应的标签
            label_path = os.path.join(DATA_ROOT, 'yolo_txts', name + '.txt')
            if os.path.exists(label_path):
                shutil.copy(label_path, os.path.join(label_dir, name + '.txt'))

    print(f"正在复制 {len(train_files)} 个文件到训练集...")
    copy_files(train_files, train_img_dir, train_label_dir)
    
    print(f"正在复制 {len(val_files)} 个文件到验证集...")
    copy_files(val_files, val_img_dir, val_label_dir)

    print("\n数据集划分完成！")
    print(f"训练集: {len(train_files)} | 验证集: {len(val_files)}")
    print(f"数据已存放在: {os.path.abspath(TARGET_ROOT)}")

if __name__ == '__main__':
    main()
