"""공통 유틸: ffprobe, 실행 래퍼, 경로/폰트 설정."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"          # 원본/분석 결과/렌더 결과 (git 제외)
INPUT = WORK / "input"
ANALYSIS = WORK / "analysis"
OUTPUT = WORK / "output"

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".3gp", ".webm", ".lrv"}

# 자막 폰트 (apt: fonts-noto-cjk, fonts-nanum)
SUB_FONT = "Noto Sans CJK KR Black"
LABEL_FONT_FILE = "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30


def run(cmd: list[str], *, quiet: bool = True, check: bool = True, **kw) -> subprocess.CompletedProcess:
    if not quiet:
        print("$", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=check,
                          stdout=kw.pop("stdout", subprocess.PIPE),
                          stderr=kw.pop("stderr", subprocess.PIPE), **kw)


@dataclass
class Probe:
    path: Path
    duration: float
    width: int          # 회전 적용 후 표시 크기
    height: int
    fps: float
    has_audio: bool
    rotation: int
    creation_time: str
    hdr: bool           # HLG/PQ (아이폰 HDR 등) -> 렌더 시 SDR 톤매핑

    @property
    def portrait(self) -> bool:
        return self.height > self.width


def probe(path: Path) -> Probe:
    out = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path]).stdout
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "rotate" in v.get("tags", {}):
        rot = int(v["tags"]["rotate"])
    w, h = int(v["width"]), int(v["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    dur = float(info["format"].get("duration") or v.get("duration") or 0)
    tags = {**info["format"].get("tags", {}), **v.get("tags", {})}
    ctime = tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time", "")
    hdr = v.get("color_transfer") in ("arib-std-b67", "smpte2084")
    return Probe(path, dur, w, h, fps, has_audio, rot, ctime, hdr)


def list_videos(folder: Path) -> list[Path]:
    vids = [p for p in sorted(folder.rglob("*")) if p.suffix.lower() in VIDEO_EXT and p.is_file()]
    # 촬영 시각 순 정렬 (없으면 파일명 순)
    def key(p: Path):
        try:
            return (probe(p).creation_time or "~", p.name)
        except Exception:
            return ("~", p.name)
    return sorted(vids, key=key)


def require(binary: str) -> None:
    if not shutil.which(binary):
        raise SystemExit(f"{binary} 가 필요합니다. setup.sh 를 먼저 실행하세요.")


def fmt_t(sec: float) -> str:
    m, s = divmod(max(sec, 0), 60)
    return f"{int(m)}:{s:04.1f}"
