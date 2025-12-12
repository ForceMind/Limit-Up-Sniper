#!/bin/bash

# update.sh - 自动更新代码并重启服务
# 用法: sudo ./update.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Limit-Up Sniper 更新脚本 ===${NC}"

# 1. 检查 Root 权限
if [ "$EUID" -ne 0 ]; then 
  echo -e "${YELLOW}提示: 建议使用 sudo 运行以确保服务重启成功${NC}"
fi

# 2. 拉取最新代码
echo -e "${YELLOW}[1/3] 拉取最新代码...${NC}"
git config --global --add safe.directory $(pwd)
git pull
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Git pull 失败，尝试强制重置 (git reset --hard)...${NC}"
    read -p "是否丢弃本地修改并强制更新? (y/n): " CONFIRM
    if [ "$CONFIRM" == "y" ]; then
        git fetch --all
        git reset --hard origin/main
    else
        echo "更新取消。"
        exit 1
    fi
fi

# 3. 更新依赖
echo -e "${YELLOW}[2/3] 更新 Python 依赖...${NC}"
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt -q
else
    echo "未找到虚拟环境，跳过依赖更新。"
fi

# 3.1 检查并修复 Service 文件路径 (针对 v2.0 结构变更)
SERVICE_FILE="/etc/systemd/system/limit-up-sniper.service"
if [ -f "$SERVICE_FILE" ]; then
    if grep -q "uvicorn main:app" "$SERVICE_FILE"; then
        echo -e "${YELLOW}[Fix] 检测到旧版服务配置，正在更新为 app.main:app...${NC}"
        sed -i 's/uvicorn main:app/uvicorn app.main:app/g' "$SERVICE_FILE"
        systemctl daemon-reload
    fi
fi

# 4. 重启服务
echo -e "${YELLOW}[3/3] 重启服务...${NC}"
if systemctl is-active --quiet limit-up-sniper; then
    sudo systemctl restart limit-up-sniper
    echo -e "${GREEN}服务已重启!${NC}"
else
    echo -e "${YELLOW}服务未运行，尝试启动...${NC}"
    sudo systemctl start limit-up-sniper
fi

# 5. 检查状态
echo -e "${GREEN}更新完成! 当前状态:${NC}"
sudo systemctl status limit-up-sniper --no-pager | head -n 10
