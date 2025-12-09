# 迎新晚会票务系统

一个基于 Flask + SQLite 的在线票务管理系统，支持学生在线领票、座位自动分配、管理员后台管理等功能。

## 📋 目录

- [系统概述](#系统概述)
- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [数据库设计](#数据库设计)
- [运行逻辑](#运行逻辑)
- [安装与部署](#安装与部署)
- [API 文档](#api-文档)
- [辅助脚本](#辅助脚本)

---

## 系统概述

本系统为迎新晚会设计，实现了完整的票务管理流程：
- 🎫 **学生端**：在线领票，实时查看座位信息和剩余票数
- 👨‍💼 **管理端**：控制取票窗口、管理座位分配、查看统计数据
- 🔒 **安全机制**：IP 限制、学号姓名验证、座位集合分阶段开放

## 核心功能

### 用户端功能
1. **在线领票**
   - 输入学号和姓名进行身份验证
   - 系统自动随机分配座位
   - 显示座位号、位置和票号（格式：NO.251221xxx）
   - 实时显示剩余座位数

2. **IP 限制**
   - 每个 IP 地址只能领取一张票
   - 同一 IP 可重复查询自己的票

3. **票务信息显示**
   - 取票窗口状态（开放/未开放）
   - 剩余座位数动态更新
   - 座位详情（座位ID + 位置）

### 管理端功能

1. **取票窗口管理**
   - 一键开放/关闭取票
   - 实时显示窗口状态

2. **座位集合管理**（两阶段开放机制）
   - 集合 1：6-14排，7-21列（中心区域）
   - 集合 2：其他座位（边缘区域）
   - 可分别控制每个集合的开放状态
   - 仅从已开放集合中分配座位

3. **座位管理**
   - 查看所有座位状态
   - 新增/删除座位
   - 修改座位占用情况
   - 支持批量导入

4. **用户管理**
   - 查看所有已领票用户
   - 手动分配/调整座位
   - 删除用户及其座位

5. **有效学号管理**
   - 维护合法学号库
   - 支持姓名信息

6. **测试工具**
   - 一键清除 IP 记录（便于测试）

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | Flask | 轻量级 Python Web 框架 |
| 数据库 | SQLite | 嵌入式关系型数据库 |
| 前端 | HTML + CSS + JavaScript | 原生前端技术 |
| 认证 | HTTP Basic Auth | 管理员接口保护 |
| Excel 处理 | pandas + openpyxl | 数据导入工具 |

## 数据库设计

### 表结构

#### 1. seats（座位表）
```sql
CREATE TABLE seats (
    seat_id INTEGER PRIMARY KEY,      -- 座位ID
    pos TEXT NOT NULL,                 -- 座位位置描述
    occupied BOOLEAN DEFAULT 0,        -- 是否已占用
    student_id TEXT,                   -- 占用学生的学号
    group_id INTEGER DEFAULT 1,        -- 所属集合（1或2）
    row_num INTEGER,                   -- 行号
    col_num INTEGER                    -- 列号
);
```

#### 2. users（用户表）
```sql
CREATE TABLE users (
    student_id TEXT PRIMARY KEY,       -- 学号
    seat_id INTEGER NOT NULL,          -- 分配的座位ID
    FOREIGN KEY (seat_id) REFERENCES seats(seat_id)
);
```

#### 3. valid_ids（有效学号表）
```sql
CREATE TABLE valid_ids (
    student_id TEXT PRIMARY KEY,       -- 学号
    student_name TEXT                  -- 学生姓名
);
```

#### 4. ip_ticket_log（IP 领票记录表）
```sql
CREATE TABLE ip_ticket_log (
    ip_address TEXT NOT NULL,          -- IP 地址
    student_id TEXT NOT NULL,          -- 学号
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 领票时间
    PRIMARY KEY (ip_address, student_id)
);
```

#### 5. ticket_status（取票窗口状态表）
```sql
CREATE TABLE ticket_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单例记录
    is_open BOOLEAN DEFAULT 0               -- 是否开放（0=关闭，1=开放）
);
```

#### 6. seat_groups（座位集合状态表）
```sql
CREATE TABLE seat_groups (
    id INTEGER PRIMARY KEY CHECK (id IN (1, 2)),  -- 集合ID
    group_id INTEGER,                             -- 集合编号
    is_open BOOLEAN DEFAULT 0                      -- 是否开放
);
```

## 运行逻辑

### 领票流程

```
用户访问 → 输入学号+姓名
    ↓
检查取票窗口状态
    ↓ (已开放)
验证学号和姓名是否匹配
    ↓ (通过)
检查该学号是否已领取
    ↓ (未领取)
检查 IP 是否已领票
    ↓ (未领取)
检查是否有开放的座位集合
    ↓ (有)
从开放集合中随机分配座位
    ↓
更新数据库 + 记录 IP
    ↓
返回座位信息 + 票号
```

### 座位集合分配逻辑

- **取票窗口关闭**：拒绝所有领票请求
- **取票窗口开放 + 集合1开放**：仅从集合1分配
- **取票窗口开放 + 集合2开放**：仅从集合2分配
- **取票窗口开放 + 两个集合都开放**：从两个集合的并集中分配
- **取票窗口开放 + 两个集合都关闭**：拒绝领票

### 管理员访问

1. 浏览器访问 `/admin`
2. 输入管理员账号密码（HTTP Basic Auth）
   - 默认账号：`admin`
   - 默认密码：`password`
   - 可通过环境变量 `ADMIN_USER` 和 `ADMIN_PASS` 自定义

## 安装与部署

### 环境要求
- Python 3.7+
- pip

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd ticketsystem
```

2. **创建虚拟环境（推荐）**
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **初始化数据库**

首次运行会自动创建数据库和表结构。如需导入座位和学号数据，参见[辅助脚本](#辅助脚本)。

5. **启动服务**
```bash
python app.py
```

默认运行在 `http://0.0.0.0:5000`

6. **自定义管理员账号（可选）**
```bash
# Windows
set ADMIN_USER=your_username
set ADMIN_PASS=your_password

# Linux/Mac
export ADMIN_USER=your_username
export ADMIN_PASS=your_password

python app.py
```

### 生产部署

推荐使用 Gunicorn + Nginx：

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务（4个worker）
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## API 文档

### 公开接口

#### 1. 领取票
```http
POST /ticket
Content-Type: application/x-www-form-urlencoded

student_id=学号&student_name=姓名
```

**响应示例**：
```json
{
  "status": "ok",
  "msg": "领取成功",
  "seat": 123,
  "pos": "第8排，第15列",
  "ticket_no": "NO.251221045"
}
```

#### 2. 获取剩余座位数
```http
GET /api/available-seats
```

**响应示例**：
```json
{
  "available": 150,
  "total": 267
}
```

#### 3. 获取取票窗口状态
```http
GET /admin/api/ticket-status
```

**响应示例**：
```json
{
  "is_open": 1
}
```

### 管理接口（需要认证）

所有 `/admin/api/*` 接口需要 HTTP Basic Auth 认证。

#### 座位管理
- `GET /admin/api/seats` - 获取所有座位
- `POST /admin/api/seats` - 新增座位
- `PUT /admin/api/seats/<seat_id>` - 更新座位
- `DELETE /admin/api/seats/<seat_id>` - 删除座位

#### 用户管理
- `GET /admin/api/users` - 获取所有用户
- `POST /admin/api/users` - 新增用户
- `PUT /admin/api/users/<student_id>` - 更新用户
- `DELETE /admin/api/users/<student_id>` - 删除用户

#### 有效学号管理
- `GET /admin/api/validids` - 获取所有有效学号
- `POST /admin/api/validids` - 添加有效学号
- `DELETE /admin/api/validids/<student_id>` - 删除有效学号

#### 系统管理
- `POST /admin/api/ticket-status` - 开放/关闭取票窗口
- `GET /admin/api/seat-groups` - 获取座位集合状态
- `POST /admin/api/seat-groups/<group_id>` - 开放/关闭座位集合
- `POST /admin/api/clear-ip-log` - 清除 IP 记录
- `GET /admin/api/stats` - 获取统计数据

## 辅助脚本

### 1. import_names.py - 导入学号姓名

从 Excel 文件批量导入学号和姓名到 `valid_ids` 表。

**用法**：
```bash
# 仅更新已存在的学号
python import_names.py

# 插入缺失的学号
python import_names.py --insert-missing
```

**数据源**：
- `data_get/25.xlsx`
- `data_get/241.xlsx`
- `data_get/242.xlsx`

### 2. update_seats_layout.py - 更新座位布局

为座位表添加行列信息，删除指定座位，设置座位集合。

**功能**：
- 解析 `pos` 字段为 `row_num` 和 `col_num`
- 删除第5排7-21列的座位
- 设置座位集合分组
  - 集合1：6-14排，7-21列
  - 集合2：其他座位

**用法**：
```bash
python update_seats_layout.py
```

**警告**：此脚本会直接修改数据库，请先备份 `ticket.db`！

### 3. data_get/extract.py - 提取学号

从 Excel 文件提取学号到文本文件。

**用法**：
```python
from data_get.extract import extract_ids
extract_ids("data_get/25.xlsx", "data_get/stu_num.txt")
```

## 项目结构

```
ticketsystem/
├── app.py                      # 主应用程序
├── ticket.db                   # SQLite 数据库
├── requirements.txt            # Python 依赖
├── README.md                   # 项目文档
├── import_names.py             # 导入学号脚本
├── update_seats_layout.py      # 座位布局更新脚本
├── templates/                  # HTML 模板
│   ├── index.html             # 用户端页面
│   └── admin.html             # 管理端页面
└── data_get/                   # 数据处理工具
```

## 常见问题

### Q1: 如何重置所有领票记录？

在管理员后台点击"一键清除 IP 记录"，然后手动删除所有用户和座位的占用状态。

### Q2: 如何修改座位总数？

使用 `update_seats_layout.py` 或在管理后台手动添加/删除座位。

### Q3: 忘记管理员密码怎么办？

重新设置环境变量 `ADMIN_USER` 和 `ADMIN_PASS`，或直接修改代码中的默认值。

### Q4: 数据库损坏如何恢复？

定期备份 `ticket.db` 文件。恢复时直接替换损坏的数据库文件。

## 许可证

MIT License

## 作者

票务系统开发团队

## 更新日志

### v1.0.0 (2024-12-09)
- ✅ 核心领票功能
- ✅ IP 限制机制
- ✅ 取票窗口控制
- ✅ 座位集合分阶段管理
- ✅ 管理员后台
- ✅ 实时座位数显示
- ✅ 票号生成（NO.251221xxx）