"""쇼츠/릴스 편집 도구.

  python -m shorts fetch <드라이브 링크...>     # 영상 받기 -> work/input
  python -m shorts analyze [영상...]            # 지루한 장면/하이라이트/자막 분석
  python -m shorts plan [--target 30]           # 편집안 work/<name>.yaml 자동 생성
  python -m shorts render work/shorts.yaml      # 최종 영상 work/output/*.mp4
  python -m shorts auto <드라이브 링크>         # 위 과정 한 번에
  python -m shorts frames <영상> 12.5 30 ...    # 특정 시점 프레임 이미지 뽑기 (검토용)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import ANALYSIS, INPUT, LABEL_FONT_FILE, list_videos, require, run


def main() -> None:
    ap = argparse.ArgumentParser(prog="shorts", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch"); f.add_argument("urls", nargs="+")

    a = sub.add_parser("analyze"); a.add_argument("videos", nargs="*", type=Path)
    a.add_argument("--model", default="large-v3-turbo",
                   help="Whisper 모델 (빠르게: small)")
    a.add_argument("--prompt", default="",
                   help="음성 인식 힌트 단어 (예: '알보칠, 구내염, 면봉'). 주면 자막을 다시 인식")

    p = sub.add_parser("plan")
    p.add_argument("--target", type=float, default=30, help="목표 길이(초)")
    p.add_argument("--name", default="shorts"); p.add_argument("--title", default="")
    p.add_argument("--fit", default="crop", choices=["crop", "blur"])

    r = sub.add_parser("render"); r.add_argument("edit", type=Path)
    r.add_argument("-o", "--out", type=Path); r.add_argument("--preview", action="store_true",
                                                            help="저화질 빠른 미리보기")

    au = sub.add_parser("auto"); au.add_argument("urls", nargs="*")
    au.add_argument("--target", type=float, default=30); au.add_argument("--title", default="")
    au.add_argument("--model", default="large-v3-turbo")

    fr = sub.add_parser("frames"); fr.add_argument("video", type=Path)
    fr.add_argument("times", nargs="+", type=float)

    args = ap.parse_args()
    require("ffmpeg")

    if args.cmd == "fetch":
        from .fetch import fetch
        fetch(args.urls)
    elif args.cmd == "analyze":
        from .analyze import analyze
        vids = args.videos or list_videos(INPUT)
        if not vids:
            raise SystemExit(f"{INPUT} 에 영상이 없어요.")
        analyze(vids, args.model, args.prompt)
    elif args.cmd == "plan":
        from .plan import auto_plan
        auto_plan(args.target, args.name, args.title, args.fit)
    elif args.cmd == "render":
        from .render import render
        render(args.edit, args.out, args.preview)
    elif args.cmd == "auto":
        from .analyze import analyze
        from .fetch import fetch
        from .plan import auto_plan
        from .render import render
        if args.urls:
            fetch(args.urls)
        analyze(list_videos(INPUT), args.model)
        render(auto_plan(args.target, title=args.title))
    elif args.cmd == "frames":
        d = ANALYSIS / args.video.stem / "frames"
        d.mkdir(parents=True, exist_ok=True)
        for t in args.times:
            o = d / f"{t:07.2f}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", args.video, "-frames:v", "1",
                 "-vf", f"scale=-2:640,drawtext=fontfile={LABEL_FONT_FILE}:text='{t:.1f}s':"
                        "x=10:y=10:fontsize=32:fontcolor=white:box=1:boxcolor=black@0.6", o])
            print(o)


if __name__ == "__main__":
    main()
