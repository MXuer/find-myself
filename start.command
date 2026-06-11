#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "尚未安装，请先双击 setup.command。"
  read -n 1 -s -r -p "按任意键退出"
  exit 1
fi

source .venv/bin/activate
python -m streamlit run app.py --server.address 127.0.0.1
