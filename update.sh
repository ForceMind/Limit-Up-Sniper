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

# 备份本地数据 (防止 git reset 误删)
BACKUP_DIR="._data_backup"
if [ -d "data" ]; then
    echo -e "${YELLOW}正在备份 data 目录...${NC}"
    rm -rf "$BACKUP_DIR"
    cp -r data "$BACKUP_DIR"
fi

git config --global --add safe.directory $(pwd)
# 使用 if ! 命令; then 的方式，即使开启了 set -e 也不会导致脚本崩溃
if ! git pull; then
    echo -e "${YELLOW}Git pull 失败，自动执行强制重置 (git reset --hard)...${NC}"
    
    # 获取当前分支名称 (比写死 main 更安全，防止你在 dev 分支时切回 main)
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    
    git fetch --all
    git reset --hard "origin/$CURRENT_BRANCH"
else
    echo -e "${GREEN}Git pull 成功。${NC}"
fi

# 恢复本地数据
if [ -d "$BACKUP_DIR" ]; then
    echo -e "${YELLOW}正在恢复 data 目录...${NC}"
    mkdir -p data
    cp -r "$BACKUP_DIR"/* data/
    rm -rf "$BACKUP_DIR"
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
