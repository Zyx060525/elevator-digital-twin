#!/usr/bin/env bash
# 生成提交证据图（真实运行输出 → PNG 截图 + UTF-8 日志）
# 用法：bash 一键生成证据_Linux.sh          # 全部证据（Web 截图需本机有 chrome / chromium）
#       bash 一键生成证据_Linux.sh --no-web # 只生成控制台类证据
set -e
cd "$(dirname "$0")"
python3 生成证据图.py "$@"
echo
echo "产物在 证据图/ 目录，可直接上传赛事平台。"
