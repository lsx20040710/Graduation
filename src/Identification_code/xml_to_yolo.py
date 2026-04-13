import xml.etree.ElementTree as ET
import os
import glob

# ==========================================
# 核心配置区 (请根据您的实际路径修改)
# ==========================================
# 您的 XML 文件存放目录 (假设目前和图片放在一起，或者单独建了一个 xml_labels 文件夹)
XML_DIR = 'raw_data/xmls'  
# 转换后的 YOLO TXT 存放目录
TXT_DIR = 'raw_data/yolo_txts' 

# 定义您的物理类别字典 (非常重要，YOLO 只认数字)
# 假设 0 代表塑料袋，1 代表塑料瓶
CLASSES = {
    "seacucumber": 0,
}

def convert_box_to_yolo(size, box):
    """
    执行核心的几何降维与归一化计算
    size: (image_width, image_height)
    box: (xmin, xmax, ymin, ymax)
    """
    dw = 1.0 / size[0]
    dh = 1.0 / size[1]
    
    # 计算中心点
    x_center = (box[0] + box[1]) / 2.0
    y_center = (box[2] + box[3]) / 2.0
    
    # 计算宽高
    width = box[1] - box[0]
    height = box[3] - box[2]
    
    # 归一化处理
    x_center = x_center * dw
    width = width * dw
    y_center = y_center * dh
    height = height * dh
    
    # 严密的边界防护：防止坐标由于标注失误溢出 0~1 的范围
    x_center, y_center = max(0, min(1, x_center)), max(0, min(1, y_center))
    width, height = max(0, min(1, width)), max(0, min(1, height))
    
    return (x_center, y_center, width, height)

def convert_annotation(xml_path):
    # 解析 XML 树结构
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # 提取图像真实的宽、高信息
    size = root.find('size')
    w = int(size.find('width').text)
    h = int(size.find('height').text)
    
    if w == 0 or h == 0:
        print(f"[警告] {xml_path} 尺寸为 0，已跳过。")
        return

    # 准备写入对应的 TXT 文件
    basename = os.path.basename(xml_path)
    txt_filename = os.path.splitext(basename)[0] + '.txt'
    txt_path = os.path.join(TXT_DIR, txt_filename)
    
    has_valid_object = False
    
    with open(txt_path, 'w', encoding='utf-8') as out_file:
        for obj in root.iter('object'):
            difficult = obj.find('difficult').text if obj.find('difficult') is not None else '0'
            cls_name = obj.find('name').text.lower() # 统一转小写，防止大小写不一致
            
            # 如果类别不在我们的字典里，或者被标记为极其困难的样本，则丢弃
            if cls_name not in CLASSES or int(difficult) == 1:
                continue
                
            cls_id = CLASSES[cls_name]
            xmlbox = obj.find('bndbox')
            
            # 提取绝对坐标
            b = (float(xmlbox.find('xmin').text), 
                 float(xmlbox.find('xmax').text), 
                 float(xmlbox.find('ymin').text), 
                 float(xmlbox.find('ymax').text))
                 
            # 调用数学转换函数
            bb = convert_box_to_yolo((w, h), b)
            
            # 写入单行数据：class_id x y w h
            out_file.write(f"{cls_id} {bb[0]:.6f} {bb[1]:.6f} {bb[2]:.6f} {bb[3]:.6f}\n")
            has_valid_object = True
            
    # 如果这个 XML 里没有我们关心的目标，把生成的空 TXT 删掉，保持数据集纯净
    if not has_valid_object:
        os.remove(txt_path)

def main():
    os.makedirs(TXT_DIR, exist_ok=True)
    xml_files = glob.glob(os.path.join(XML_DIR, '*.xml'))
    
    if len(xml_files) == 0:
        print(f"[错误] 在 {XML_DIR} 中没有找到任何 XML 文件，请检查路径！")
        return
        
    print(f">> 开始清洗数据，共发现 {len(xml_files)} 个 XML 标注文件...")
    for xml_path in xml_files:
        convert_annotation(xml_path)
    print(f">> 转换完成！所有受支持的 YOLO 格式标签已存入: {TXT_DIR}")

if __name__ == '__main__':
    main()