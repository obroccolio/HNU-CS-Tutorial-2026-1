# HNU-CSCoversation-2026-1

这是一个面向课程展示与实验演示的仓库，目前包含两个相对独立的主题：

1. `audio/`：音频频谱隐写实验
2. `shellcode/`：基于 C 语言的 Shellcode / NX 绕过演示

仓库中既保留了源码，也保留了部分实验输出文件、图片和讲解材料，方便直接展示、复现实验过程。

## 目录结构

```text
.
├── audio/
│   ├── stego_audio.py
│   ├── audio_original.wav
│   ├── audio_stego.wav
│   ├── spectrogram_comparison.png
│   ├── encoding_principle.png
│   └── 音频频谱隐写_技术实现报告.docx
└── shellcode/
    ├── shellcode_hnu.c
    ├── Shellcode_demo.ipynb
    └── shellcode_hnu
```

## 项目一：音频频谱隐写

### 实验简介

`audio/stego_audio.py` 的核心思路是把一段文本或 Logo 位图映射到音频的“时间 - 频率”平面中：

- 横轴对应位图的列
- 纵轴对应位图的行
- 对值为 `1` 的像素，在指定时间窗和高频槽位注入微弱正弦波
- 最终在频谱图视图中显示隐藏内容

默认隐写频段位于 `18kHz ~ 19.8kHz`，尽量降低人耳感知，同时保留在频谱图中的可见性。

### Python 依赖

- Python 3.10 及以上
- `numpy`
- `scipy`
- `matplotlib`
- `Pillow`

安装方式：

```bash
pip install numpy scipy matplotlib pillow
```

### 快速运行

在仓库根目录执行：

```bash
python3 audio/stego_audio.py
```

这会使用脚本内置背景音频，默认写入消息：

```text
I Love Hunan University!
```

### 常用用法

写入自定义文字：

```bash
python3 audio/stego_audio.py --message "HELLO HNU"
```

使用自己的 WAV 作为载体音频：

```bash
python3 audio/stego_audio.py --input path/to/input.wav --duration 12
```

写入 Logo 图像：

```bash
python3 audio/stego_audio.py --logo path/to/logo.png
```

指定输出目录：

```bash
python3 audio/stego_audio.py --output-dir output
```

### 主要输出文件

运行后默认会在 `audio/` 目录下生成或覆盖以下文件：

- `audio_original.wav`：原始载体音频
- `audio_stego.wav`：嵌入隐写信息后的音频
- `spectrogram_comparison.png`：原始音频与隐写音频的频谱对比图
- `encoding_principle.png`：编码原理示意图

仓库中已经保留了一组示例输出，可直接用于展示。

### 脚本特性

- 支持文本点阵编码和 Logo 位图编码两种模式
- 支持输入外部 WAV，并自动重采样到 `44100 Hz`
- 自动生成频谱对比图和编码原理图
- 输出简单的信噪比（SNR）分析结果

### 相关材料

- `audio/音频频谱隐写_技术实现报告.docx`
- `audio/spectrogram_zoom.png`
- `audio/audio_original.pkf`
- `audio/audio_stego.pkf`

## 项目二：Shellcode / NX 绕过演示

### 实验简介

`shellcode/shellcode_hnu.c` 演示了一个经典的底层实验流程：

1. 将一段机器码放入 `unsigned char` 数组
2. 通过 `sysconf(_SC_PAGESIZE)` 获取页大小
3. 对齐到数组所在内存页的起始地址
4. 使用 `mprotect` 把该页改成 `PROT_READ | PROT_WRITE | PROT_EXEC`
5. 把数组强制转换成函数指针并执行

执行后，程序会通过 `sys_write` 打印：

```text
I Love Hunan University!
```

### 适用环境

- Linux x86_64
- `gcc`

说明：

- 该实验中的机器码与系统调用约定针对 Linux x86_64 编写
- 在 macOS 或非 x86_64 环境下，不能保证可以按预期运行
- 更适合作为受控环境下的体系结构与操作系统机制演示

### 编译与运行

```bash
cd shellcode
gcc shellcode_hnu.c -o shellcode_hnu
./shellcode_hnu
```

### 预期输出

程序运行时会打印 shellcode 地址、页对齐地址，以及执行结果，例如：

```text
[*] System Hacker Mode Activated
[*] Shellcode address: 0x...
[*] Page start address: 0x...
[+] NX Bit bypassed successfully using mprotect!
[+] Executing data array as machine instructions...

I Love Hunan University!

[+] Execution finished safely.
```

### 配套讲解材料

- `shellcode/Shellcode_demo.ipynb`：适合在 Jupyter 中逐步展示和讲解
- `shellcode/shellcode_hnu.c`：实验源码

## 使用建议

- 如果你是做课堂展示，建议直接使用仓库中现成的图片、音频和 Notebook。
- 如果你是做复现实验，建议先运行 `audio/stego_audio.py`，再在频谱软件中观察隐写效果。
- `shellcode` 部分建议仅在 Linux 实验环境中运行，并明确区分“教学演示”与“真实攻击”。

## 说明

本仓库内容主要用于课程实验、技术演示与原理讲解。

- `audio/` 更偏向数字信号处理与信息隐藏展示
- `shellcode/` 更偏向操作系统、体系结构和底层执行机制展示

如果后续还要继续扩展，我比较建议再补两个内容：

1. `requirements.txt`，方便一键安装 Python 依赖
2. 演示截图或 GIF，方便 GitHub 首页直接预览效果
