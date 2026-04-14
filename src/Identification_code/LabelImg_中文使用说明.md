# LabelImg 中文使用说明

## 这份说明解决什么问题
这份文档专门对应当前仓库里的标注流程，重点说明下面几件事：

1. 在独立环境里怎么直接启动官方 `labelImg`；
2. 官方 `labelImg` 的模式切换按钮到底在哪；
3. `YOLO TXT` 和 `Pascal VOC XML` 两种模式分别怎么保存；
4. 按 `W` 键直接退出或闪退时应该怎么排查；
5. 是否建议单独建一个 Anaconda 标注环境；
6. 数据集划分时遇到无标签图片会不会报错。

---

## 一、当前仓库里的正确启动方式
你现在已经验证过，最稳妥的方式不是走仓库启动脚本，而是：

1. 单独准备一个 `Python 3.9` 的 Anaconda 标注环境；
2. 在这个环境里直接启动官方 `labelImg`；
3. 标注完成后再回到当前项目运行 `split_dataset.py` 和训练脚本。

推荐命令：

```bash
conda activate labelimg39
labelImg
```

如果本机还没有这个环境，可以这样创建：

```bash
conda create -n labelimg39 python=3.9 -y
conda activate labelimg39
python -m pip install labelImg lxml
```

当前项目里的图片目录仍然建议统一使用：

```text
raw_data/images
```

---

## 二、模式切换按钮到底在哪
你前面找不到“右下角模式切换”，不是你看漏了，而是之前项目里的提示写得不准确。

按照官方仓库说明，格式切换按钮在：

1. 官方 `labelImg` 主界面的工具栏区域；
2. `Save` 按钮的下方；
3. 按钮文字通常显示为 `PascalVOC`；
4. 点击它后可以在 `PascalVOC` 和 `YOLO` 之间切换。

也就是说：

1. 它不是右下角开关；
2. 它更接近左上到中上方的工具栏区域；
3. 如果窗口太小，工具栏折叠后会更不容易发现，建议把窗口拉大一点。

---

## 三、两种标注模式怎么用

### 1. 直接标成 YOLO TXT
这种模式更适合你现在这套训练流程。

操作步骤：

1. 在 `labelimg39` 环境里直接运行 `labelImg`；
2. 打开 `raw_data/images`；
3. 进入官方界面后，点击 `Save` 按钮下方的 `PascalVOC`，切换成 `YOLO`；
4. 按 `W` 开始画框；
5. 选中类别后保存。

这个模式有一个很重要的官方行为：

1. 生成的 `.txt` 会直接保存在图片同目录；
2. 也就是会保存在 `raw_data/images`；
3. 官方 `labelImg` 不能把 `YOLO txt` 单独保存到另一套标签目录。

所以如果你后面要划分训练集，应该让：

```bash
python split_dataset.py --image-dir raw_data/images --label-dir raw_data/images --target-root datasets/my_dataset --val-ratio 0.2
```

### 2. 保留 Pascal VOC XML
如果你只是想保留 XML 版本，也可以继续用 XML 模式。

操作步骤：

1. 在 `labelimg39` 环境里直接运行 `labelImg`；
2. 打开 `raw_data/images`；
3. 确认 `Save` 下方的格式按钮显示为 `PascalVOC`；
4. 按 `Ctrl+R`，把保存目录切到 `raw_data/xmls`；
5. 再开始画框和保存。

---

## 四、常用快捷键
这部分只保留你当前最常用的几个：

1. `W`：开始画框；
2. `Ctrl + S`：保存当前标注；
3. `Ctrl + R`：切换默认保存目录；
4. `A` / `D`：上一张 / 下一张图片；
5. `Del`：删除当前选中的框。

如果某个快捷键按下去就异常退出，优先怀疑环境和 `labelImg` 本体兼容性，而不是你的数据目录。

---

## 五、按 W 就退出，优先怎么判断
你描述的是“按 `W` 一开始画框就退出”。这个现象不一定是你操作错了，更像是 `labelImg` 本身和当前环境的兼容问题。

当前工作区里我查到的情况是：

1. 当前激活环境是 `Python 3.13.9`；
2. 当前这个环境里能查到 `PyQt5 5.15.11` 和 `lxml 5.3.0`；
3. 但当前环境里并没有查到 `labelImg` 包本体。

这说明两件事：

1. 你现在看到的官方 `labelImg`，很可能不是从当前这个环境稳定启动的；
2. 就算后续直接往当前 `Python 3.13` 里装，稳定性也不值得乐观。

另外，官方仓库的 issue 里本身就有人报告过在 Windows 上按 `W` 开始框选时直接报错退出的问题。  
所以这件事不能简单下结论说“只要是你环境太高”，但环境过新确实会把这类老项目的问题放大。

---

## 六、要不要单独建一个 Anaconda 环境
你现在已经实测过，结论可以直接落地：**要，而且 `Python 3.9` 环境更稳。**

原因很直接：

1. `labelImg` 这个项目已经比较老，兼容性不适合继续跟着你主开发环境一起漂移；
2. 你当前主环境是 `Python 3.13.9`，对于这类基于 `PyQt5` 的老工具并不稳妥；
3. 标注工具和训练环境拆开后，后面就算训练环境升级，也不会把标注工具一起带崩。

推荐直接固定成单独的 `labelimg39` 环境：

```bash
conda create -n labelimg39 python=3.9 -y
conda activate labelimg39
python -m pip install labelImg lxml
```

然后在这个环境里运行：

```bash
labelImg
```

### 为什么这里直接写成 3.9
这里不是理论推测，而是按你已经做过的实测结果来定。

当前这样写的依据是：

1. 你已经验证 `Python 3.9` 环境里直接启动官方 `labelImg` 最稳；
2. 你之前在更高版本环境里遇到了按 `W` 退出的问题；
3. 这个项目当前最重要的是先让标注流程稳定，而不是继续追版本。

---

## 七、如果你不想折腾环境
还有一个更省事的办法：

1. 直接使用官方仓库提供的 Windows 打包版；
2. 这种方式和你本机的 Python 环境耦合更少；
3. 如果你的主要目标只是稳定标注，它通常比在高版本 Python 里现装更省事。

---

## 八、我建议你的实际执行顺序
按你现在这个项目，建议这样处理：

1. 进入 `labelimg39` 环境；
2. 直接运行官方 `labelImg`；
3. 优先用 `YOLO TXT` 模式直接标注；
4. 让图片和标签都落在 `raw_data/images`；
5. 再运行 `split_dataset.py` 划分数据集。

这样最符合你现在的工作流目标：

`raw_data/images -> 直接标 YOLO txt -> 划分数据集 -> 训练`

---

## 九、无标签图片参与 split 会不会报错
按当前 [split_dataset.py](E:/Desktop/Study_for_robot/A-Graduation/src/Identification_code/split_dataset.py:115) 的实现，不会报错。

原因很直接：

1. 脚本先无条件复制图片；
2. 然后再检查同名标签文件是否存在；
3. 只有标签存在时才复制 `.txt`。

对应的关键逻辑在 [split_dataset.py](E:/Desktop/Study_for_robot/A-Graduation/src/Identification_code/split_dataset.py:121)。

这意味着：

1. 没有标签的图片仍然会进入训练集或验证集；
2. 但它不会带 `.txt` 文件；
3. 训练时它会被当成负样本，也就是“这张图里没有目标”。

这个行为本身不是错误，但有一个前提：

1. 这些无标签图片必须真的是“没有海参”；
2. 如果图片里其实有海参，只是你漏标了，那么它会把漏标目标当成背景，影响训练效果。

---

## 十、官方参考链接
下面这两个链接是你这次最值得保留的官方来源：

1. 官方仓库 README（格式切换、基本使用说明）：  
   [https://github.com/HumanSignal/labelImg](https://github.com/HumanSignal/labelImg)
2. 官方 issue，Windows 下按 `W` 开始框选时报错的案例：  
   [https://github.com/HumanSignal/labelImg/issues/811](https://github.com/HumanSignal/labelImg/issues/811)

如果你愿意，我下一步可以继续帮你做一件更实用的事：  
把 `split_dataset.py` 再补一个可选开关，比如“跳过无标签图片”或者“统计无标签图片数量并警告”。
