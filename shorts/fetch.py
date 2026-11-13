"""Google Drive 공유 링크(폴더/파일)에서 영상 내려받기.

공유 설정이 '링크가 있는 모든 사용자'여야 합니다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import INPUT, VIDEO_EXT


def _drive_id(url: str) -> tuple[str, str]:
    m = re.search(r"/folders/([\w-]+)", url)
    if m:
        return "folder", m.group(1)
    m = re.search(r"(?:/d/|id=)([\w-]+)", url)
    if m:
        return "file", m.group(1)
    if re.fullmatch(r"[\w-]{20,}", url):
        return "file", url
    raise SystemExit(f"Drive 링크를 이해하지 못했어요: {url}")


def fetch(urls: list[str], dest: Path = INPUT) -> list[Path]:
    import gdown

    dest.mkdir(parents=True, exist_ok=True)
    got: list[Path] = []
    for url in urls:
        kind, fid = _drive_id(url)
        if kind == "folder":
            files = gdown.download_folder(id=fid, output=str(dest), quiet=False,
                                          remaining_ok=True, resume=True) or []
            got += [Path(f) for f in files]
        else:
            f = gdown.download(id=fid, output=str(dest) + "/", quiet=False, resume=True)
            if f:
                got.append(Path(f))
    vids = [p for p in got if p.suffix.lower() in VIDEO_EXT]
    print(f"\n영상 {len(vids)}개 받음 -> {dest}")
    for p in vids:
        print("  ", p.relative_to(dest) if p.is_relative_to(dest) else p,
              f"{p.stat().st_size/1e6:.0f}MB")
    return vids
