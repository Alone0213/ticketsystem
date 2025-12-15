from flask import Flask, request, jsonify, render_template, Response, send_from_directory
import sqlite3, random, os
from contextlib import contextmanager

app = Flask(__name__, static_folder='pics', static_url_path='/static/pics')
app.config['DATABASE'] = 'ticket.db'


# ------------ SQLite 数据库连接 ------------
@contextmanager
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """初始化数据库表结构（如果不存在）"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seats (
                seat_id INTEGER PRIMARY KEY,
                pos TEXT NOT NULL,
                occupied BOOLEAN NOT NULL DEFAULT 0,
                student_id TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                student_id TEXT PRIMARY KEY,
                seat_id INTEGER NOT NULL,
                FOREIGN KEY (seat_id) REFERENCES seats(seat_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS valid_ids (
                student_id TEXT PRIMARY KEY
            )
        ''')
        # 新增 IP 地址领票记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ip_ticket_log (
                ip_address TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 新增取票窗口状态表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticket_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_open BOOLEAN DEFAULT 0
            )
        ''')
        # 如果 ticket_status 表为空，插入默认状态（关闭）
        cursor.execute('SELECT COUNT(*) as cnt FROM ticket_status')
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute('INSERT INTO ticket_status (id, is_open) VALUES (1, 0)')
        
        # 新增座位集合状态表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seat_groups (
                id INTEGER PRIMARY KEY CHECK (id IN (1, 2)),
                group_id INTEGER,
                is_open BOOLEAN DEFAULT 0
            )
        ''')
        # 如果 seat_groups 表为空，插入默认状态（两个集合都关闭）
        cursor.execute('SELECT COUNT(*) as cnt FROM seat_groups')
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute('INSERT INTO seat_groups (id, group_id, is_open) VALUES (1, 1, 0)')
            cursor.execute('INSERT INTO seat_groups (id, group_id, is_open) VALUES (2, 2, 0)')
        
        # 为 seats 表添加 group_id 列（如果不存在）
        cursor.execute("PRAGMA table_info(seats)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'group_id' not in cols:
            cursor.execute('ALTER TABLE seats ADD COLUMN group_id INTEGER DEFAULT 1')
        
        # 为 seats 表添加 row_num 列（如果不存在）
        cursor.execute("PRAGMA table_info(seats)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'row_num' not in cols:
            cursor.execute('ALTER TABLE seats ADD COLUMN row_num INTEGER DEFAULT 0')
        
        # 为 seats 表添加 col_num 列（如果不存在）
        cursor.execute("PRAGMA table_info(seats)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'col_num' not in cols:
            cursor.execute('ALTER TABLE seats ADD COLUMN col_num INTEGER DEFAULT 0')
        
        # 新增本地密钥开关表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS local_key_switch (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_open BOOLEAN DEFAULT 0
            )
        ''')
        # 如果 local_key_switch 表为空，插入默认状态（关闭）
        cursor.execute('SELECT COUNT(*) as cnt FROM local_key_switch')
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute('INSERT INTO local_key_switch (id, is_open) VALUES (1, 0)')
        
        # 新增说明信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS info_section (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                content TEXT DEFAULT ''
            )
        ''')
        # 如果 info_section 表为空，插入默认内容
        cursor.execute('SELECT COUNT(*) as cnt FROM info_section')
        if cursor.fetchone()['cnt'] == 0:
            default_content = '''欢迎参加"智启新元，AI创未来"迎新晚会！请按照以下说明进行领票：
1.领票通道开放时间：XX日XX时。线上共开放135个座位，领完即止。
2.每个设备限领一张票，同学们凭票入场。
3.没有抢到票的同学不用气馁，剩下的票可通过服务点扫码线下领票，依旧先到先得。
线下领票时间地点：'''
            cursor.execute('INSERT INTO info_section (id, content) VALUES (1, ?)', (default_content,))
        
        conn.commit()


# ---------- 响应头优化：添加浏览器缓存 ----------
@app.after_request
def add_cache_headers(response):
    """为不同类型资源添加缓存头"""
    path = request.path
    
    # 为 /static/pics 下的图片设置缓存（30天）
    if path.startswith('/static/pics/'):
        response.headers['Cache-Control'] = 'public, max-age=2592000'
        response.headers['Pragma'] = 'public'
    
    return response

# ---------- 简单 HTTP Basic Auth 装饰器 ----------
def check_auth():
    auth = request.authorization
    if not auth:
        return False
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_pass = os.environ.get("ADMIN_PASS", "password")
    return auth.username == admin_user and auth.password == admin_pass

def require_auth():
    return Response('需要认证', 401, {"WWW-Authenticate": 'Basic realm="Login"'})

def auth_required(f):
    def wrapper(*args, **kwargs):
        if not check_auth():
            return require_auth()
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ---------- 获取真实客户端 IP（支持 nginx 反代） ----------
def get_client_ip():
    """
    获取真实客户端IP，支持nginx反代
    
    优先级：
    1. X-Forwarded-For header（nginx反代常用）
    2. X-Real-IP header（一些反代使用）
    3. CF-Connecting-IP header（Cloudflare使用）
    4. request.remote_addr（直连）
    """
    # 检查 X-Forwarded-For（可能包含多个IP，取第一个是原始客户端）
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    # 检查 X-Real-IP
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    # 检查 CF-Connecting-IP（Cloudflare）
    cf_ip = request.headers.get('CF-Connecting-IP')
    if cf_ip:
        return cf_ip.strip()
    
    # 默认使用 remote_addr
    return request.remote_addr

# ------------ 首页（扫码跳转） ------------
@app.route("/")
def home():
    return render_template("index.html")

# ------------ 票据页面 ------------
@app.route("/ticket")
def ticket_page():
    return render_template("ticket.html")

# ------------ 领取票 ------------
@app.route("/ticket", methods=["POST"])
def ticket():
    student_id = request.form.get("student_id", "").strip()
    student_name = request.form.get("student_name", "").strip()
    local_key = request.form.get("local_key", "").strip()
    client_ip = get_client_ip()  # 获取真实客户端 IP 地址（支持nginx反代）

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # 获取当前取票窗口状态
            cursor.execute('SELECT is_open FROM ticket_status WHERE id = 1')
            status_row = cursor.fetchone()
            is_open = bool(status_row['is_open']) if status_row else False
            
            # 获取本地密钥开关状态
            cursor.execute('SELECT is_open FROM local_key_switch WHERE id = 1')
            key_switch_row = cursor.fetchone()
            key_switch_open = bool(key_switch_row['is_open']) if key_switch_row else False
            
            # 特殊密钥：当学号为 xuanlan40 且姓名为空时，跳转到管理员页面（无论取票窗口状态）
            if student_id == "xuanlan40" and not student_name:
                return jsonify({"status": "admin_redirect", "url": "/admin"})
            
            # 如果取票窗口开放（is_open == 1）
            if is_open:
                # 开放状态：要求同时提供姓名和学号以进行验证
                if not student_id or not student_name:
                    return jsonify({"status": "fail", "msg": "需要提供姓名和学号"}), 400

                # --- 检查本地密钥开关（如果打开，需要验证密钥） ---
                if key_switch_open:
                    local_pass = os.environ.get("LOCAL_PASS", "123456")
                    if not local_key:
                        # 没有输入密钥
                        return jsonify({"status": "fail", "msg": "请前往线下扫码获取密钥"}), 400
                    elif local_key != local_pass:
                        # 密钥输入错误
                        return jsonify({"status": "fail", "msg": "请输入正确的密钥"}), 400
                
                # --- 检查学号是否存在并且姓名匹配（不区分大小写） ---
                cursor.execute('SELECT student_name FROM valid_ids WHERE student_id = ?', (student_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({"status": "fail", "msg": "学号不合法"}), 400
                db_name = row['student_name'] or ''
                if db_name.strip().lower() != student_name.strip().lower():
                    return jsonify({"status": "fail", "msg": "姓名与学号不匹配"}), 400
                
                # --- 检查座位集合是否有可用的开放集合 ---
                cursor.execute('SELECT group_id FROM seat_groups WHERE is_open = 1')
                open_groups = [row['group_id'] for row in cursor.fetchall()]
                if not open_groups:
                    return jsonify({"status": "fail", "msg": "未到取票时间，请耐心等待"}), 400
            else:
                # 关闭状态：只接受管理员密钥或提示等待
                if student_id or student_name:
                    # 有任何输入都不允许（除非是管理员密钥，已在上面检查过）
                    return jsonify({"status": "fail", "msg": "未到取票时间，请耐心等待"}), 400
                else:
                    # 没有任何输入
                    return jsonify({"status": "fail", "msg": "需要提供学号"}), 400
            
            # --- 检查 IP 地址领票限制 ---
            cursor.execute('SELECT student_id FROM ip_ticket_log WHERE ip_address = ?', (client_ip,))
            ip_ticket = cursor.fetchone()
            
            # 如果该 IP 已领过票
            if ip_ticket:
                ip_student_id = ip_ticket['student_id']
                # 如果输入的学号与 IP 记录的学号不同，拒绝
                if ip_student_id != student_id:
                    return jsonify({"status": "fail", "msg": "你只能领取一张票"}), 400
                # 如果学号相同，继续执行（允许查询自己的座位）
            
            # --- 已领取过 ---
            cursor.execute('''
                SELECT seat_id FROM users WHERE student_id = ?
            ''', (student_id,))
            existing_user = cursor.fetchone()
            if existing_user:
                seat_id = existing_user['seat_id']
                # 直接从seats表查询所有必要信息
                cursor.execute('''
                    SELECT pos, row_num, col_num FROM seats WHERE seat_id = ?
                ''', (seat_id,))
                seat = cursor.fetchone()
                # 计算该座位的票号（已占座位数中的序号）
                cursor.execute('SELECT COUNT(*) as cnt FROM seats WHERE occupied = 1 AND seat_id <= ?', (seat_id,))
                ticket_seq = cursor.fetchone()['cnt']
                ticket_no = f"NO.251221{ticket_seq:03d}"
                return jsonify({
                    "status": "ok",
                    "msg": "你已领取过",
                    "seat": seat_id,
                    "pos": seat['pos'],
                    "row_num": seat['row_num'],
                    "col_num": seat['col_num'],
                    "ticket_no": ticket_no
                })
            
            # --- 分配可用座位（仅限开放集合范围内） ---
            if is_open:
                # 在开放的集合范围内随机分配
                cursor.execute('SELECT group_id FROM seat_groups WHERE is_open = 1')
                open_groups = [row['group_id'] for row in cursor.fetchall()]
                if open_groups:
                    placeholders = ','.join('?' * len(open_groups))
                    cursor.execute(f'SELECT seat_id, pos, row_num, col_num FROM seats WHERE occupied = 0 AND group_id IN ({placeholders}) ORDER BY RANDOM() LIMIT 1', open_groups)
                else:
                    cursor.execute('SELECT seat_id, pos, row_num, col_num FROM seats WHERE occupied = 0 ORDER BY RANDOM() LIMIT 1')
            else:
                cursor.execute('SELECT seat_id, pos, row_num, col_num FROM seats WHERE occupied = 0 ORDER BY RANDOM() LIMIT 1')
            
            available = cursor.fetchone()
            if not available:
                return jsonify({"status": "fail", "msg": "票已领完"}), 400
            
            seat_id = available['seat_id']
            pos = available['pos']
            row_num = available['row_num']
            col_num = available['col_num']
            
            # --- 获取学生姓名 ---
            cursor.execute('SELECT student_name FROM valid_ids WHERE student_id = ?', (student_id,))
            name_row = cursor.fetchone()
            student_name_db = name_row['student_name'] if name_row else ''
            
            # --- 更新座位表和用户表 ---
            cursor.execute('UPDATE seats SET occupied = 1, student_id = ? WHERE seat_id = ?',
                         (student_id, seat_id))
            cursor.execute('INSERT INTO users (student_id, seat_id, student_name, pos) VALUES (?, ?, ?, ?)',
                         (student_id, seat_id, student_name_db, pos))
            
            # --- 记录 IP 地址领票日志 ---
            cursor.execute('INSERT INTO ip_ticket_log (ip_address, student_id) VALUES (?, ?)',
                         (client_ip, student_id))
            
            conn.commit()
            # 计算当前已占座位数，作为票号序列（001..267）
            cursor.execute('SELECT COUNT(*) as cnt FROM seats WHERE occupied = 1')
            occupied_cnt = cursor.fetchone()['cnt']
            ticket_no = f"NO.251221{occupied_cnt:03d}"
            return jsonify({
                "status": "ok",
                "msg": "领取成功",
                "seat": seat_id,
                "pos": pos,
                "row_num": row_num,
                "col_num": col_num,
                "ticket_no": ticket_no
            })
    except Exception as e:
        return jsonify({"status": "fail", "msg": str(e)}), 500

# ------------ 查票接口（管理员用） ------------
@app.route("/lookup")
def lookup():
    student_id = request.args.get("sid", "").strip()
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT seat_id FROM users WHERE student_id = ?', (student_id,))
            result = cursor.fetchone()
            if result:
                return jsonify({"seat": result['seat_id']})
            return jsonify({"seat": None, "msg": "未领取"})
    except Exception as e:
        return jsonify({"status": "fail", "msg": str(e)}), 500

# ------------ 管理页面  ------------
@app.route('/admin')
@auth_required
def admin_page():
    return render_template('admin.html')


# ------------ 管理 API：Seats / Users / Valid IDs / Stats ------------
@app.route('/admin/api/seats', methods=['GET'])
@auth_required
def api_get_seats():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.seat_id, s.pos, s.occupied, s.student_id, v.student_name
                FROM seats s
                LEFT JOIN valid_ids v ON s.student_id = v.student_id
            ''')
            seats = [dict(row) for row in cursor.fetchall()]
            return jsonify(seats)
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/seats', methods=['POST'])
@auth_required
def api_create_seat():
    try:
        data = request.get_json() or {}
        seat_id = data.get('seat_id')
        if seat_id is None:
            return jsonify({'status': 'fail', 'msg': '需要 seat_id'}), 400
        
        pos = data.get('pos', '')
        occupied = bool(data.get('occupied', False))
        student = data.get('student_id') if occupied else None
        
        with get_db() as conn:
            cursor = conn.cursor()
            # 检查重复
            cursor.execute('SELECT 1 FROM seats WHERE seat_id = ?', (seat_id,))
            if cursor.fetchone():
                return jsonify({'status': 'fail', 'msg': '座位已存在'}), 400
            
            cursor.execute('''
                INSERT INTO seats (seat_id, pos, occupied, student_id)
                VALUES (?, ?, ?, ?)
            ''', (seat_id, pos, occupied, student))
            
            # 如果已占用，添加到 users 表并清理该学号的旧 IP 记录
            if student:
                cursor.execute('DELETE FROM users WHERE student_id = ?', (student,))
                # 获取学生姓名和座位位置
                cursor.execute('SELECT student_name FROM valid_ids WHERE student_id = ?', (student,))
                name_row = cursor.fetchone()
                student_name_db = name_row['student_name'] if name_row else ''
                cursor.execute('INSERT INTO users (student_id, seat_id, student_name, pos) VALUES (?, ?, ?, ?)', 
                             (student, seat_id, student_name_db, pos))
                # 清理该学号的 IP 日志（重新分配座位时应清理旧 IP 绑定）
                cursor.execute('DELETE FROM ip_ticket_log WHERE student_id = ?', (student,))
            
            conn.commit()
            return jsonify({'status': 'ok', 'seat': {'seat_id': seat_id, 'pos': pos, 'occupied': occupied, 'student_id': student}})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/seats/<seat_id>', methods=['PUT'])
@auth_required
def api_update_seat(seat_id):
    try:
        data = request.get_json() or {}
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM seats WHERE seat_id = ?', (seat_id,))
            seat = cursor.fetchone()
            if not seat:
                return jsonify({'status': 'fail', 'msg': '座位不存在'}), 404
            
            new_occ = data.get('occupied') if 'occupied' in data else seat['occupied']
            new_student = data.get('student_id') if 'student_id' in data else seat['student_id']
            new_pos = data.get('pos') if 'pos' in data else seat['pos']
            
            old_student = seat['student_id']
            old_occ = seat['occupied']
            
            # 如果学生被更改，删除旧映射并清理旧学号的 IP 日志
            if old_student and old_student != new_student:
                cursor.execute('DELETE FROM users WHERE student_id = ?', (old_student,))
                cursor.execute('DELETE FROM ip_ticket_log WHERE student_id = ?', (old_student,))
            
            # 更新座位
            cursor.execute('''
                UPDATE seats SET occupied = ?, student_id = ?, pos = ?
                WHERE seat_id = ?
            ''', (int(new_occ), new_student, new_pos, seat_id))
            
            # 如果有新学生，更新用户映射
            if new_student:
                # 释放新学生的旧座位（如有）
                cursor.execute('SELECT seat_id FROM users WHERE student_id = ?', (new_student,))
                old_seat = cursor.fetchone()
                if old_seat and str(old_seat['seat_id']) != str(seat_id):
                    cursor.execute('UPDATE seats SET occupied = 0, student_id = NULL WHERE seat_id = ?', 
                                 (old_seat['seat_id'],))
                
                cursor.execute('DELETE FROM users WHERE student_id = ?', (new_student,))
                # 获取学生姓名和座位位置
                cursor.execute('SELECT student_name FROM valid_ids WHERE student_id = ?', (new_student,))
                name_row = cursor.fetchone()
                student_name_db = name_row['student_name'] if name_row else ''
                cursor.execute('INSERT INTO users (student_id, seat_id, student_name, pos) VALUES (?, ?, ?, ?)', 
                             (new_student, seat_id, student_name_db, new_pos))
                # 清理新学号的 IP 日志（重新分配座位时应清理旧 IP 绑定）
                cursor.execute('DELETE FROM ip_ticket_log WHERE student_id = ?', (new_student,))
            elif not new_occ:
                # 座位从占用变为未占用，清理相关 IP 日志
                if old_student:
                    cursor.execute('DELETE FROM ip_ticket_log WHERE student_id = ?', (old_student,))
            
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/seats/<seat_id>', methods=['DELETE'])
@auth_required
def api_delete_seat(seat_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT student_id FROM seats WHERE seat_id = ?', (seat_id,))
            seat = cursor.fetchone()
            if not seat:
                return jsonify({'status': 'fail', 'msg': '座位不存在'}), 404
            
            student = seat['student_id']
            # 删除关联的用户
            if student:
                cursor.execute('DELETE FROM users WHERE student_id = ?', (student,))
                # 清理该学号的 IP 日志
                cursor.execute('DELETE FROM ip_ticket_log WHERE student_id = ?', (student,))
            
            cursor.execute('DELETE FROM seats WHERE seat_id = ?', (seat_id,))
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/users', methods=['GET'])
@auth_required
def api_get_users():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.student_id, u.seat_id, u.student_name, u.pos
                FROM users u
            ''')
            users = [dict(row) for row in cursor.fetchall()]
            return jsonify(users)
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/users', methods=['POST'])
@auth_required
def api_create_user():
    try:
        data = request.get_json() or {}
        student = data.get('student_id')
        seat_id = data.get('seat_id')
        if not student or seat_id is None:
            return jsonify({'status': 'fail', 'msg': '需要 student_id 和 seat_id'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # 检查座位存在
            cursor.execute('SELECT * FROM seats WHERE seat_id = ?', (seat_id,))
            seat = cursor.fetchone()
            if not seat:
                return jsonify({'status': 'fail', 'msg': '座位不存在'}), 404
            
            # 座位是否已被他人占用
            if seat['occupied'] and str(seat['student_id']) != str(student):
                return jsonify({'status': 'fail', 'msg': '座位已被占用'}), 400
            
            # 如果学生已有座位，先释放旧座位
            cursor.execute('SELECT seat_id FROM users WHERE student_id = ?', (student,))
            old = cursor.fetchone()
            if old:
                cursor.execute('UPDATE seats SET occupied = 0, student_id = NULL WHERE seat_id = ?', 
                             (old['seat_id'],))
            
            # 分配
            cursor.execute('UPDATE seats SET occupied = 1, student_id = ? WHERE seat_id = ?', 
                         (student, seat_id))
            cursor.execute('DELETE FROM users WHERE student_id = ?', (student,))
            # 获取学生姓名和座位位置
            cursor.execute('SELECT student_name FROM valid_ids WHERE student_id = ?', (student,))
            name_row = cursor.fetchone()
            student_name_db = name_row['student_name'] if name_row else ''
            cursor.execute('SELECT pos FROM seats WHERE seat_id = ?', (seat_id,))
            pos_row = cursor.fetchone()
            pos = pos_row['pos'] if pos_row else ''
            cursor.execute('INSERT INTO users (student_id, seat_id, student_name, pos) VALUES (?, ?, ?, ?)', 
                         (student, seat_id, student_name_db, pos))
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/users/<student_id>', methods=['PUT'])
@auth_required
def api_update_user(student_id):
    try:
        data = request.get_json() or {}
        new_seat = data.get('seat_id')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT seat_id FROM users WHERE student_id = ?', (student_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'status': 'fail', 'msg': '用户不存在'}), 404
            
            old_seat = user['seat_id']
            
            # 释放旧座位
            cursor.execute('UPDATE seats SET occupied = 0, student_id = NULL WHERE seat_id = ?', 
                         (old_seat,))
            
            # 检查新座位
            cursor.execute('SELECT * FROM seats WHERE seat_id = ?', (new_seat,))
            new = cursor.fetchone()
            if not new:
                return jsonify({'status': 'fail', 'msg': '新座位不存在'}), 404
            if new['occupied']:
                return jsonify({'status': 'fail', 'msg': '新座位已被占用'}), 400
            
            # 分配到新座位
            cursor.execute('UPDATE seats SET occupied = 1, student_id = ? WHERE seat_id = ?', 
                         (student_id, new_seat))
            cursor.execute('UPDATE users SET seat_id = ? WHERE student_id = ?', 
                         (new_seat, student_id))
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/users/<student_id>', methods=['DELETE'])
@auth_required
def api_delete_user(student_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT seat_id FROM users WHERE student_id = ?', (student_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'status': 'fail', 'msg': '用户不存在'}), 404
            
            seat_id = user['seat_id']
            
            # 释放座位
            cursor.execute('UPDATE seats SET occupied = 0, student_id = NULL WHERE seat_id = ?', 
                         (seat_id,))
            cursor.execute('DELETE FROM users WHERE student_id = ?', (student_id,))
            # 清理 IP 日志（该学号的 IP 绑定记录）
            cursor.execute('DELETE FROM ip_ticket_log WHERE student_id = ?', (student_id,))
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/validids', methods=['GET'])
@auth_required
def api_get_validids():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT student_id, student_name FROM valid_ids')
            ids = [dict(row) for row in cursor.fetchall()]
            return jsonify(ids)
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/validids', methods=['POST'])
@auth_required
def api_add_validid():
    try:
        data = request.get_json() or {}
        sid = data.get('student_id')
        if not sid:
            return jsonify({'status': 'fail', 'msg': '需要 student_id'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM valid_ids WHERE student_id = ?', (sid,))
            if cursor.fetchone():
                return jsonify({'status': 'fail', 'msg': '已存在'}), 400
            
            cursor.execute('INSERT INTO valid_ids (student_id) VALUES (?)', (sid,))
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/validids/<sid>', methods=['DELETE'])
@auth_required
def api_delete_validid(sid):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM valid_ids WHERE student_id = ?', (sid,))
            if not cursor.fetchone():
                return jsonify({'status': 'fail', 'msg': '学号不存在'}), 404
            
            cursor.execute('DELETE FROM valid_ids WHERE student_id = ?', (sid,))
            conn.commit()
            return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/seat-groups', methods=['GET'])
def api_get_seat_groups():
    """获取两个座位集合的状态和剩余量（公开接口，学生端需要）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            groups_info = []
            for group_id in [1, 2]:
                cursor.execute('SELECT is_open FROM seat_groups WHERE group_id = ?', (group_id,))
                group_row = cursor.fetchone()
                is_open = bool(group_row['is_open']) if group_row else False
                
                cursor.execute('SELECT COUNT(*) as total FROM seats WHERE group_id = ?', (group_id,))
                total = cursor.fetchone()['total']
                
                cursor.execute('SELECT COUNT(*) as available FROM seats WHERE group_id = ? AND occupied = 0', (group_id,))
                available = cursor.fetchone()['available']
                
                groups_info.append({
                    'group_id': group_id,
                    'is_open': int(is_open),
                    'total': total,
                    'available': available,
                    'occupied': total - available
                })
            return jsonify(groups_info)
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/seat-groups/<int:group_id>', methods=['POST'])
@auth_required
def api_set_seat_group(group_id):
    """开放或关闭指定座位集合"""
    try:
        if group_id not in [1, 2]:
            return jsonify({'status': 'fail', 'msg': '集合 ID 必须为 1 或 2'}), 400
        
        data = request.get_json() or {}
        is_open = data.get('is_open', 0)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE seat_groups SET is_open = ? WHERE group_id = ?', (int(is_open), group_id))
            conn.commit()
        return jsonify({'status': 'ok', 'group_id': group_id, 'is_open': int(is_open)})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/clear-ip-log', methods=['POST'])
@auth_required
def api_clear_ip_log():
    """一键清除所有 IP 地址领票记录（仅管理员，用于测试）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM ip_ticket_log')
            deleted_count = cursor.rowcount
            conn.commit()
        return jsonify({'status': 'ok', 'msg': f'已清除 {deleted_count} 条 IP 记录'})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/api/available-seats', methods=['GET'])
def api_available_seats():
    """获取剩余座位数（公开接口，不需要认证）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as cnt FROM seats WHERE occupied = 0')
            available = cursor.fetchone()['cnt']
            cursor.execute('SELECT COUNT(*) as cnt FROM seats')
            total = cursor.fetchone()['cnt']
            return jsonify({'available': available, 'total': total})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/ticket-status', methods=['GET'])
def api_get_ticket_status():
    """获取取票窗口状态（不需要认证，前端需要显示）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_open FROM ticket_status WHERE id = 1')
            row = cursor.fetchone()
            is_open = int(row['is_open']) if row else 0
            return jsonify({'is_open': is_open})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/ticket-status', methods=['POST'])
@auth_required
def api_set_ticket_status():
    """更新取票窗口状态（需要 Basic Auth）"""
    try:
        data = request.get_json() or {}
        is_open = data.get('is_open', 0)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE ticket_status SET is_open = ? WHERE id = 1', (int(is_open),))
            conn.commit()
        return jsonify({'status': 'ok', 'is_open': int(is_open)})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/local-key-switch', methods=['GET'])
def api_get_local_key_switch():
    """获取本地密钥开关状态（不需要认证，前端需要显示）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_open FROM local_key_switch WHERE id = 1')
            row = cursor.fetchone()
            is_open = int(row['is_open']) if row else 0
            return jsonify({'is_open': is_open})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/local-key-switch', methods=['POST'])
@auth_required
def api_set_local_key_switch():
    """更新本地密钥开关状态（需要 Basic Auth）"""
    try:
        data = request.get_json() or {}
        is_open = data.get('is_open', 0)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE local_key_switch SET is_open = ? WHERE id = 1', (int(is_open),))
            conn.commit()
        return jsonify({'status': 'ok', 'is_open': int(is_open)})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/stats', methods=['GET'])
@auth_required
def api_stats():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as cnt FROM seats')
            total = cursor.fetchone()['cnt']
            
            cursor.execute('SELECT COUNT(*) as cnt FROM seats WHERE occupied = 1')
            allocated = cursor.fetchone()['cnt']
            
            cursor.execute('SELECT COUNT(*) as cnt FROM users')
            user_count = cursor.fetchone()['cnt']
            
            return jsonify({
                'total_seats': total,
                'allocated': allocated,
                'free': total - allocated,
                'user_count': user_count
            })
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/api/info-section', methods=['GET'])
def api_get_info_section():
    """获取说明信息（公开接口，不需要认证）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT content FROM info_section WHERE id = 1')
            row = cursor.fetchone()
            content = row['content'] if row else ''
            return jsonify({'content': content})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/info-section', methods=['GET'])
@auth_required
def api_get_info_section_admin():
    """获取说明信息（管理员接口，需要认证）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT content FROM info_section WHERE id = 1')
            row = cursor.fetchone()
            content = row['content'] if row else ''
            return jsonify({'content': content})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


@app.route('/admin/api/info-section', methods=['POST'])
@auth_required
def api_set_info_section():
    """更新说明信息（需要 Basic Auth）"""
    try:
        data = request.get_json() or {}
        content = data.get('content', '')
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE info_section SET content = ? WHERE id = 1', (content,))
            conn.commit()
        return jsonify({'status': 'ok', 'content': content})
    except Exception as e:
        return jsonify({'status': 'fail', 'msg': str(e)}), 500


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
