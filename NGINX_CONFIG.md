# Nginx 反代配置指南

## 问题诊断

当使用 nginx 反代 Flask 应用时，Flask 通过 `request.remote_addr` 获取的是 nginx 服务器的 IP（通常为 127.0.0.1），而非真实用户 IP。

**症状：** 
- IP 记录显示为 `127.0.0.1|学号|时间戳`
- 第一个用户领票后，其他用户无法领票（IP限制误认为重复）

## 解决方案

### 1. Nginx 配置（重要！必须设置）

在你的 nginx 配置文件中，找到反代 Flask 的 `location` 块，添加以下请求头转发：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 改成你的域名

    location / {
        proxy_pass http://127.0.0.1:5000;  # Flask 运行地址
        
        # 关键：转发真实客户端IP信息
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
        
        # 其他建议配置
        proxy_redirect off;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
    }
}
```

### 2. Flask 代码已更新

后端代码已添加 `get_client_ip()` 函数，优先级如下：

```
1. X-Forwarded-For header（nginx 反代常用）
   → 取第一个 IP（原始客户端）
2. X-Real-IP header（某些反代使用）
3. CF-Connecting-IP header（Cloudflare 使用）
4. request.remote_addr（直连或作为最后备选）
```

## 验证步骤

### 检查 1：查看 Nginx 日志

```bash
tail -f /var/log/nginx/access.log
```

确保请求头包含客户端真实 IP 信息

### 检查 2：在 Flask 中添加调试日志

临时修改 `app.py` 中的 `ticket()` 函数，添加调试输出：

```python
print(f"[DEBUG] 客户端IP: {client_ip}")
print(f"[DEBUG] 原始remote_addr: {request.remote_addr}")
print(f"[DEBUG] X-Forwarded-For: {request.headers.get('X-Forwarded-For')}")
print(f"[DEBUG] X-Real-IP: {request.headers.get('X-Real-IP')}")
```

查看 Flask 日志输出：

```bash
tail -f Flask应用日志
```

### 检查 3：验证数据库记录

查询 IP 日志表：

```sql
sqlite3 ticket.db
SELECT * FROM ip_ticket_log ORDER BY timestamp DESC LIMIT 5;
```

应该看到真实用户 IP（如 `203.0.113.45`），而不是 `127.0.0.1`

## 常见 Nginx 反代类型配置

### A. 反向代理（单一后端）

```nginx
upstream flask_backend {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://flask_backend;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
    }
}
```

### B. 负载均衡（多后端）

```nginx
upstream flask_backend {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://flask_backend;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
    }
}
```

### C. Docker 容器（通过容器名称）

```nginx
upstream flask_backend {
    server flask-app:5000;  # Docker 容器名称
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://flask_backend;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
    }
}
```

## 调试技巧

### 1. 查看 Nginx 变量值

在 nginx 配置中添加自定义日志格式：

```nginx
log_format proxy_debug '$remote_addr - $remote_user [$time_local] '
                       '"$request" $status $body_bytes_sent '
                       '"$http_referer" "$http_user_agent" '
                       'X-Forwarded-For: "$http_x_forwarded_for" '
                       'X-Real-IP: "$http_x_real_ip"';

access_log /var/log/nginx/proxy_debug.log proxy_debug;
```

### 2. 使用 curl 本地测试

```bash
# 模拟来自不同IP的请求
curl -X POST http://localhost:5000/ticket \
  -H "X-Forwarded-For: 203.0.113.45" \
  -d "student_id=123456&student_name=张三"

# 查看 Flask 是否正确识别为 203.0.113.45
```

### 3. 重载 Nginx 配置

修改后记得重载：

```bash
sudo nginx -t              # 检查语法
sudo systemctl reload nginx # 重载配置
```

## 故障排查

### 问题：修改后仍然显示 127.0.0.1

**可能原因：**
1. Nginx 配置未保存或未重载
   - 检查：`ps aux | grep nginx`
   - 重载：`sudo systemctl reload nginx`

2. Flask 应用未重启
   - 查看进程：`ps aux | grep python`
   - 重启：重新启动 Flask 应用

3. 使用了错误的请求头名称
   - 对比 nginx 发送的请求头名称
   - 确保大小不一致：应该是 `X-Forwarded-For`（大写F）

4. 读取了错误的变量
   - 检查代码中使用的是 `get_client_ip()` 函数
   - 不要直接使用 `request.remote_addr`

### 问题：多次 IP 地址串联

示例：`203.0.113.45, 203.0.113.44, 203.0.113.43`

**原因：** 多层反代（如经过多个 nginx 服务器）

**解决：** 代码已处理，自动取第一个 IP（原始客户端）

## 发布清单

- [ ] 更新 nginx 配置文件（添加 X-Forwarded-For 等请求头）
- [ ] 重载 nginx（`sudo systemctl reload nginx`）
- [ ] 重启 Flask 应用
- [ ] 清空旧的 IP 日志（可选）：在管理后台点击"一键清除 IP 记录"
- [ ] 用不同设备/IP 进行测试
- [ ] 验证数据库中记录的是真实 IP

## 其他信息

- Flask 函数：`get_client_ip()`（位置：app.py 中的认证部分之后）
- 数据库表：`ip_ticket_log`
- 修改前：125行，`client_ip = request.remote_addr`
- 修改后：218行，`client_ip = get_client_ip()`
