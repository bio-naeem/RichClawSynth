#!/usr/bin/env python3
"""
Generate synthetic test audio files for benchmark queries.
Supports multiple TTS engines: Edge TTS (recommended), gTTS.
"""

import argparse
import os
import subprocess
import importlib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EDGE_TTS_DIR = os.path.join(SCRIPT_DIR, 'edge-tts')
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
DEFAULT_WORKSPACE = os.path.join(WORKSPACE_ROOT, 'tmp_output', 'claw-input-file-generator')
SETUP_COMMAND = 'pip3 install Pillow markdown weasyprint openpyxl python-docx gTTS'
EDGE_SETUP_COMMAND = 'cd scripts/edge-tts && npm install'

# Default voice sample text
DEFAULT_TEXT = "大家好，这是我的声音样本录音。我喜欢用温和的语气和别人交流。"

# Edge TTS voices
EDGE_TTS_VOICES = {
    'female-narrator': 'zh-CN-XiaoxiaoNeural',
    'female-assistant': 'zh-CN-XiaoxiaoNeural',
    'female-chat': 'zh-CN-XiaoxiaoNeural',
    'male-narrator': 'zh-CN-YunyangNeural',
    'male-chat': 'zh-CN-YunyangNeural',
    'male-documentary': 'zh-CN-YunyangNeural',
}


def edge_speed_to_rate(speed):
    """Convert 0-100 speed scale to Edge TTS percentage string."""
    speed = max(0, min(100, speed))
    pct = int((speed - 50) * 2)
    return 'default' if pct == 0 else f'{pct:+d}%'


def edge_volume_to_volume(volume):
    """Convert 0-100 volume scale to Edge TTS percentage string."""
    volume = max(0, min(100, volume))
    pct = int(volume - 50)
    return 'default' if pct == 0 else f'{pct:+d}%'


def generate_with_edge_tts(text, output_path, voice='zh-CN-XiaoxiaoNeural', speed=50, volume=50):
    """Generate audio using the local edge-tts skill."""
    tts_script = os.path.join(EDGE_TTS_DIR, 'tts-converter.js')
    ensure_parent_dir(output_path)
    
    if not os.path.exists(tts_script):
        raise RuntimeError(f"Edge TTS script not found at {tts_script}")

    if not os.path.exists(os.path.join(EDGE_TTS_DIR, 'node_modules')):
        raise RuntimeError(
            "Bundled Edge TTS dependencies are missing. "
            f"Install them first: {EDGE_SETUP_COMMAND}"
        )
    
    cmd = [
        'node', tts_script,
        text,
        '--lang', 'zh-CN',
        '--voice', voice,
        '--rate', edge_speed_to_rate(speed),
        '--volume', edge_volume_to_volume(volume),
        '--output', output_path,
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return output_path
        raise RuntimeError(f"Edge TTS failed: {result.stderr or result.stdout}".strip())
    except RuntimeError:
        raise
    except subprocess.TimeoutExpired:
        raise RuntimeError("Edge TTS timed out")
    except Exception as e:
        raise RuntimeError(f"Edge TTS error: {e}") from e


def generate_with_gtts(text, output_path, lang='zh-CN'):
    """Generate audio using Google TTS (fallback)."""
    require_python_package('gtts', 'gTTS')
    from gtts import gTTS
    ensure_parent_dir(output_path)
    
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(output_path)
    return output_path


def generate_audio(text, output_path, engine='edge', voice=None, speed=50, volume=50):
    """
    Generate audio from text.
    
    Args:
        text: Text to synthesize
        output_path: Output audio file path
        engine: TTS engine ('edge' or 'gtts')
        voice: Voice name (for Edge TTS)
        speed: Speech speed (0-100)
        volume: Volume (0-100)
    
    Returns:
        Output path if successful, None otherwise
    """
    if engine == 'edge':
        voice = voice or EDGE_TTS_VOICES['female-narrator']
        return generate_with_edge_tts(text, output_path, voice, speed, volume)

    if engine == 'auto':
        voice = voice or EDGE_TTS_VOICES['female-narrator']
        try:
            return generate_with_edge_tts(text, output_path, voice, speed, volume)
        except RuntimeError as exc:
            print(f"{exc}\nFalling back to gTTS because --engine auto was requested.")

    return generate_with_gtts(text, output_path)


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def require_python_package(module_name, package_name):
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(
            f"Missing Python dependency '{package_name}'. "
            f"Install skill prerequisites first: {SETUP_COMMAND}"
        ) from exc


def main():
    parser = argparse.ArgumentParser(description='Generate synthetic test audio files')
    parser.add_argument('--text', default=DEFAULT_TEXT, help='Text to synthesize')
    parser.add_argument('--output', default=None, help='Output audio file path')
    parser.add_argument('--workspace', default=DEFAULT_WORKSPACE, help='Workspace directory')
    parser.add_argument('--engine', choices=['edge', 'gtts', 'auto'], 
                       default='auto', help='TTS engine to use')
    parser.add_argument('--voice', default=None, help='Voice name (Edge TTS)')
    parser.add_argument('--speed', type=int, default=50, help='Speech speed (0-100)')
    parser.add_argument('--volume', type=int, default=50, help='Volume (0-100)')
    parser.add_argument('--list-voices', action='store_true', help='List bundled voice aliases')
    
    args = parser.parse_args()
    
    if args.list_voices:
        print("Available Edge TTS voices:")
        for name, vcn in EDGE_TTS_VOICES.items():
            print(f"  {name}: {vcn}")
        return
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        os.makedirs(args.workspace, exist_ok=True)
        output_path = os.path.join(args.workspace, 'my_voice.mp3')
    
    # Determine engine
    engine = args.engine
    
    # Generate audio
    result = generate_audio(
        args.text,
        output_path,
        engine=engine,
        voice=args.voice,
        speed=args.speed,
        volume=args.volume
    )
    
    if not result or not os.path.exists(result):
        raise SystemExit(f"Generator did not create the expected file: {output_path}")

    print(f"Generated: {result}")


if __name__ == '__main__':
    main()
