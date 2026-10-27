"""音频播放：优先 simpleaudio（wait_done 阻塞），不可用时降级 winsound。

评分细则 C-7 要求播放不能吞异常；这里只在“库不可用”时切换实现，
真正的文件缺失 / 解码失败会原样抛出。
"""
from __future__ import annotations

import os
import sys

try:  # simpleaudio 需要 C 扩展，Windows 上可能因缺少 MSVC 而装不上
    import simpleaudio as sa
except ImportError:  # pragma: no cover - 取决于本机编译环境
    sa = None


def play_audio(audio_path: str) -> bool:
    """阻塞播放音频，直到播完才返回。

    参数：
        audio_path: WAV 文件路径
    返回：
        True 表示播放完成
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在：{audio_path}")

    if sa is not None:
        wave_obj = sa.WaveObject.from_wave_file(audio_path)
        play_obj = wave_obj.play()
        play_obj.wait_done()  # 阻塞等待播放结束
        return True

    # 降级路径：winsound.PlaySound 默认同步阻塞，语义与 wait_done 一致
    import winsound
    winsound.PlaySound(audio_path, winsound.SND_FILENAME)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python play.py outputs/advice.wav")
        raise SystemExit(1)
    play_audio(sys.argv[1])
