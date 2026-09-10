#!/bin/sh
# 双击运行：ChatCut 环境预检 / 自动安装（macOS）
# 也可以：sh scripts/install-macos.command
cd "$(dirname "$0")/.." || exit 1

PY=""
for c in python3 /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "没找到 python3。请先安装：xcode-select --install"
  echo "装好后重新双击本文件。"
  read -r _
  exit 1
fi

"$PY" scripts/ensure-chatcut.py
echo
echo "按回车键关闭这个窗口。"
read -r _
