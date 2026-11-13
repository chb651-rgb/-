#!/usr/bin/env bash
# 쇼츠 편집 도구 설치 (Ubuntu). 여러 번 실행해도 안전.
set -e
need_apt=0
command -v ffmpeg >/dev/null || need_apt=1
fc-list | grep -q "Noto Sans CJK KR" || need_apt=1
fc-list | grep -qi "NanumSquare" || need_apt=1
if [ "$need_apt" = 1 ]; then
  apt-get update -q >/dev/null
  apt-get install -y -q ffmpeg fonts-noto-cjk fonts-nanum fonts-nanum-extra >/dev/null
fi
pip install -q -r "$(dirname "$0")/requirements.txt" 2>&1 | grep -v -i "warning" || true
echo "준비 완료"
