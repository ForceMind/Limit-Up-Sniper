#!/bin/bash

# Limit-Up Sniper 一键部署脚本
# 适用系统: Ubuntu 20.04/22.04 LTS
# 用法: sudo ./install.sh

set -e

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   Limit-Up Sniper 一键部署脚本          ${NC}"
echo -e "${GREEN}=========================================${NC}"

# 1. 检查 Root 权限
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}[Error] 请使用 sudo 运行此脚本: sudo ./install.sh${NC}"
  exit 1
fi

# 2. 安装系统依赖
echo -e "${YELLOW}[1/6] 正在安装系统依赖 (Python3, Git, Nginx)...${NC}"
apt update -qq
apt install -y python3 python3-pip python3-venv git nginx -qq

# 3. 设置 Python 环境
echo -e "${YELLOW}[2/6] 配置 Python 虚拟环境...${NC}"
APP_DIR=$(pwd)
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
echo "正在安装 Python 依赖 (这可能需要几分钟)..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 4. 配置 API Key
echo -e "${YELLOW}[3/6] 配置 Deepseek API...${NC}"
read -p "请输入您的 Deepseek API Key: " API_KEY
if [ -z "$API_KEY" ]; then
    echo -e "${RED}[Error] API Key 不能为空。${NC}"
    exit 1
fi

# 5. 配置 Systemd 服务
echo -e "${YELLOW}[4/6] 配置后台服务 (Systemd)...${NC}"

# 确定运行用户
RUN_USER=$SUDO_USER
if [ -z "$RUN_USER" ]; then
    RUN_USER="root"
fi

SERVICE_FILE="/etc/systemd/system/limit-up-sniper.service"
cat > $SERVICE_FILE <<EOF
[Unit]
Description=Limit-Up Sniper FastAPI Service
After=network.target

[Service]
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="DEEPSEEK_API_KEY=$API_KEY"
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable limit-up-sniper
systemctl restart limit-up-sniper

# 6. 配置 Nginx
echo -e "${YELLOW}[5/6] 配置 Nginx 反向代理...${NC}"

# 尝试获取公网 IP
SERVER_IP=$(curl -s ifconfig.me || echo "your_server_ip")
read -p "请输入服务器 IP 或域名 (默认: $SERVER_IP): " USER_IP
USER_IP=${USER_IP:-$SERVER_IP}

NGINX_CONF="/etc/nginx/sites-available/limit-up-sniper"
cat > $NGINX_CONF <<EOF
server {
    listen 80;
    server_name $USER_IP;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
EOF

ln -sf $NGINX_CONF /etc/nginx/sites-enabled/
# 移除默认配置以避免冲突
rm -f /etc/nginx/sites-enabled/default

nginx -t
if [ $? -eq 0 ]; then
    systemctl restart nginx
else
    echo -e "${RED}[Error] Nginx 配置有误，请检查。${NC}"
    exit 1
fi

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   ✅ 部署成功! (Deployment Success)     ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "访问地址: http://$USER_IP"
echo -e "查看日志: sudo journalctl -u limit-up-sniper -f"
