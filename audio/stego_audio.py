"""
音频频谱隐写核心实现
原理：在音频特定时间窗口、特定频率处注入人耳不可感知的微弱正弦波
      频谱分析软件切换到 Spectrogram 视图时，这些频率点会亮起，拼出文字
"""

import os
import tempfile
import argparse
import math

os.environ.setdefault(
    'MPLCONFIGDIR',
    os.path.join(tempfile.gettempdir(), 'matplotlib-cache')
)

import numpy as np
from scipy.io import wavfile
from scipy.signal import spectrogram, resample_poly
import matplotlib
from matplotlib import font_manager
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

# ──────────────────────────────────────────
# 参数配置
# ──────────────────────────────────────────
SAMPLE_RATE   = 44100          # 采样率 (Hz)
DURATION      = 12.0           # 音频总时长 (秒)
AMPLITUDE_BG  = 0.15           # 背景音乐幅度
AMPLITUDE_MSG = 0.018          # 隐写信号幅度 (约为背景的 12%，人耳极难察觉)

# 隐写频率范围：18000~19800 Hz（高频段，人耳阈值高）
FREQ_LOW      = 18000
FREQ_HIGH     = 19800
MESSAGE       = "I Love Hunan University!"
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
LOGO_HEIGHT   = 56
LOGO_THRESHOLD = 0.90
MIN_COL_DURATION = 0.045
MARGIN_TIME = 0.5
PREVIEW_MAX_ROWS = 48
PREVIEW_MAX_COLS = 96

# 字体点阵（5×7 像素，ASCII 子集）
# 每个字符用 5 个 5-bit 整数表示，按“行”存储
FONT_5X7 = {
    'I': [0b11111, 0b00100, 0b00100, 0b00100, 0b11111],
    ' ': [0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    'L': [0b10000, 0b10000, 0b10000, 0b10000, 0b11111],
    'o': [0b01110, 0b10001, 0b10001, 0b10001, 0b01110],
    'v': [0b10001, 0b10001, 0b01010, 0b01010, 0b00100],
    'e': [0b01110, 0b10001, 0b11111, 0b10000, 0b01111],
    'H': [0b10001, 0b10001, 0b11111, 0b10001, 0b10001],
    'u': [0b10001, 0b10001, 0b10001, 0b10001, 0b01111],
    'n': [0b11000, 0b10100, 0b10010, 0b10001, 0b10001],
    'a': [0b01110, 0b00001, 0b01111, 0b10001, 0b01111],
    'U': [0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    'i': [0b01100, 0b00100, 0b00100, 0b00100, 0b01110],
    'r': [0b11000, 0b10100, 0b10000, 0b10000, 0b10000],
    's': [0b01111, 0b10000, 0b01110, 0b00001, 0b11110],
    't': [0b11111, 0b00100, 0b00100, 0b00100, 0b00011],
    'y': [0b10001, 0b10001, 0b01111, 0b00001, 0b01110],
    '!': [0b00100, 0b00100, 0b00100, 0b00000, 0b00100],
}


def configure_matplotlib():
    """配置可用中文字体，避免标题和注释显示为方块。"""
    available_fonts = {f.name for f in font_manager.fontManager.ttflist}
    fallback_fonts = [
        'Hiragino Sans GB',
        'Songti SC',
        'Arial Unicode MS',
        'DejaVu Sans',
    ]
    plt.rcParams['font.sans-serif'] = [
        font for font in fallback_fonts if font in available_fonts
    ] or ['DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False


configure_matplotlib()


def char_to_columns(ch):
    """将字符转为点阵列数据（5列，每列7行）"""
    rows = FONT_5X7.get(ch, FONT_5X7[' '])
    # 扩展为7行（5行字符 + 1行间距）
    result = []
    for col_idx in range(5):
        col = [((rows[row_idx] >> (4 - col_idx)) & 1) for row_idx in range(5)]
        col += [0, 0]  # 底部留白
        result.append(col)
    result.append([0]*7)  # 字符间空列
    return result  # list of 6 cols, each col has 7 rows


def bitmap_to_columns(bitmap):
    """将二维位图转为按列组织的数据。"""
    if bitmap.ndim != 2:
        raise ValueError("bitmap 必须是二维数组")
    return [bitmap[:, col_idx].astype(np.uint8).tolist() for col_idx in range(bitmap.shape[1])]


def columns_to_bitmap(columns):
    """将按列组织的数据还原为二维位图。"""
    if not columns:
        return np.zeros((0, 0), dtype=np.uint8)
    return np.array(columns, dtype=np.uint8).T


def resize_bitmap(bitmap, target_width=None, target_height=None):
    """使用最近邻缩放二值位图，保持硬边缘。"""
    if bitmap.ndim != 2:
        raise ValueError("bitmap 必须是二维数组")
    if target_width is None and target_height is None:
        return bitmap.astype(np.uint8)

    src_h, src_w = bitmap.shape
    if src_h == 0 or src_w == 0:
        raise ValueError("bitmap 不能为空")

    if target_width is None:
        target_width = max(1, round(src_w * target_height / src_h))
    if target_height is None:
        target_height = max(1, round(src_h * target_width / src_w))

    image = Image.fromarray((bitmap.astype(np.uint8) * 255), mode='L')
    resized = image.resize((int(target_width), int(target_height)), resample=Image.Resampling.NEAREST)
    return (np.array(resized) > 127).astype(np.uint8)


def trim_bitmap(bitmap):
    """裁掉位图四周的纯空白边界。"""
    active = np.argwhere(bitmap > 0)
    if active.size == 0:
        raise ValueError("图像没有可编码的有效像素，请检查 logo 是否过白或阈值过低")

    top, left = active.min(axis=0)
    bottom, right = active.max(axis=0) + 1
    return bitmap[top:bottom, left:right]


def build_text_bitmap(message):
    """将消息文本转换为可编码的点阵位图。"""
    all_columns = []
    for ch in message:
        all_columns.extend(char_to_columns(ch))

    bitmap = columns_to_bitmap(all_columns)
    if bitmap.size == 0:
        raise ValueError("消息不能为空")
    return bitmap


def estimate_max_columns(duration):
    """根据音频时长估计可清晰显示的最大列数。"""
    usable_duration = duration - 2 * MARGIN_TIME
    if usable_duration <= 0:
        raise ValueError("音频时长至少需要大于 1 秒")
    return max(8, int(usable_duration / MIN_COL_DURATION))


def load_logo_bitmap(logo_path, target_height=LOGO_HEIGHT, duration=DURATION,
                     threshold=LOGO_THRESHOLD, side_padding=4):
    """读取 logo 图像，去白底后转成频谱可编码的二值位图。"""
    image = Image.open(logo_path).convert('RGBA')
    white_bg = Image.new('RGBA', image.size, (255, 255, 255, 255))
    image = Image.alpha_composite(white_bg, image).convert('RGB')

    gray = np.array(image.convert('L'), dtype=np.float32) / 255.0
    ink_mask = (gray < threshold).astype(np.uint8)
    ink_mask = trim_bitmap(ink_mask)

    src_h, src_w = ink_mask.shape
    target_width = max(1, round(src_w * target_height / src_h))
    max_logo_cols = max(1, estimate_max_columns(duration) - side_padding * 2)
    if target_width > max_logo_cols:
        scale = max_logo_cols / target_width
        target_width = max_logo_cols
        target_height = max(8, round(target_height * scale))

    resized = resize_bitmap(ink_mask, target_width=target_width, target_height=target_height)
    resized = trim_bitmap(resized)

    if side_padding > 0:
        resized = np.pad(resized, ((0, 0), (side_padding, side_padding)), mode='constant')

    return resized.astype(np.uint8)


def audio_to_float32(audio):
    """将 PCM / float 音频统一转换到 [-1, 1] 浮点范围。"""
    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)
        audio = audio.astype(np.float32)
        if info.min == 0:
            midpoint = info.max / 2.0
            audio = (audio - midpoint) / max(midpoint, 1.0)
        else:
            scale = max(abs(info.min), info.max)
            audio = audio / max(scale, 1)
    else:
        audio = audio.astype(np.float32)

    return np.clip(audio, -1.0, 1.0)


def get_mono_audio(audio):
    """将多声道音频折叠为单声道，便于画图和做频谱。"""
    if audio.ndim == 1:
        return audio
    return np.mean(audio, axis=1)


def load_audio_file(input_path, target_sample_rate=SAMPLE_RATE, target_duration=None):
    """读取用户提供的 WAV，并按需要重采样/裁剪。"""
    sample_rate, audio = wavfile.read(input_path)
    audio = audio_to_float32(audio)

    if audio.ndim > 2:
        raise ValueError("仅支持单声道或立体声音频")

    original_channels = 1 if audio.ndim == 1 else audio.shape[1]

    if sample_rate != target_sample_rate:
        gcd = math.gcd(sample_rate, target_sample_rate)
        up = target_sample_rate // gcd
        down = sample_rate // gcd
        audio = resample_poly(audio, up, down, axis=0)
        sample_rate = target_sample_rate

    if target_duration is not None:
        target_samples = int(target_duration * target_sample_rate)
        if len(audio) > target_samples:
            audio = audio[:target_samples]
        elif len(audio) < target_samples:
            pad_shape = (target_samples - len(audio),) if audio.ndim == 1 else (
                target_samples - len(audio), audio.shape[1]
            )
            audio = np.concatenate(
                [audio, np.zeros(pad_shape, dtype=audio.dtype)],
                axis=0
            )

    info = {
        'sample_rate': sample_rate,
        'channels': original_channels,
        'duration': len(audio) / sample_rate,
    }
    return audio, info


def generate_background_audio(sample_rate=SAMPLE_RATE, duration=DURATION):
    """生成作为载体的背景音频。"""
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)

    audio = np.zeros(n_samples)
    for freq, amp in [(220, 0.12), (330, 0.08), (440, 0.06),
                      (550, 0.04), (660, 0.03), (880, 0.02)]:
        phase = np.random.uniform(0, 2*np.pi)
        audio += amp * np.sin(2 * np.pi * freq * t + phase)

    audio += np.random.normal(0, 0.008, n_samples)
    return audio


def encode_bitmap_to_audio(bitmap, sample_rate=SAMPLE_RATE, duration=DURATION,
                           carrier_audio=None):
    """
    核心编码函数
    将二维位图编码为频谱可见的音频信号
    
    原理：
    - 时间轴 → 位图的横向列
    - 频率轴 → 位图的纵向像素
    - 像素=1 → 在该(时间,频率)处注入微弱正弦波
    - 像素=0 → 静默
    """
    bitmap = np.array(bitmap, dtype=np.uint8)
    if bitmap.ndim != 2:
        raise ValueError("bitmap 必须是二维数组")

    if carrier_audio is None:
        n_samples = int(sample_rate * duration)
        audio = generate_background_audio(sample_rate, duration)
    else:
        audio = np.array(carrier_audio, copy=True)
        if audio.ndim > 2:
            raise ValueError("carrier_audio 仅支持单声道或立体声")
        n_samples = len(audio)
        duration = n_samples / sample_rate

    t = np.arange(n_samples) / sample_rate
    all_columns = bitmap_to_columns(bitmap)
    
    # 3. 计算时间和频率布局
    total_cols = len(all_columns)
    text_duration = duration - 2 * MARGIN_TIME
    if text_duration <= 0:
        raise ValueError("音频时长至少需要大于 1 秒")
    if total_cols == 0:
        raise ValueError("位图不能为空")
    col_duration = text_duration / total_cols  # 每列占多少秒
    
    n_rows = bitmap.shape[0]
    freq_slots = np.linspace(FREQ_LOW, FREQ_HIGH, n_rows)
    
    # 4. 逐列注入隐写信号
    for col_idx, col_data in enumerate(all_columns):
        t_start = MARGIN_TIME + col_idx * col_duration
        t_end   = t_start + col_duration * 0.85  # 留5%间隔避免频率泄漏
        
        idx_start = int(t_start * sample_rate)
        idx_end   = int(t_end   * sample_rate)
        
        for row_idx, pixel in enumerate(col_data):
            if pixel == 1:
                freq = freq_slots[n_rows - 1 - row_idx]  # 上下翻转（高频=上）
                chunk_t = t[idx_start:idx_end]
                # 加入汉宁窗，减少频谱泄漏
                window = np.hanning(len(chunk_t))
                signal = AMPLITUDE_MSG * np.sin(2 * np.pi * freq * chunk_t) * window
                if audio.ndim == 1:
                    audio[idx_start:idx_end] += signal
                else:
                    audio[idx_start:idx_end] += signal[:, np.newaxis]
    
    return audio, all_columns, freq_slots


def encode_message_to_audio(message, sample_rate=SAMPLE_RATE, duration=DURATION,
                            carrier_audio=None):
    """兼容旧接口：将文本先转换为位图，再编码到音频。"""
    bitmap = build_text_bitmap(message)
    return encode_bitmap_to_audio(
        bitmap, sample_rate=sample_rate, duration=duration, carrier_audio=carrier_audio
    )


def save_wav(audio, filename, sample_rate=SAMPLE_RATE):
    """保存为16位WAV文件"""
    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    wavfile.write(filename, sample_rate, audio_int16)
    size_kb = os.path.getsize(filename) / 1024
    print(f"  [保存] {filename}  ({size_kb:.1f} KB)")


def generate_spectrogram_comparison(audio_clean, audio_stego, sample_rate, output_path,
                                    content_label, content_mode):
    """
    生成对比频谱图：左侧原始音频，右侧隐写音频
    展示频域中文字的浮现效果
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 10),
                              facecolor='#0d0d0d')
    fig.suptitle(f'频谱隐写演示：{content_label}',
                 color='white', fontsize=16, fontweight='bold', y=0.98)

    hidden_subject = '隐藏 logo' if content_mode == 'logo' else '隐藏文字'
    
    configs = [
        (audio_clean, '原始音频 — 时域波形',  0, 0, '#4CAF50'),
        (audio_stego, '隐写音频 — 时域波形',  0, 1, '#4CAF50'),
        (audio_clean, '原始音频 — 频谱图',    1, 0, None),
        (audio_stego, f'隐写音频 — 频谱图\n（切换到此视图，{hidden_subject}现身！）', 1, 1, None),
    ]
    
    for audio, title, row, col, color in configs:
        ax = axes[row][col]
        ax.set_facecolor('#1a1a2e')
        display_audio = get_mono_audio(audio)
        
        if row == 0:  # 时域波形
            time_axis = np.linspace(0, len(display_audio)/sample_rate, len(display_audio))
            ax.plot(time_axis[::100], display_audio[::100],
                    color=color, linewidth=0.4, alpha=0.85)
            ax.set_xlabel('时间 (s)', color='#aaaaaa', fontsize=9)
            ax.set_ylabel('振幅', color='#aaaaaa', fontsize=9)
            ax.set_xlim(0, len(display_audio)/sample_rate)
            
        else:  # 频谱图 Spectrogram
            # 关注 15kHz~22kHz 高频段
            nperseg = 2048
            noverlap = int(nperseg * 0.85)
            f, t_seg, Sxx = spectrogram(display_audio, fs=sample_rate,
                                         nperseg=nperseg, noverlap=noverlap,
                                         window='hann')
            
            # 截取高频部分
            freq_mask = (f >= 15000) & (f <= 22050)
            Sxx_db = 10 * np.log10(Sxx[freq_mask] + 1e-10)
            
            if col == 1:  # 隐写音频使用更高对比度
                vmin, vmax = np.percentile(Sxx_db, 15), np.percentile(Sxx_db, 99.5)
                cmap = 'inferno'
            else:
                vmin, vmax = np.percentile(Sxx_db, 5), np.percentile(Sxx_db, 95)
                cmap = 'viridis'
            
            im = ax.imshow(Sxx_db, aspect='auto', origin='lower',
                           extent=[0, len(display_audio)/sample_rate,
                                   f[freq_mask][0]/1000, f[freq_mask][-1]/1000],
                           cmap=cmap, vmin=vmin, vmax=vmax, interpolation='nearest')
            
            ax.set_xlabel('时间 (s)', color='#aaaaaa', fontsize=9)
            ax.set_ylabel('频率 (kHz)', color='#aaaaaa', fontsize=9)
            plt.colorbar(im, ax=ax, label='功率 (dB)',
                         fraction=0.03).ax.yaxis.label.set_color('#aaaaaa')
            
            # 标注隐写频率范围
            if col == 1:
                ax.axhline(y=FREQ_LOW/1000,  color='cyan', linewidth=0.7,
                           linestyle='--', alpha=0.6, label=f'隐写区间 {FREQ_LOW//1000}kHz')
                ax.axhline(y=FREQ_HIGH/1000, color='cyan', linewidth=0.7,
                           linestyle='--', alpha=0.6, label=f'隐写区间 {FREQ_HIGH//1000}kHz')
                ax.legend(loc='upper right', fontsize=7,
                          facecolor='#1a1a2e', labelcolor='cyan')
        
        ax.set_title(title, color='white', fontsize=10, pad=8)
        for spine in ax.spines.values():
            spine.set_edgecolor('#444444')
        ax.tick_params(colors='#888888', labelsize=8)
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='#0d0d0d', edgecolor='none')
    plt.close()
    print(f"  [保存] {output_path}")


def fit_bitmap_for_preview(bitmap, max_rows=PREVIEW_MAX_ROWS, max_cols=PREVIEW_MAX_COLS):
    """将位图缩放到适合展示的尺寸。"""
    rows, cols = bitmap.shape
    scale = min(max_rows / rows, max_cols / cols, 1.0)
    if scale >= 1.0:
        return bitmap.astype(np.uint8)

    target_rows = max(1, round(rows * scale))
    target_cols = max(1, round(cols * scale))
    return resize_bitmap(bitmap, target_width=target_cols, target_height=target_rows)


def generate_principle_diagram(output_path, bitmap, content_label, content_mode, duration):
    """生成动态原理示意图：展示当前文字或 logo 的映射方式。"""
    preview = fit_bitmap_for_preview(bitmap)
    col_duration_ms = ((duration - 2 * MARGIN_TIME) / bitmap.shape[1]) * 1000
    mode_label = 'Logo 图像' if content_mode == 'logo' else '文字点阵'

    fig = plt.figure(figsize=(14, 5), facecolor='#0d0d0d', constrained_layout=True)
    grid = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.2, 1.0], wspace=0.28)
    ax_input = fig.add_subplot(grid[0, 0])
    ax_map = fig.add_subplot(grid[0, 1])
    ax_info = fig.add_subplot(grid[0, 2])

    fig.suptitle('编码原理：图样 → 时间-频率映射',
                 color='white', fontsize=14, fontweight='bold', y=0.98)

    ax_input.set_facecolor('#111122')
    ax_input.imshow(preview, cmap='gray_r', origin='upper',
                    interpolation='nearest', aspect='auto')
    ax_input.set_title(f'输入图样（{mode_label}）', color='white', fontsize=10)
    ax_input.set_xlabel('时间列', color='#aaaaaa', fontsize=9)
    ax_input.set_ylabel('像素行', color='#aaaaaa', fontsize=9)
    ax_input.tick_params(colors='#888888', labelsize=8)

    ax_map.set_facecolor('#111122')
    ax_map.imshow(np.flipud(preview), cmap='inferno', origin='lower',
                  interpolation='nearest', aspect='auto',
                  extent=[0, preview.shape[1], FREQ_LOW/1000, FREQ_HIGH/1000])
    ax_map.set_title('映射后的频率网格', color='white', fontsize=10)
    ax_map.set_xlabel('时间列', color='#aaaaaa', fontsize=9)
    ax_map.set_ylabel('频率 (kHz)', color='#aaaaaa', fontsize=9)
    ax_map.tick_params(colors='#888888', labelsize=8)
    ax_map.axhline(y=FREQ_LOW/1000, color='cyan', linewidth=0.7,
                   linestyle='--', alpha=0.6)
    ax_map.axhline(y=FREQ_HIGH/1000, color='cyan', linewidth=0.7,
                   linestyle='--', alpha=0.6)

    ax_info.set_facecolor('#0d0d0d')
    ax_info.axis('off')
    notes = [
        ('输入内容', content_label),
        ('编码模式', mode_label),
        ('位图尺寸', f'{bitmap.shape[1]} 列 × {bitmap.shape[0]} 行'),
        ('频率范围', f'{FREQ_LOW//1000}~{FREQ_HIGH//1000} kHz'),
        ('时间分辨', f'每列约 {col_duration_ms:.0f} ms'),
        ('信号幅度', f'{AMPLITUDE_MSG}'),
    ]
    y_pos = 0.88
    for key, value in notes:
        ax_info.text(0.02, y_pos, key + '：', color='#aaaaaa',
                     fontsize=10, fontweight='bold', transform=ax_info.transAxes)
        ax_info.text(0.34, y_pos, value, color='#4fc3f7',
                     fontsize=10, transform=ax_info.transAxes)
        y_pos -= 0.12

    ax_info.text(0.02, 0.14,
                 '每一列对应一个时间窗；\n每一行对应一个频率槽；\n像素为 1 时注入高频正弦波。',
                 color='#00ff88', fontsize=10, transform=ax_info.transAxes)

    for axis in [ax_input, ax_map]:
        for spine in axis.spines.values():
            spine.set_edgecolor('#444444')

    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='#0d0d0d', edgecolor='none')
    plt.close()
    print(f"  [保存] {output_path}")


def prepare_embedding_bitmap(message, duration, logo_path=None,
                             logo_height=LOGO_HEIGHT, logo_threshold=LOGO_THRESHOLD):
    """根据输入模式构建要嵌入频谱的位图。"""
    if logo_path:
        bitmap = load_logo_bitmap(
            logo_path,
            target_height=logo_height,
            duration=duration,
            threshold=logo_threshold,
        )
        label = os.path.splitext(os.path.basename(logo_path))[0]
        mode = 'logo'
    else:
        bitmap = build_text_bitmap(message)
        label = message
        mode = 'text'

    return bitmap, label, mode


def scale_audio_pair(audio_clean, audio_stego, peak_target=0.85):
    """统一缩放载体音频和隐写音频，避免写盘时削波。"""
    peak = max(
        float(np.max(np.abs(audio_clean))),
        float(np.max(np.abs(audio_stego))),
        1e-12,
    )
    scale = peak_target / peak
    return audio_clean * scale, audio_stego * scale


def parse_args():
    parser = argparse.ArgumentParser(description='音频频谱隐写演示脚本')
    parser.add_argument(
        '--input',
        help='用户自己的 WAV 音频路径；不传则使用脚本内置背景音'
    )
    parser.add_argument(
        '--message',
        default=MESSAGE,
        help='要写入频谱中的文字，默认使用脚本内置消息'
    )
    parser.add_argument(
        '--logo',
        help='要嵌入频谱中的 logo 图片路径；传入后将优先于 --message'
    )
    parser.add_argument(
        '--logo-height',
        type=int,
        default=LOGO_HEIGHT,
        help='logo 预处理后的目标高度（像素行数），默认 56'
    )
    parser.add_argument(
        '--logo-threshold',
        type=float,
        default=LOGO_THRESHOLD,
        help='logo 二值化阈值，越大越容易保留浅色边缘，默认 0.90'
    )
    parser.add_argument(
        '--duration',
        type=float,
        help='输出音频时长（秒）；用于裁剪/补零，不传则沿用输入音频原时长'
    )
    parser.add_argument(
        '--output-dir',
        default=BASE_DIR,
        help='输出目录，默认写到 audio/ 目录'
    )
    return parser.parse_args()


# ──────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────
if __name__ == '__main__':
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 55)
    print("  音频频谱隐写 — 技术实现验证")
    print("=" * 55)
    
    print("\n[步骤 1] 准备载体音频…")
    if args.input:
        audio_clean, input_info = load_audio_file(
            args.input, target_sample_rate=SAMPLE_RATE, target_duration=args.duration
        )
        duration = input_info['duration']
        print(f"  输入文件：{os.path.abspath(args.input)}")
        print(f"  声道数：{input_info['channels']}")
        print(f"  输出采样率：{input_info['sample_rate']} Hz")
        print(f"  输出时长：{duration:.2f} s")
    else:
        duration = args.duration if args.duration is not None else DURATION
        audio_clean = generate_background_audio(duration=duration)
        print("  使用内置背景音频")
        print(f"  输出时长：{duration:.2f} s")
    
    print("[步骤 2] 编码隐写信号…")
    bitmap, content_label, content_mode = prepare_embedding_bitmap(
        args.message,
        duration=duration,
        logo_path=args.logo,
        logo_height=args.logo_height,
        logo_threshold=args.logo_threshold,
    )
    audio_stego, all_cols, freq_slots = encode_bitmap_to_audio(
        bitmap, duration=duration, carrier_audio=audio_clean
    )
    audio_clean, audio_stego = scale_audio_pair(audio_clean, audio_stego)

    if args.logo:
        print(f"  Logo 文件：{os.path.abspath(args.logo)}")
    else:
        print(f"  消息：{args.message}")
    print(f"  编码模式：{'logo 图像' if content_mode == 'logo' else '文字点阵'}")
    print(f"  位图尺寸：{bitmap.shape[1]} 列 × {bitmap.shape[0]} 行")
    print(f"  总频率点：{len(all_cols) * bitmap.shape[0]}")
    print(f"  频率范围：{FREQ_LOW}~{FREQ_HIGH} Hz")
    print(f"  信号幅度：{AMPLITUDE_MSG}（背景：{AMPLITUDE_BG}）")
    
    print("\n[步骤 3] 保存 WAV 文件…")
    save_wav(audio_clean, os.path.join(output_dir, 'audio_original.wav'))
    save_wav(audio_stego, os.path.join(output_dir, 'audio_stego.wav'))

    print("\n[步骤 4] 生成频谱对比图…")
    generate_spectrogram_comparison(
        audio_clean, audio_stego, SAMPLE_RATE,
        os.path.join(output_dir, 'spectrogram_comparison.png'),
        content_label,
        content_mode,
    )

    print("\n[步骤 5] 生成编码原理图…")
    generate_principle_diagram(
        os.path.join(output_dir, 'encoding_principle.png'),
        bitmap,
        content_label,
        content_mode,
        duration,
    )
    
    print("\n[步骤 6] 信噪比分析…")
    diff = audio_stego[:len(audio_clean)] - audio_clean[:len(audio_stego)]
    signal_power = np.mean(audio_clean**2)
    noise_power  = np.mean(diff**2)
    snr_db = 10 * np.log10(signal_power / (noise_power + 1e-12))
    print(f"  载体信号功率：{signal_power:.6f}")
    print(f"  隐写噪声功率：{noise_power:.6f}")
    print(f"  信噪比 (SNR)：{snr_db:.1f} dB  （越高越难察觉）")
    
    print("\n✅ 全部完成！")
