from flask import Flask, request, jsonify, render_template, Response
import sqlite3, random, os
from contextlib import contextmanager

app = Flask(__name__)
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
        conn.commit()


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

# ------------ 首页（扫码跳转） ------------
@app.route("/")
def home():
    return render_template("index.html")

# ------------ 领取票 ------------
@app.route("/ticket", methods=["POST"])
def ticket():
    student_id = request.form.get("student_id", "").strip()

    # 特殊密钥：跳转到管理员页面（管理员页面受 Basic Auth 保护）
    if student_id == "xuanlan40":
        return jsonify({"status": "admin_redirect", "url": "/admin"})

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # --- 检查合法学号 ---
            cursor.execute('SELECT * FROM valid_ids WHERE student_id = ?', (student_id,))
            if not cursor.fetchone():
                return jsonify({"status": "fail", "msg": "学号不合法"}), 400
            
            # --- 已领取过 ---
            cursor.execute('SELECT seat_id FROM users WHERE student_id = ?', (student_id,))
            existing = cursor.fetchone()
            if existing:
                return jsonify({
                    "status": "ok",
                    "msg": "你已领取过",
                    "seat": existing['seat_id']
                })
            
            # --- 分配可用座位 ---
            cursor.execute('SELECT seat_id FROM seats WHERE occupied = 0 ORDER BY RANDOM() LIMIT 1')
            available = cursor.fetchone()
            if not available:
                return jsonify({"status": "fail", "msg": "票已领完"}), 400
            
            seat_id = available['seat_id']
            
            # --- 更新座位表和用户表 ---
            cursor.execute('UPDATE seats SET occupied = 1, student_id = ? WHERE seat_id = ?', 
                         (student_id, seat_id))
            cursor.execute('INSERT INTO users (student_id, seat_id) VALUES (?, ?)', 
                         (student_id, seat_id))
            conn.commit()
            
            return jsonify({
                "status": "ok",
                "msg": "领取成功",
                "seat": seat_id
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
            cursor.execute('SELECT * FROM seats')
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
            
            # 如果已占用，添加到 users 表
            if student:
                cursor.execute('DELETE FROM users WHERE student_id = ?', (student,))
                cursor.execute('INSERT INTO users (student_id, seat_id) VALUES (?, ?)', 
                             (student, seat_id))
            
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
            
            # 如果学生被更改，删除旧映射
            if old_student and old_student != new_student:
                cursor.execute('DELETE FROM users WHERE student_id = ?', (old_student,))
            
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
                cursor.execute('INSERT INTO users (student_id, seat_id) VALUES (?, ?)', 
                             (new_student, seat_id))
            
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
            
            # 删除关联的用户
            if seat['student_id']:
                cursor.execute('DELETE FROM users WHERE student_id = ?', (seat['student_id'],))
            
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
            cursor.execute('SELECT student_id, seat_id FROM users')
            users = {row['student_id']: row['seat_id'] for row in cursor.fetchall()}
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
            cursor.execute('INSERT INTO users (student_id, seat_id) VALUES (?, ?)', 
                         (student, seat_id))
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
            cursor.execute('SELECT student_id FROM valid_ids')
            ids = [row['student_id'] for row in cursor.fetchall()]
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


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
