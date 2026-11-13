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


def _download(fid: str, dest: Path, name: str | None = None) -> Path | None:
    """drive.usercontent.google.com 에서 직접 받기 (큰 파일도 확인 페이지 없이)."""
    import requests

    url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        if "text/html" in r.headers.get("content-type", ""):
            print(f"  ! {name or fid}: 내려받기 실패 (공유 설정을 '링크가 있는 모든 사용자'로 바꿔 주세요)")
            return None
        if not name:
            cd = r.headers.get("content-disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)", cd)
            from urllib.parse import unquote
            name = unquote(m.group(1) or m.group(2)) if m else f"{fid}.mp4"
        out = dest / name
        if out.exists() and out.stat().st_size == int(r.headers.get("content-length", -1)):
            print(f"  = {name} (이미 있음)")
            return out
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(out, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
        print(f"  ✓ {name}  {done / 1e6:.0f}MB" + ("" if not total or done == total else "  (크기 불일치!)"))
        return out


def fetch(urls: list[str], dest: Path = INPUT) -> list[Path]:
    import gdown

    dest.mkdir(parents=True, exist_ok=True)
    got: list[Path] = []
    for url in urls:
        kind, fid = _drive_id(url)
        if kind == "folder":
            # 목록만 가져오고(하위 폴더 포함), 내려받기는 직접
            items = gdown.download_folder(id=fid, output=str(dest), quiet=True,
                                          skip_download=True) or []
            for it in items:
                if Path(it.path).suffix.lower() in VIDEO_EXT:
                    p = _download(it.id, dest, Path(it.path).name)
                    if p:
                        got.append(p)
        else:
            p = _download(fid, dest)
            if p:
                got.append(p)
    vids = [p for p in got if p.suffix.lower() in VIDEO_EXT]
    print(f"\n영상 {len(vids)}개 받음 -> {dest}")
    return vids
