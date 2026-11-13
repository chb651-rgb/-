"""영상 분석: 지루한 구간 / 하이라이트 후보 / 음성 인식 / 썸네일 시트.

결과: work/analysis/<영상이름>/{analysis.json, transcript.json, sheet.jpg}
      work/analysis/report.md  (사람이 읽는 요약)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from .common import ANALYSIS, LABEL_FONT_FILE, Probe, fmt_t, probe, run

FW, FH, AFPS = 320, 180, 4          # 분석용 프레임 크기/샘플링
SR = 16000

# ── 임계값 (320x180 회색조 기준) ─────────────────────────────
DARK = 28            # 평균 밝기 이하 -> 어두움
BLUR = 18            # 라플라시안 분산 이하 -> 흐림/초점 나감
STATIC = 1.2         # 프레임 차이 이하 -> 거의 정지
QUIET_DB = -42       # 이하 -> 조용함


# ── 저수준 측정 ──────────────────────────────────────────────
def _frames(p: Probe):
    cmd = ["ffmpeg", "-v", "error", "-i", str(p.path), "-an",
           "-vf", f"fps={AFPS},scale={FW}:{FH},format=gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = FW * FH
    while True:
        buf = proc.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(FH, FW).astype(np.float32)
    proc.wait()


def video_metrics(p: Probe) -> dict[str, np.ndarray]:
    bright, sharp, motion = [], [], []
    prev = None
    for f in _frames(p):
        bright.append(f.mean())
        lap = (-4 * f[1:-1, 1:-1] + f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:])
        sharp.append(lap.var())
        motion.append(0.0 if prev is None else float(np.abs(f - prev).mean()))
        prev = f
    if motion:
        motion[0] = motion[1] if len(motion) > 1 else 0.0
    return {k: np.array(v) for k, v in
            (("bright", bright), ("sharp", sharp), ("motion", motion))}


def load_audio(p: Probe) -> np.ndarray:
    """모노 16kHz float32 (Whisper 입력 형식)."""
    if not p.has_audio:
        return np.zeros(0, np.float32)
    raw = run(["ffmpeg", "-v", "error", "-i", p.path, "-vn", "-ac", "1", "-ar", SR,
               "-f", "s16le", "-"]).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def audio_db(p: Probe, a: np.ndarray, hop: float = 0.25) -> np.ndarray:
    if not len(a):
        return np.full(int(p.duration / hop) + 1, -90.0)
    h = int(SR * hop)
    n = len(a) // h
    if n == 0:
        return np.array([-90.0])
    rms = np.sqrt((a[: n * h].reshape(n, h) ** 2).mean(1) + 1e-10)
    return 20 * np.log10(rms)


# ── 음성 인식 ────────────────────────────────────────────────
_MODEL = None


def transcribe(p: Probe, audio: np.ndarray, model: str, out: Path, prompt: str = "") -> list[dict]:
    if out.exists() and not prompt:
        return json.loads(out.read_text())
    if not len(audio):
        out.write_text("[]")
        return []
    global _MODEL
    from faster_whisper import WhisperModel
    if _MODEL is None or _MODEL[0] != model:
        print(f"  Whisper 모델 로드: {model}")
        _MODEL = (model, WhisperModel(model, device="cpu", compute_type="int8"))
    segs, _ = _MODEL[1].transcribe(
        audio, language="ko", vad_filter=True, word_timestamps=True,
        condition_on_previous_text=False, beam_size=5,
        hotwords=prompt or None)
    res = []
    for s in segs:
        # 무음/잡음에서 생기는 환각 문장 제거
        if s.no_speech_prob > 0.6 or s.avg_logprob < -1.2:
            continue
        res.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [{"start": round(w.start, 2), "end": round(w.end, 2), "w": w.word}
                              for w in (s.words or [])]})
    res = _resplit(res)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def _resplit(segs: list[dict], gap: float = 0.7) -> list[dict]:
    """한 덩어리로 뭉친 문장을 단어 사이 공백(침묵) 기준으로 다시 나눈다."""
    out = []
    for seg in segs:
        cur: list[dict] = []
        for w in seg["words"]:
            if cur and (w["start"] - cur[-1]["end"] > gap or cur[-1]["w"].strip().endswith((".", "?", "!", ","))):
                out.append(cur); cur = []
            cur.append(w)
        if cur:
            out.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"],
             "text": "".join(w["w"] for w in c).strip().rstrip(","),
             "words": [{**w, "w": w["w"].rstrip(",")} for w in c]} for c in out]


# ── 초 단위 특징 + 판정 ─────────────────────────────────────
def per_second(p: Probe, vm: dict, adb: np.ndarray, speech: list[dict]) -> list[dict]:
    secs = max(1, int(np.ceil(p.duration)))
    med_db = float(np.median(adb)) if len(adb) else -60
    rows = []
    for s in range(secs):
        sl = slice(s * AFPS, (s + 1) * AFPS)
        al = slice(s * 4, (s + 1) * 4)
        b = vm["bright"][sl]; sh = vm["sharp"][sl]; mo = vm["motion"][sl]; a = adb[al]
        if len(b) == 0:
            break
        talk = any(seg["start"] < s + 1 and seg["end"] > s for seg in speech)
        db = float(a.max()) if len(a) else -90
        rows.append({
            "t": s,
            "bright": round(float(b.mean()), 1),
            "sharp": round(float(np.median(sh)), 1),
            "motion": round(float(mo.mean()), 2),
            "db": round(db, 1),
            "peak": db > max(med_db + 9, -30),       # 웃음/환호/큰소리
            "speech": talk,
        })
    for r in rows:
        why = []
        if r["bright"] < DARK:
            why.append("너무 어두움")
        if r["sharp"] < BLUR and r["bright"] >= DARK:
            why.append("흐림/초점 나감")
        if r["motion"] > 25 and r["sharp"] < BLUR * 2 and r["bright"] >= DARK:
            why.append("심한 흔들림")
        if r["motion"] < STATIC and not r["speech"] and r["db"] < QUIET_DB:
            why.append("정지 화면 + 조용함")
        r["boring"] = why
        motion_n = min(r["motion"] / 10, 1.0) if r["motion"] <= 25 else 0.6
        audio_n = float(np.clip((r["db"] + 50) / 35, 0, 1))
        r["score"] = round(0.30 * motion_n + 0.20 * audio_n + 0.25 * r["speech"]
                           + 0.30 * r["peak"] - 0.6 * bool(why), 3)
    return rows


def _ranges(rows, pred, min_len=1):
    out, start = [], None
    for r in rows + [None]:
        if r is not None and pred(r):
            start = r["t"] if start is None else start
        elif start is not None:
            end = (r["t"] if r else rows[-1]["t"] + 1)
            if end - start >= min_len:
                out.append([start, end])
            start = None
    return out


def boring_ranges(rows, duration) -> list[dict]:
    res = []
    for s, e in _ranges(rows, lambda r: bool(r["boring"]), min_len=2):
        why = sorted({w for r in rows[s:e] for w in r["boring"]})
        res.append({"start": s, "end": min(e, duration), "why": why})
    # 촬영 시작/끝 (버튼 누르는 손떨림)
    if duration > 4:
        res.append({"start": 0, "end": 0.6, "why": ["촬영 시작 부분"]})
        res.append({"start": round(duration - 0.6, 2), "end": round(duration, 2), "why": ["촬영 끝 부분"]})
    return sorted(res, key=lambda r: r["start"])


def _snap_words(s: float, e: float, speech: list[dict]) -> tuple[float, float]:
    """단어 중간에서 잘리지 않게 경계를 단어 앞/뒤로 맞춘다."""
    for w in (w for seg in speech for w in seg.get("words", [])):
        if w["start"] < s < w["end"]:
            s = w["start"] - 0.1
        if w["start"] < e < w["end"]:
            e = w["end"] + 0.2 if w["end"] - e < 1.2 else w["start"] - 0.05
    return max(0.0, s), e


def highlights(rows, speech, duration, max_n=10, min_len=2.0, max_len=6.0) -> list[dict]:
    """점수 높은 초를 중심으로 창을 잡고, 말이 잘리지 않게 문장 경계로 넓힌다."""
    sc = np.array([r["score"] for r in rows])
    used = np.zeros(len(rows), bool)
    out = []
    smooth = np.convolve(sc, np.ones(3) / 3, mode="same")
    for idx in np.argsort(-smooth):
        if len(out) >= max_n or smooth[idx] < 0.15:
            break
        if used[max(0, idx - 1): idx + 2].any():
            continue
        s, e = max(0.6, idx - 1.0), min(duration - 0.6, idx + 2.0)
        for seg in speech:                      # 문장 단위로 확장
            if seg["start"] < e and seg["end"] > s:
                s, e = min(s, seg["start"] - 0.15), max(e, seg["end"] + 0.25)
        s, e = max(0.0, s), min(duration, e)
        if e - s > max_len:                     # 너무 길면 피크 중심으로 자르기
            c = idx + 0.5
            s, e = max(s, c - max_len / 2), min(e, c + max_len / 2)
        s, e = _snap_words(s, e, speech)
        if e - s < min_len:
            continue
        lo, hi = int(s), int(np.ceil(e))
        if used[lo:hi].any() or any(r["boring"] for r in rows[lo:hi] if "너무 어두움" in r["boring"]):
            continue
        used[lo:hi] = True
        why = []
        seg_rows = rows[lo:hi]
        if any(r["peak"] for r in seg_rows): why.append("큰 소리/웃음")
        if any(r["speech"] for r in seg_rows): why.append("대화")
        if np.mean([r["motion"] for r in seg_rows]) > 5: why.append("움직임 많음")
        text = " ".join(x["text"] for x in speech if x["start"] < e and x["end"] > s)
        out.append({"start": round(s, 2), "end": round(e, 2),
                    "score": round(float(np.mean(sc[lo:hi])), 3), "why": why, "text": text})
    return sorted(out, key=lambda h: h["start"])


def contact_sheet(p: Probe, out: Path, n: int = 30) -> None:
    step = max(p.duration / n, 0.5)
    cols = 6 if p.portrait else 4
    rows = int(np.ceil(min(n, p.duration / step) / cols)) or 1
    label = (f"drawtext=fontfile={LABEL_FONT_FILE}:text='%{{pts\\:hms}}':x=6:y=6:"
             "fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6")
    run(["ffmpeg", "-v", "error", "-y", "-i", p.path, "-an",
         "-vf", f"fps=1/{step:.3f},scale=-2:300,{label},tile={cols}x{rows}:padding=4",
         "-frames:v", "1", "-q:v", "4", out])


# ── 엔트리 ──────────────────────────────────────────────────
def analyze(videos: list[Path], model: str = "large-v3-turbo", prompt: str = "") -> list[dict]:
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    results = []
    for i, path in enumerate(videos, 1):
        p = probe(path)
        d = ANALYSIS / path.stem
        d.mkdir(exist_ok=True)
        print(f"[{i}/{len(videos)}] {path.name}  {fmt_t(p.duration)}  {p.width}x{p.height}"
              f"{' HDR' if p.hdr else ''}")
        vm = video_metrics(p)
        audio = load_audio(p)
        adb = audio_db(p, audio)
        speech = transcribe(p, audio, model, d / "transcript.json", prompt)
        rows = per_second(p, vm, adb, speech)
        res = {
            "file": str(path), "name": path.name, "duration": round(p.duration, 2),
            "width": p.width, "height": p.height, "fps": round(p.fps, 2), "hdr": p.hdr,
            "has_audio": p.has_audio, "creation_time": p.creation_time,
            "boring": boring_ranges(rows, p.duration),
            "highlights": highlights(rows, speech, p.duration),
            "speech": [{k: s[k] for k in ("start", "end", "text")} for s in speech],
            "seconds": rows,
        }
        (d / "analysis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        contact_sheet(p, d / "sheet.jpg")
        results.append(res)
    write_report(results)
    return results


def write_report(results: list[dict]) -> Path:
    L = ["# 영상 분석 리포트", ""]
    total = sum(r["duration"] for r in results)
    L.append(f"영상 {len(results)}개, 총 {fmt_t(total)}\n")
    for r in results:
        bore = sum(b["end"] - b["start"] for b in r["boring"])
        L += [f"## {r['name']}  ({fmt_t(r['duration'])}, {r['width']}x{r['height']})",
              f"썸네일: `work/analysis/{Path(r['file']).stem}/sheet.jpg`  ",
              f"버릴 만한 구간 합계: {bore:.0f}초 / {r['duration']:.0f}초", ""]
        if r["boring"]:
            L.append("**✂️ 버릴 장면**\n")
            L += [f"- {fmt_t(b['start'])}–{fmt_t(b['end'])}  {', '.join(b['why'])}" for b in r["boring"]]
            L.append("")
        if r["highlights"]:
            L.append("**⭐ 하이라이트 후보**\n")
            for h in sorted(r["highlights"], key=lambda h: -h["score"]):
                t = f' — "{h["text"]}"' if h["text"] else ""
                L.append(f"- {fmt_t(h['start'])}–{fmt_t(h['end'])}  점수 {h['score']:.2f}  "
                         f"{', '.join(h['why'])}{t}")
            L.append("")
    out = ANALYSIS / "report.md"
    out.write_text("\n".join(L))
    print(f"\n리포트: {out}")
    return out
