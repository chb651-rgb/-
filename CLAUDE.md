# 일상 쇼츠/릴스 만들기 — 작업 안내 (Claude용)

사용자가 휴대폰·카메라·액션캠으로 찍은 영상을 보내면 **재미있는 세로 쇼츠/릴스(1080x1920)** 로 만들어 준다.
사용자는 한국어로 대화하고, 주로 휴대폰으로 본다. 답변은 짧고 쉬운 한국어로.

## 세션 시작 시 준비
```bash
bash setup.sh          # 한글 폰트, ffmpeg, faster-whisper 등 설치 (이미 있으면 금방 끝남)
```
- Whisper 모델은 Hugging Face에서 받는다. 환경 허용 목록에 `huggingface.co`, `us.aws.cdn.hf.co` 등이 이미 들어 있다.
- 영상은 Google Drive 공유 링크로 받는다 (`drive.google.com`, `drive.usercontent.google.com` 허용됨).
  공유가 '링크가 있는 모든 사용자'가 아니면 내려받기가 실패한다 → 사용자에게 공유 설정을 바꿔 달라고 한다.

## 작업 순서
1. **받기**: `python -m shorts fetch <드라이브 링크>` → `work/input/`
   - 링크 없이 "다 올렸어"라고 하면, 전에 받은 폴더 링크를 다시 쓴다.
   - Drive 커넥터(`search_files`, `parentId = '<폴더ID>'`)로 파일 목록만 먼저 확인할 수 있다 (내려받기는 fetch로).
2. **분석**: `python -m shorts analyze` (빠르게 하려면 `--model small`)
   - `work/analysis/report.md` : 영상별 ✂️ 버릴 장면 / ⭐ 하이라이트 후보 / 대사
   - `work/analysis/<영상>/sheet.jpg` : 시간표시 썸네일 모음 → **반드시 Read로 직접 보고** 무슨 장면인지 파악한다.
     숫자 점수만 믿지 말 것. 귀여운 표정, 웃긴 순간, 풍경 같은 건 눈으로 봐야 안다.
   - 애매한 시점은 `python -m shorts frames <영상> 12.5 30` 으로 프레임을 뽑아 확인한다.
3. **편집안**: `python -m shorts plan --target 30 --title "제목"` → `work/shorts.yaml`
   - 이 파일을 Claude가 직접 다듬는 게 핵심이다:
     - 지루한/중복 장면 빼고, 순서를 이야기 흐름(도입 → 하이라이트 → 마무리)에 맞게 조정
     - 첫 1~2초에 가장 눈길 끄는 장면 (후킹)
     - `captions`에 **재미 자막**: 짧고(10자 내외) 상황에 맞는 드립, 'ㅋㅋ', 속마음 자막 등. `style: pop`
     - 같은 장소에서 이어지는 장면은 `cut`, 장소/시간이 바뀌면 `slideleft`/`zoomin`/`smoothup` 같은 전환
     - 움직임 많은 순간은 `speed: 0.5`(슬로모션), 지루하게 긴 이동은 `speed: 1.5~2`
     - 가로 영상(액션캠)은 `fit: crop` + `crop_x`로 피사체 위치 맞추기, 피사체가 넓게 퍼져 있으면 `fit: blur`
     - 이모지는 폰트에 없어서 안 나온다 → 쓰지 말 것
4. **미리보기**: `python -m shorts render work/shorts.yaml --preview` → 프레임 몇 장 뽑아 Read로 확인
   (자막 겹침, 잘린 얼굴, 전환 위치)
5. **최종**: `python -m shorts render work/shorts.yaml` → `work/output/shorts.mp4`
   - SendUserFile로 사용자에게 보낸다. 사용자에게 알릴 것:
     - 버린 장면 요약 (왜 뺐는지: 어두움/흔들림/정지 화면 등)
     - 넣은 장면과 재미 자막 목록
     - 고치고 싶은 점 있으면 말해 달라고 (자막 문구, 길이, 순서, 음악 등)
   - BGM 파일을 사용자가 주면 `bgm:` 에 경로 지정 (말할 때 자동으로 작아짐). 저작권 있는 음악은 넣지 말고, 플랫폼 앱에서 음악을 넣는 것도 안내.

## 구조
```
shorts/
  common.py   ffprobe, 경로, 폰트, 출력 규격
  fetch.py    Google Drive 내려받기 (gdown)
  analyze.py  밝기/선명도/움직임/소리/음성인식 → 지루한 구간, 하이라이트 후보, 썸네일
  plan.py     하이라이트 → edit.yaml 자동 생성
  render.py   edit.yaml → ffmpeg (자르기, 9:16, xfade 전환, ASS 자막, BGM 덕킹, -14 LUFS)
work/         원본·분석·결과물 (git에 안 올림, 세션 끝나면 사라짐 → 결과물은 꼭 사용자에게 전달)
```

## 주의
- `work/` 는 컨테이너에만 있다. 결과 영상은 SendUserFile 로 꼭 전달한다 (용량이 크면 Drive에 올리는 방법 안내).
- 아이폰 HDR(HLG) 영상은 자동으로 SDR 변환된다.
- 판정 임계값(`analyze.py` 상단 DARK/BLUR/STATIC/QUIET_DB)은 실제 영상을 보고 맞지 않으면 조정한다.
