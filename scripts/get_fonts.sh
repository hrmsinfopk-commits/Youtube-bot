#!/usr/bin/env bash
# Free Google Fonts download (captions + thumbnails)
set -e
mkdir -p fonts
B=https://github.com/google/fonts/raw/main/ofl
curl -sSfL -o fonts/Anton-Regular.ttf "$B/anton/Anton-Regular.ttf" || echo "Anton font download failed"
curl -sSfL -o fonts/NotoNastaliqUrdu.ttf "$B/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf" || echo "Urdu font download failed"
curl -sSfL -o fonts/NotoSansDevanagari.ttf "$B/notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf" || echo "Hindi font download failed"

curl -sSfL -o fonts/SpecialElite-Regular.ttf "$B/specialelite/SpecialElite-Regular.ttf" || echo "Special Elite font download failed"
ls -la fonts
