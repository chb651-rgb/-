"""저작권 걱정 없는 배경음악/효과음 합성.

  python -m shorts music            -> work/music/ 에 bgm_*.wav, sfx_*.wav 생성
edit.yaml 에서:  bgm: work/music/bgm_sneaky.wav
                 clips[].sfx: [{at: 1.0, name: sad_trombone, stop_bgm: true}]
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .common import WORK

SR = 44100
MUSIC = WORK / "music"


def _note(n: str) -> float:
    """'C4', 'F#3', 'Bb2' -> Hz"""
    names = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    semi = names[n[0]]
    i = 1
    while n[i] in "#b":
        semi += 1 if n[i] == "#" else -1
        i += 1
    octave = int(n[i:])
    return 440.0 * 2 ** ((semi + 12 * (octave + 1) - 69) / 12)


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def _tone(freq, dur, partials=((1, 1.0),), attack=0.005, decay=0.3, vib=0.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ph = 2 * np.pi * freq * t
    if vib:
        ph += vib * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.3, 0, 1)
    sig = sum(a * np.sin(k * ph) for k, a in partials)
    return sig * _env(n, attack, decay)


def marimba(f, dur=0.35):
    return _tone(f, dur, ((1, 1.0), (4, 0.25), (10, 0.05)), 0.002, 0.12)


def pizz(f, dur=0.3):
    return _tone(f, dur, ((1, 1.0), (2, 0.5), (3, 0.3), (4, 0.15)), 0.003, 0.08)


def bass(f, dur=0.4):
    return _tone(f, dur, ((1, 1.0), (2, 0.35)), 0.004, 0.18)


def tick(dur=0.05, amp=0.15):
    n = int(dur * SR)
    noise = np.random.default_rng(1).standard_normal(n)
    noise = np.diff(noise, prepend=0)          # 고역 강조 (하이햇 느낌)
    return amp * noise * _env(n, 0.001, 0.012)


def _mix_at(buf, sig, t, gain=1.0):
    i = int(t * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += gain * sig[: j - i]


def _norm(x, peak=0.8):
    m = np.abs(x).max() or 1
    return x / m * peak


def save(x: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    st = (np.stack([x, x], 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(st.tobytes())
    return path


# ── 배경음악 ─────────────────────────────────────────────────
def bgm_sneaky(bars: int = 16, bpm: float = 112) -> np.ndarray:
    """살금살금 장난스러운 곡 (피치카토 + 마림바). 루프 가능."""
    beat = 60 / bpm
    buf = np.zeros(int(bars * 4 * beat * SR) + SR)
    prog = [("A2", ["A3", "C4", "E4"]), ("F2", ["F3", "A3", "C4"]),
            ("D2", ["D3", "F3", "A3"]), ("E2", ["E3", "G#3", "B3"])]
    # 8분음표 멜로디 (None = 쉼표). 2마디 단위 패턴, 코드에 맞춰 이동
    mel = [["A4", None, "C5", None, "B4", "A4", None, "E4"],
           [None, "F4", "A4", None, "C5", None, "A4", None],
           ["D5", None, "C5", None, "A4", "F4", None, "D4"],
           ["E4", None, "G#4", None, "B4", None, "E5", None]]
    for b in range(bars):
        root, chord = prog[b % 4]
        t0 = b * 4 * beat
        for k in (0, 2):                                   # 베이스: 1, 3박
            _mix_at(buf, bass(_note(root)), t0 + k * beat, 0.9)
            _mix_at(buf, bass(_note(root) * 1.5, 0.25), t0 + (k + 1.5) * beat, 0.4)
        for k in (1, 3):                                   # 화음: 2, 4박 스타카토
            for n in chord:
                _mix_at(buf, pizz(_note(n), 0.18), t0 + k * beat, 0.28)
        if b >= 2:                                         # 멜로디는 3마디부터
            for k, n in enumerate(mel[b % 4]):
                if n:
                    _mix_at(buf, marimba(_note(n)), t0 + k * beat / 2, 0.55)
        for k in range(8):                                 # 하이햇: 8분 뒷박
            if k % 2:
                _mix_at(buf, tick(), t0 + k * beat / 2, 1.0)
    buf = buf[: int(bars * 4 * beat * SR)]
    return _norm(buf, 0.7)


# ── 효과음 ───────────────────────────────────────────────────
def sfx_sad_trombone() -> np.ndarray:
    """빠-밤-빠-바아암~ (허무함)"""
    notes = [("A3", 0.32), ("G#3", 0.32), ("G3", 0.32), ("F#3", 1.3)]
    out, t = [], 0
    for i, (n, d) in enumerate(notes):
        last = i == len(notes) - 1
        partials = tuple((k, 1 / k ** 1.1) for k in range(1, 12))   # 톱니파 비슷한 금관 소리
        s = _tone(_note(n), d, partials, 0.04, d * (1.4 if last else 3), vib=0.9 if last else 0)
        n_ = len(s)
        rel = np.ones(n_); r = int(0.06 * SR); rel[-r:] = np.linspace(1, 0, r)
        out.append(s * rel)
    return _norm(np.concatenate(out), 0.75)


def sfx_suspense() -> np.ndarray:
    """둥.. 둥.. 두둥! (긴장)"""
    buf = np.zeros(int(1.6 * SR))
    for t, f, g in ((0.0, "D2", 0.7), (0.45, "D2", 0.7), (0.9, "C#2", 1.0)):
        hit = _tone(_note(f), 0.7, ((1, 1.0), (2, 0.5), (3, 0.25)), 0.003, 0.35)
        boom = _tone(45, 0.7, ((1, 1.0),), 0.002, 0.15)
        _mix_at(buf, hit + boom, t, g)
    return _norm(buf, 0.85)


def sfx_sparkle() -> np.ndarray:
    """반짝~ (등장/소환)"""
    buf = np.zeros(int(1.2 * SR))
    for i, n in enumerate(["C6", "E6", "G6", "C7", "E7"]):
        _mix_at(buf, _tone(_note(n), 0.8, ((1, 1.0), (2.76, 0.3)), 0.002, 0.25), i * 0.06, 0.5)
    return _norm(buf, 0.6)


def sfx_pop() -> np.ndarray:
    """뽁 (자막 등장)"""
    n = int(0.12 * SR); t = np.arange(n) / SR
    f = 900 * np.exp(-t * 18) + 300
    return _norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.001, 0.03), 0.6)


def sfx_whoosh() -> np.ndarray:
    """휙 (화면 전환)"""
    n = int(0.45 * SR)
    noise = np.random.default_rng(3).standard_normal(n)
    k = np.hanning(n)
    x = np.convolve(noise, np.ones(12) / 12, mode="same") * k   # 부드러운 바람 소리
    return _norm(x, 0.5)


ALL = {
    "bgm_sneaky": bgm_sneaky,
    "sfx_sad_trombone": sfx_sad_trombone, "sfx_suspense": sfx_suspense,
    "sfx_sparkle": sfx_sparkle, "sfx_pop": sfx_pop, "sfx_whoosh": sfx_whoosh,
}


def build_all() -> list[Path]:
    out = [save(fn(), MUSIC / f"{name}.wav") for name, fn in ALL.items()]
    for p in out:
        print(p)
    return out


def sfx_path(name: str) -> Path:
    p = Path(name)
    if p.suffix:                     # 사용자가 준 파일
        return p
    f = MUSIC / f"sfx_{name}.wav"
    if not f.exists():
        build_all()
    return f
