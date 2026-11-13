"""edit.yaml -> 1080x1920 세로 영상 렌더링 (화면 전환 + 자막 + BGM)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .common import ANALYSIS, OUT_FPS, OUT_H, OUT_W, OUTPUT, ROOT, SUB_FONT, probe, run

CUT = 1.0 / OUT_FPS          # 'cut' = 1프레임짜리 전환 (사실상 하드컷)
TR_LEN = {"cut": CUT, "fade": 0.35, "dissolve": 0.4, "radial": 0.45, "circleopen": 0.45,
          "pixelize": 0.4}
DEFAULT_TR_LEN = 0.3

# ── ASS 자막 스타일 (1080x1920 기준) ─────────────────────────
# 색상은 &HAABBGGRR
ASS_HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{SUB_FONT},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,2,2,70,70,560,1
Style: Pop,{SUB_FONT},118,&H0000E1FF,&H0000E1FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,9,3,8,60,60,470,1
Style: Top,{SUB_FONT},76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,2,8,60,60,300,1
Style: Title,{SUB_FONT},84,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,18,0,8,60,60,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
POP_IN = r"{\fscx40\fscy40\t(0,110,\fscx112\fscy112)\t(110,190,\fscx100\fscy100)}"
SUB_IN = r"{\fad(60,60)}"


def _ts(t: float) -> str:
    t = max(t, 0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", r"\N")


def _chunks(words: list[dict], max_chars=13, max_dur=2.2, gap=0.45) -> list[dict]:
    """단어 타임스탬프 -> 짧은 자막 덩어리 (쇼츠는 한 줄에 짧게)."""
    out, cur = [], []
    for w in words:
        txt = w["w"].strip()
        if not txt:
            continue
        if cur:
            joined = "".join(x["w"] for x in cur + [w]).strip()
            if (len(joined) > max_chars or w["start"] - cur[-1]["end"] > gap
                    or w["end"] - cur[0]["start"] > max_dur):
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"],
             "text": "".join(x["w"] for x in c).strip()} for c in out]


def _transcript(src: Path) -> list[dict]:
    f = ANALYSIS / src.stem / "transcript.json"
    return json.loads(f.read_text()) if f.exists() else []


# ── 클립별 필터 ─────────────────────────────────────────────
def _atempo(speed: float) -> str:
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0"); s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5"); s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def _video_chain(i: int, c: dict, p, fit: str) -> str:
    pre = []
    if p.hdr:   # 아이폰 HDR(HLG) -> SDR
        pre.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                   "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
    pre += [f"setpts=(PTS-STARTPTS)/{c['speed']}", f"fps={OUT_FPS}"]
    z = float(c.get("zoom", 1.0))
    cx = float(c.get("crop_x", 0.5))
    ratio = p.width / p.height
    cover = (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
             f"crop={OUT_W}:{OUT_H}:(iw-{OUT_W})*{cx}:(ih-{OUT_H})/2")
    if ratio <= 0.75 or fit == "crop":
        geo = f"[{i}:v]{','.join(pre)},{cover}"
    else:   # blur: 흐린 배경 + 가운데 원본
        geo = (f"[{i}:v]{','.join(pre)},split[bg{i}][fg{i}];"
               f"[bg{i}]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
               f"gblur=sigma=12,eq=brightness=-0.08,scale={OUT_W}:{OUT_H}[bgb{i}];"
               f"[fg{i}]scale={OUT_W}:-2[fgs{i}];"
               f"[bgb{i}][fgs{i}]overlay=0:(H-h)/2")
    if z > 1.001:
        geo += (f",scale=iw*{z:.3f}:ih*{z:.3f},crop={OUT_W}:{OUT_H}")
    return geo + f",setsar=1,format=yuv420p[v{i}]"


def _audio_chain(i: int, c: dict, p, dur: float) -> str:
    if p.has_audio:
        return (f"[{i}:a]asetpts=PTS-STARTPTS,{_atempo(c['speed'])},aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=0:{dur:.3f}[a{i}]")
    return f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[a{i}]"


# ── 렌더 ─────────────────────────────────────────────────────
def render(edit_path: Path, out: Path | None = None, preview: bool = False) -> Path:
    edit = yaml.safe_load(Path(edit_path).read_text())
    clips = edit["clips"]
    if not clips:
        raise SystemExit("clips 가 비어 있어요.")
    fit = edit.get("fit", "crop")
    out = out or OUTPUT / (Path(edit_path).stem + ("_preview" if preview else "") + ".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    inputs, fl, lens, starts = [], [], [], []
    for i, c in enumerate(clips):
        c.setdefault("speed", 1.0)
        src = Path(c["src"])
        src = src if src.is_absolute() else ROOT / src
        c["_src"] = src
        p = probe(src)
        cin, cout = float(c["in"]), min(float(c["out"]), p.duration)
        L = (cout - cin) / c["speed"]
        lens.append(L)
        inputs += ["-ss", f"{cin:.3f}", "-t", f"{cout - cin:.3f}", "-i", str(src)]
        fl.append(_video_chain(i, c, p, fit))
        fl.append(_audio_chain(i, c, p, L))

    # 전환 연결
    trs = []
    for i, c in enumerate(clips[:-1]):
        name = c.get("transition", "cut") or "cut"
        d = TR_LEN.get(name, DEFAULT_TR_LEN)
        d = min(d, lens[i] / 3, lens[i + 1] / 3)
        trs.append(("fade" if name == "cut" else name, max(d, CUT)))
    vcur, acur, t = "[v0]", "[a0]", lens[0]
    starts.append(0.0)
    for i, (name, d) in enumerate(trs, start=1):
        off = t - d
        starts.append(off)
        fl.append(f"{vcur}[v{i}]xfade=transition={name}:duration={d:.3f}:offset={off:.3f}[vx{i}]")
        fl.append(f"{acur}[a{i}]acrossfade=d={d:.3f}:c1=tri:c2=tri[ax{i}]")
        vcur, acur, t = f"[vx{i}]", f"[ax{i}]", off + lens[i]
    total = t

    # 자막
    ass = out.with_suffix(".ass")
    ass.write_text(build_ass(edit, clips, starts, lens, trs, total))
    assp = str(ass).replace(":", r"\:").replace("'", r"\'")
    post = f"ass='{assp}'"
    if preview:
        post += ",scale=540:960"
    fl.append(f"{vcur}{post}[vout]")

    # BGM (말소리에 맞춰 자동으로 줄어듦) + 쇼츠 음량(-14 LUFS)
    bgm = edit.get("bgm")
    if bgm:
        bp = Path(bgm) if Path(bgm).is_absolute() else ROOT / bgm
        inputs += ["-stream_loop", "-1", "-i", str(bp)]
        b = len(clips)
        vol = float(edit.get("bgm_volume", 0.25))
        fl.append(f"[{b}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                  f"volume={vol},atrim=0:{total:.3f},afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5[bgm]")
        fl.append(f"{acur}asplit[av][sc]")
        fl.append("[bgm][sc]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=500[bgd]")
        fl.append("[av][bgd]amix=inputs=2:duration=first:normalize=0[am]")
        acur = "[am]"
    fl.append(f"{acur}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    cmd = ["ffmpeg", "-v", "error", "-stats", "-y", *inputs,
           "-filter_complex", ";\n".join(fl), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "ultrafast" if preview else "medium",
           "-crf", "28" if preview else "19", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-r", str(OUT_FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           "-t", f"{total:.3f}", str(out)]
    (out.with_suffix(".filter.txt")).write_text(";\n".join(fl))
    print(f"렌더링: {len(clips)}개 장면, {total:.1f}초 -> {out}")
    run(cmd, stdout=None, stderr=None)
    return out


def build_ass(edit, clips, starts, lens, trs, total) -> str:
    ev = []

    def add(st, a, b, text, layer=0):
        if b - a >= 0.2:
            ev.append(f"Dialogue: {layer},{_ts(a)},{_ts(b)},{st},,0,0,0,,{text}")

    if edit.get("title"):
        add("Title", 0.0, min(2.5, total), SUB_IN + _esc(edit["title"]), 2)

    auto = edit.get("subtitles", "auto") == "auto"
    repl = edit.get("replace") or {}

    def fix(text: str) -> str:
        """잘못 인식된 자막 고치기. replace: {틀린말: 맞는말}, 빈 값이면 그 자막 삭제."""
        t = text.strip()
        for k, v in repl.items():
            if k in t:
                if not v:
                    return ""
                t = t.replace(k, str(v))
        return t.rstrip(".")
    for i, c in enumerate(clips):
        s0 = starts[i]
        vis_end = s0 + lens[i] - (trs[i][1] / 2 if i < len(trs) else 0)
        sp = c["speed"]
        if auto and c.get("sub", True):
            chunks = []
            for seg in _transcript(c["_src"]):          # 문장 단위로 끊고, 그 안에서 짧게 나눔
                words = [w for w in seg.get("words", [])
                         if w["end"] > c["in"] + 0.1 and w["start"] < c["out"] - 0.1]
                chunks += _chunks(words)
            for j, ch in enumerate(chunks):
                a = s0 + (ch["start"] - c["in"]) / sp
                b = s0 + (ch["end"] - c["in"]) / sp + 0.15
                if j + 1 < len(chunks):
                    b = min(b, s0 + (chunks[j + 1]["start"] - c["in"]) / sp)
                text = fix(ch["text"])
                if text:
                    add("Sub", max(a, s0), min(b, vis_end), SUB_IN + _esc(text))
        for cap in c.get("captions") or []:
            a = s0 + float(cap.get("at", 0))
            b = min(a + float(cap.get("dur", 1.5)), vis_end)
            style = {"pop": "Pop", "sub": "Sub", "top": "Top"}.get(cap.get("style", "pop"), "Pop")
            fx = POP_IN if style == "Pop" else SUB_IN
            add(style, a, b, fx + _esc(str(cap["text"])), 1)
    return ASS_HEAD + "\n".join(ev) + "\n"
