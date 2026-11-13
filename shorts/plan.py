"""분석 결과 -> 편집안(edit.yaml) 자동 생성.

edit.yaml 은 사람이(또는 Claude가) 직접 고쳐서 다시 렌더링하는 '편집 대본'이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .common import ANALYSIS, WORK

# 다른 영상/장면으로 넘어갈 때 돌려 쓰는 전환 (ffmpeg xfade 이름)
SCENE_TRANSITIONS = ["slideleft", "zoomin", "smoothup", "circleopen", "wipeleft", "slideup",
                     "radial", "smoothleft"]

EDIT_HELP = """\
# ───────────────────────────────────────────────────────────
#  쇼츠/릴스 편집 대본.  고친 뒤:  python -m shorts render <이 파일>
#
#  title      : 첫 2.5초 상단에 뜨는 제목 (없애려면 "")
#  fit        : 가로 영상 처리  crop=꽉 채우게 자름 | blur=흐린 배경 위에 원본
#  subtitles  : auto=음성 자동 자막 | off
#  replace    : 잘못 인식된 자막 고치기 {틀린말: 맞는말}, 맞는말을 ""로 두면 그 자막 삭제
#  bgm        : 배경음악 파일 경로 (기본 제공: work/music/bgm_sneaky.wav) (말할 때 자동으로 작아짐), 없으면 null
#  clips      : 순서대로 이어붙일 장면
#    in/out     원본 영상의 시작/끝 초
#    speed      0.5=슬로모션, 1.5=빨리감기
#    crop_x     가로 영상을 자를 때 위치 (0 왼쪽 ~ 0.5 가운데 ~ 1 오른쪽)
#    zoom       1.0=그대로, 1.2=살짝 확대(펀치인)
#    transition 다음 장면으로 넘어가는 효과:
#               cut, fade, slideleft, slideright, slideup, smoothleft, smoothup,
#               zoomin, circleopen, wipeleft, radial, dissolve, pixelize
#    captions   재미 자막. at=장면 시작 기준 초, dur=길이,
#               style: pop(노란 큰 글씨, 강조) | sub(일반 자막) | top(상단 고정)
#               (이모지는 폰트에 없어서 안 나와요)
#    sub        이 장면에 음성 자동 자막 표시 여부
#    sfx        효과음 [{at: 장면 시작 기준 초, name: 이름 또는 파일, vol: 0.8, stop_bgm: true}]
#               name: sad_trombone(허무), suspense(긴장), sparkle(반짝), pop(뽁), whoosh(휙)
#               stop_bgm: true 면 그 순간 배경음악이 뚝 끊김
#               pause_bgm: 2.5 면 그 순간부터 2.5초 동안만 배경음악 멈춤
# ───────────────────────────────────────────────────────────
"""


def load_analyses() -> list[dict]:
    res = []
    for f in sorted(ANALYSIS.glob("*/analysis.json")):
        res.append(json.loads(f.read_text()))
    if not res:
        raise SystemExit("분석 결과가 없어요. 먼저: python -m shorts analyze")
    # 촬영 순서
    return sorted(res, key=lambda r: (r.get("creation_time") or "~", r["name"]))


def auto_plan(target: float = 30.0, name: str = "shorts", title: str = "",
              fit: str = "crop") -> Path:
    analyses = load_analyses()
    order = {r["file"]: i for i, r in enumerate(analyses)}
    cands = [{**h, "file": r["file"]} for r in analyses for h in r["highlights"]]
    if not cands:
        raise SystemExit("하이라이트 후보가 없어요. 영상이 너무 짧거나 전부 어두운/정지 화면일 수 있어요.")

    picked, total = [], 0.0
    # 1) 영상마다 최고 장면 하나씩 (괜찮은 것만)  2) 나머지는 점수순
    best = {}
    for c in cands:
        if c["score"] >= 0.3 and c["score"] > best.get(c["file"], {"score": -1})["score"]:
            best[c["file"]] = c
    for c in sorted(best.values(), key=lambda c: -c["score"]) + sorted(cands, key=lambda c: -c["score"]):
        if c in picked:
            continue
        if total >= target:
            break
        picked.append(c)
        total += c["end"] - c["start"] - 0.3
    picked.sort(key=lambda c: (order[c["file"]], c["start"]))

    clips, k = [], 0
    for i, c in enumerate(picked):
        nxt = picked[i + 1] if i + 1 < len(picked) else None
        if nxt is None:
            tr = "fade"
        elif nxt["file"] == c["file"] and nxt["start"] - c["end"] < 8:
            tr = "cut"                       # 같은 장면 이어짐 -> 깔끔한 컷
        else:
            tr = SCENE_TRANSITIONS[k % len(SCENE_TRANSITIONS)]
            k += 1
        clips.append({
            "src": str(Path(c["file"]).relative_to(WORK.parent)) if Path(c["file"]).is_relative_to(WORK.parent) else c["file"],
            "in": c["start"], "out": c["end"], "speed": 1.0, "crop_x": 0.5, "zoom": 1.0,
            "transition": tr, "sub": True, "captions": [],
            "note": f"점수 {c['score']:.2f} / {', '.join(c['why'])}" + (f' / "{c["text"]}"' if c["text"] else ""),
        })

    plan = {"title": title, "fit": fit, "subtitles": "auto", "replace": {}, "bgm": None, "bgm_volume": 0.25,
            "clips": clips}
    out = WORK / f"{name}.yaml"
    out.write_text(EDIT_HELP + yaml.safe_dump(plan, allow_unicode=True, sort_keys=False, width=200))
    print(f"편집안: {out}  (장면 {len(clips)}개, 약 {total:.0f}초)")
    return out
