# 일상 쇼츠/릴스 자동 편집

휴대폰·카메라·액션캠 영상 → 세로 쇼츠/릴스(1080x1920, 30fps)

- ✂️ 지루한 장면 찾기: 어두움, 흐림, 심한 흔들림, 정지 화면 + 조용함, 촬영 시작/끝
- ⭐ 하이라이트 찾기: 움직임, 웃음·큰소리, 대화 (말이 잘리지 않게 문장 단위로 자름)
- 🎬 화면 전환: 컷, 슬라이드, 줌, 원형, 와이프 등 (ffmpeg xfade)
- 💬 자막: Whisper 한국어 자동 자막 + 노란 강조 '재미 자막' + 상단 제목
- 🎵 배경음악: 말할 때 자동으로 작아짐, 쇼츠 표준 음량(-14 LUFS)

```bash
bash setup.sh
python -m shorts fetch "https://drive.google.com/drive/folders/..."
python -m shorts analyze                 # work/analysis/report.md
python -m shorts plan --target 30 --title "제목"   # work/shorts.yaml (직접 수정 가능)
python -m shorts render work/shorts.yaml --preview
python -m shorts render work/shorts.yaml # work/output/shorts.mp4
```

편집 대본(`work/shorts.yaml`) 항목 설명은 파일 맨 위 주석에 있어요.
