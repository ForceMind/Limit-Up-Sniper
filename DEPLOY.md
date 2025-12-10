# 🚀 部署指南 (Deployment Guide)

本指南将指导你如何在 Linux 服务器 (以 Ubuntu 22.04 为例) 上部署 **Limit-Up Sniper**。

## ⚡ 一键部署 (推荐)

我们提供了一个自动化脚本，可以帮你完成所有安装步骤。

1.  **下载代码**
    ```bash
    cd ~
    git clone https://github.com/ForceMind/Limit-Up-Sniper.git limit-up-sniper
    cd limit-up-sniper
    ```

2.  **运行安装脚本**
    ```bash
    sudo bash install.sh
    ```

3.  **按提示操作**
    *   脚本会自动安装 Python、Nginx 等依赖。
    *   当提示输入 **Deepseek API Key** 时，请粘贴你的密钥。
    *   当提示输入 **IP 或域名** 时，确认即可。

4.  **完成**
    *   脚本运行结束后，直接访问显示的 URL 即可使用。

## 🔄 如何更新 (Update)

当你拉取了最新代码后，建议重新运行安装脚本以确保所有配置（如 Nginx、Systemd）都已更新。

```bash
cd limit-up-sniper
git pull
sudo bash install.sh
```

---

## 🛠️ 手动部署 (Manual Deployment)

如果你想手动控制每一个步骤，请参考以下流程。

## 1. 环境准备

首先，更新系统并安装 Python 3 和 Git。

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git nginx -y
```

## 2. 获取代码

将项目克隆到服务器的 `/var/www` 或 `~/` 目录下。

```bash
cd ~
git clone <你的仓库地址> limit-up-sniper
cd limit-up-sniper
```

## 3. 配置 Python 环境

建议使用虚拟环境，避免污染系统库。

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 4. 配置环境变量

为了安全起见，不要直接修改代码中的 API Key。我们将在 Systemd 服务中配置它。

## 5. 配置 Systemd 守护进程

使用 Systemd 让应用在后台运行，并开机自启。

创建服务文件：
```bash
sudo nano /etc/systemd/system/limit-up-sniper.service
```

粘贴以下内容 (请修改 `User`, `WorkingDirectory`, `ExecStart` 中的路径和 `DEEPSEEK_API_KEY`)：

```ini
[Unit]
Description=Limit-Up Sniper FastAPI Service
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/limit-up-sniper
Environment="PATH=/root/limit-up-sniper/venv/bin"
Environment="DEEPSEEK_API_KEY=sk-你的Deepseek密钥"
ExecStart=/root/limit-up-sniper/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1

# 自动重启配置
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

保存并退出 (`Ctrl+O`, `Enter`, `Ctrl+X`)。

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl start limit-up-sniper
sudo systemctl enable limit-up-sniper
```

检查状态：
```bash
sudo systemctl status limit-up-sniper
```

## 6. 配置 Nginx 反向代理

使用 Nginx 将外部流量转发到本地的 8000 端口。

创建 Nginx 配置文件：
```bash
sudo nano /etc/nginx/sites-available/limit-up-sniper
```

粘贴以下内容 (将 `your_server_ip` 替换为你的服务器 IP 或域名)：

```nginx
server {
    listen 80;
    server_name your_server_ip;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket 支持 (关键配置)
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

启用配置并重启 Nginx：
```bash
sudo ln -s /etc/nginx/sites-available/limit-up-sniper /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 7. 访问

现在，你可以通过浏览器访问 `http://<你的服务器IP>` 来使用系统了。

## 8. 常用维护命令

*   **查看应用日志**:
    ```bash
    sudo journalctl -u limit-up-sniper -f
    ```
*   **重启应用**:
    ```bash
    sudo systemctl restart limit-up-sniper
    ```
*   **更新代码**:
    ```bash
    cd ~/limit-up-sniper
    git pull
    sudo systemctl restart limit-up-sniper
    ```

## 2. 上传代码
将整个 `Limit-Up-Sniper` 文件夹上传到服务器。

## 3. 安装依赖
```bash
cd Limit-Up-Sniper
pip install -r requirements.txt
```

## 4. 设置环境变量 (Deepseek Key)
```bash
export DEEPSEEK_API_KEY="your-key-here"
```

## 5. 后台运行 (使用 nohup)
```bash
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

## 6. 访问
在浏览器访问 `http://服务器IP:8000`。

## 7. (可选) 使用 Nginx 反向代理
如果需要绑定域名或使用 80 端口，建议配置 Nginx。
