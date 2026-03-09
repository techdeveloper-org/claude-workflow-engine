#!/usr/bin/env python3
"""
Script Name: voice-notifier.py
Version: 2.0.0
Last Modified: 2026-03-07
Description: Text-to-speech voice notification handler.
             Accepts a text message and speaks it using available TTS engines.

v2.0.0: MAJOR UPGRADE - Coqui TTS neural voice (primary engine)
  - Coqui TTS: High-quality neural voice synthesis (free, offline, MIT license)
  - Model: VITS (fast inference, natural sound)
  - Auto-downloads model on first run (~100MB, cached after that)
  - Generates WAV file, plays via platform audio player
  - Fallback chain: Coqui TTS -> pyttsx3 (Windows) / espeak (Unix)

v1.0.0: Original pyttsx3/espeak implementation

Usage:
    python voice-notifier.py "Your message here"

TTS Engine Priority:
    1. Coqui TTS (neural, natural voice) - pip install TTS
    2. pyttsx3 (Windows built-in, robotic) - pip install pyttsx3
    3. espeak (Unix built-in, robotic) - apt install espeak

Windows-Safe: ASCII only (no Unicode/emojis in print statements)
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

MEMORY_BASE = Path.home() / '.claude' / 'memory'
VOICE_LOG = MEMORY_BASE / 'logs' / 'voice-notifier.log'

# Coqui TTS config
COQUI_MODEL = "tts_models/en/ljspeech/vits"
COQUI_CACHE_DIR = Path.home() / '.claude' / 'cache' / 'tts'


def log_voice(msg):
    """Append a timestamped entry to the voice notifier log file."""
    VOICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(VOICE_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# AUDIO PLAYBACK HELPERS
# =============================================================================

def play_wav_windows(wav_path):
    """Play a WAV file on Windows using winsound (built-in, no deps)."""
    try:
        import winsound
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
        return True
    except Exception as e:
        log_voice(f"[PLAY-WIN] winsound failed: {str(e)[:80]}")
        # Fallback: try powershell
        try:
            subprocess.run(
                ['powershell', '-Command',
                 f'(New-Object Media.SoundPlayer "{wav_path}").PlaySync()'],
                timeout=30, capture_output=True
            )
            return True
        except Exception as e2:
            log_voice(f"[PLAY-WIN] powershell fallback failed: {str(e2)[:80]}")
            return False


def play_wav_unix(wav_path):
    """Play a WAV file on Unix using aplay, paplay, or ffplay."""
    players = [
        ['aplay', str(wav_path)],
        ['paplay', str(wav_path)],
        ['ffplay', '-nodisp', '-autoexit', str(wav_path)],
    ]
    for cmd in players:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                log_voice(f"[PLAY-UNIX] Played with {cmd[0]}")
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue
    log_voice("[PLAY-UNIX] No audio player found (tried aplay, paplay, ffplay)")
    return False


def play_wav(wav_path):
    """Play a WAV file using platform-appropriate player."""
    if sys.platform == 'win32':
        return play_wav_windows(wav_path)
    else:
        return play_wav_unix(wav_path)


# =============================================================================
# TTS ENGINE 1: COQUI TTS (Neural - Primary)
# =============================================================================

def speak_coqui(text):
    """Speak text using Coqui TTS neural voice synthesis.

    Uses VITS model for fast, natural-sounding speech.
    Auto-downloads model on first run (~100MB, cached after).
    Generates WAV -> plays via platform audio player.

    Args:
        text: Text to speak.

    Returns:
        bool: True if spoken successfully.
    """
    try:
        from TTS.api import TTS
    except ImportError:
        log_voice("[TTS-COQUI] TTS package not installed (pip install TTS)")
        return False

    wav_path = None
    try:
        # Create cache dir for model storage
        COQUI_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize TTS with VITS model (fast + good quality)
        tts = TTS(model_name=COQUI_MODEL, progress_bar=False)

        # Generate WAV to temp file
        wav_fd, wav_path = tempfile.mkstemp(suffix='.wav', prefix='claude_voice_')
        os.close(wav_fd)

        tts.tts_to_file(text=text, file_path=wav_path)
        log_voice(f"[TTS-COQUI] Generated WAV: {wav_path}")

        # Play the audio
        played = play_wav(wav_path)

        if played:
            log_voice(f"[TTS-COQUI-SUCCESS] Spoke: {text[:60]}")
            return True
        else:
            log_voice("[TTS-COQUI] WAV generated but playback failed")
            return False

    except Exception as e:
        log_voice(f"[TTS-COQUI-ERROR] {str(e)[:100]}")
        return False
    finally:
        # Cleanup temp WAV file
        if wav_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except Exception:
                pass


# =============================================================================
# TTS ENGINE 2: PYTTSX3 (Windows Fallback - Robotic)
# =============================================================================

def speak_pyttsx3(text):
    """Speak text on Windows using the pyttsx3 TTS engine (fallback).

    Attempts to select an Indian English voice first; falls back
    to the first available English voice.

    Args:
        text: Text to speak.

    Returns:
        bool: True if spoken successfully.
    """
    try:
        import pyttsx3
        engine = pyttsx3.init()

        voices = engine.getProperty('voices')
        indian_voice = None
        for voice in voices:
            try:
                if 'en-in' in voice.languages[0].lower() or 'indian' in voice.name.lower():
                    indian_voice = voice.id
                    break
            except (IndexError, AttributeError):
                continue

        if indian_voice:
            engine.setProperty('voice', indian_voice)
            log_voice(f"[TTS-PYTTSX3] Using Indian voice: {indian_voice}")
        else:
            for voice in voices:
                try:
                    if any(lang in voice.languages[0].lower() for lang in ['en-us', 'en-gb', 'en']):
                        engine.setProperty('voice', voice.id)
                        log_voice(f"[TTS-PYTTSX3] Using fallback voice: {voice.id}")
                        break
                except (IndexError, AttributeError):
                    continue

        engine.setProperty('rate', 150)
        engine.say(text)
        engine.runAndWait()
        log_voice(f"[TTS-PYTTSX3-SUCCESS] Spoke: {text[:60]}")
        return True

    except ImportError:
        log_voice("[TTS-PYTTSX3] pyttsx3 not installed - skipping")
        return False
    except Exception as e:
        log_voice(f"[TTS-PYTTSX3-ERROR] {str(e)[:100]}")
        return False


# =============================================================================
# TTS ENGINE 3: ESPEAK (Unix Fallback - Robotic)
# =============================================================================

def speak_espeak(text):
    """Speak text on Unix using the espeak command-line TTS tool (fallback).

    Args:
        text: Text to speak.

    Returns:
        bool: True if spoken successfully.
    """
    try:
        cmd = ['espeak', '-v', 'en-in', '-s', '150', text]
        result = subprocess.run(cmd, capture_output=True, timeout=10)

        if result.returncode == 0:
            log_voice(f"[TTS-ESPEAK-SUCCESS] Spoke with en-in: {text[:60]}")
            return True
        else:
            cmd = ['espeak', '-v', 'en', '-s', '150', text]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0:
                log_voice(f"[TTS-ESPEAK-SUCCESS] Spoke with fallback: {text[:60]}")
                return True
            else:
                log_voice(f"[TTS-ESPEAK-FAILED] Return code: {result.returncode}")
                return False

    except FileNotFoundError:
        log_voice("[TTS-ESPEAK] espeak not installed - skipping")
        return False
    except Exception as e:
        log_voice(f"[TTS-ESPEAK-ERROR] {str(e)[:100]}")
        return False


# =============================================================================
# MAIN - TTS ENGINE CHAIN
# =============================================================================

def main():
    """Entry point - tries TTS engines in priority order.

    Priority: Coqui TTS (neural) -> pyttsx3/espeak (robotic fallback)
    """
    if len(sys.argv) < 2:
        log_voice("[ERROR] No text provided")
        sys.exit(1)

    text = ' '.join(sys.argv[1:])

    if not text or not text.strip():
        log_voice("[ERROR] Empty text provided")
        sys.exit(1)

    log_voice(f"[INIT] Speaking: {text[:80]}")

    # ENGINE 1: Coqui TTS (neural voice - best quality)
    if speak_coqui(text):
        log_voice("[OK] Voice notification completed (Coqui TTS)")
        sys.exit(0)

    # ENGINE 2: Platform fallback (robotic but always available)
    log_voice("[FALLBACK] Coqui TTS unavailable, trying platform TTS...")

    if sys.platform == 'win32':
        success = speak_pyttsx3(text)
    else:
        success = speak_espeak(text)

    if success:
        log_voice("[OK] Voice notification completed (platform fallback)")
    else:
        log_voice("[WARN] All TTS engines failed - silent mode")

    sys.exit(0)


if __name__ == '__main__':
    main()
