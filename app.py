from flask import Flask, request, jsonify, render_template, Response
import json, random, os, tempfile

app = Flask(__name__)

# ------------ JSON 读写工具 ------------
def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    # 原子写入：先写入临时文件，再替换
    dirn = os.path.dirname(filename) or "."
    fd, tmp_path = tempfile.mkstemp(prefix="tmp-", dir=dirn, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filename)
    except Exception:
        # 清理临时文件
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


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

    valid_ids = load_json("valid_ids.json")
    users = load_json("users.json")
    seats = load_json("seats.json")

    # --- 检查合法学号 ---
    if student_id not in valid_ids:
        return jsonify({"status": "fail", "msg": "学号不合法"}), 400

    # --- 已领取过 ---
    if student_id in users:
        return jsonify({
            "status": "ok",
            "msg": "你已领取过",
            "seat": users[student_id]
        })

    # --- 分配可用座位 ---
    available = [s for s in seats if not s["occupied"]]
    if not available:
        return jsonify({"status": "fail", "msg": "票已领完"}), 400

    selected = random.choice(available)
    seat_id = selected["seat_id"]

    # --- 写入 seats.json ---
    for s in seats:
        if s["seat_id"] == seat_id:
            s["occupied"] = True
            s["student_id"] = student_id
            break

    # --- 写入 users.json ---
    users[student_id] = seat_id

    save_json("seats.json", seats)
    save_json("users.json", users)

    return jsonify({
        "status": "ok",
        "msg": "领取成功",
        "seat": seat_id
    })


# ------------ 管理页面  ------------
@app.route('/admin')
@auth_required
def admin_page():
    return render_template('admin.html')


# ------------ 管理 API：Seats / Users / Valid IDs / Stats ------------
@app.route('/admin/api/seats', methods=['GET'])
@auth_required
def api_get_seats():
    seats = load_json('seats.json')
    return jsonify(seats)


@app.route('/admin/api/seats', methods=['POST'])
@auth_required
def api_create_seat():
    data = request.get_json() or {}
    seat_id = data.get('seat_id')
    if seat_id is None:
        return jsonify({'status': 'fail', 'msg': '需要 seat_id'}), 400
    seats = load_json('seats.json')
    users = load_json('users.json')
    # 不允许重复 seat_id
    if any(str(s.get('seat_id')) == str(seat_id) for s in seats):
        return jsonify({'status': 'fail', 'msg': '座位已存在'}), 400
    occupied = bool(data.get('occupied', False))
    student = data.get('student_id') if occupied else None
    new = {'seat_id': seat_id, 'occupied': occupied, 'student_id': student}
    seats.append(new)
    # 如果设置为已占用，更新 users 映射（覆盖已有）
    if student:
        users[student] = seat_id
    save_json('seats.json', seats)
    save_json('users.json', users)
    return jsonify({'status': 'ok', 'seat': new})


@app.route('/admin/api/seats/<seat_id>', methods=['PUT'])
@auth_required
def api_update_seat(seat_id):
    data = request.get_json() or {}
    seats = load_json('seats.json')
    users = load_json('users.json')
    target = None
    for s in seats:
        if str(s.get('seat_id')) == str(seat_id):
            target = s
            break
    if not target:
        return jsonify({'status': 'fail', 'msg': '座位不存在'}), 404

    # 处理 occupied/student_id 变更
    new_occ = data.get('occupied') if 'occupied' in data else target.get('occupied')
    new_student = data.get('student_id') if 'student_id' in data else target.get('student_id')

    # 如果原来有学生并且被替换，移除旧映射
    old_student = target.get('student_id')
    if old_student and old_student != new_student and old_student in users:
        del users[old_student]

    target['occupied'] = bool(new_occ)
    target['student_id'] = new_student if new_student else None

    # 如果现在有新学生，写入 users（覆盖旧位置）
    if new_student:
        # 释放新学生原来的座位（如果有）
        if new_student in users and str(users[new_student]) != str(seat_id):
            old_seat = users[new_student]
            for s in seats:
                if str(s.get('seat_id')) == str(old_seat):
                    s['occupied'] = False
                    s['student_id'] = None
                    break
        users[new_student] = seat_id

    save_json('seats.json', seats)
    save_json('users.json', users)
    return jsonify({'status': 'ok', 'seat': target})


@app.route('/admin/api/seats/<seat_id>', methods=['DELETE'])
@auth_required
def api_delete_seat(seat_id):
    seats = load_json('seats.json')
    users = load_json('users.json')

    # 找到并移除座位
    found = None
    for s in seats:
        if str(s.get('seat_id')) == str(seat_id):
            found = s
            break
    if not found:
        return jsonify({'status': 'fail', 'msg': '座位不存在'}), 404

    # 如果座位上有关联的学生，删除 users.json 中对应记录
    student = found.get('student_id')
    if student and student in users:
        del users[student]

    seats = [s for s in seats if str(s.get('seat_id')) != str(seat_id)]

    save_json('seats.json', seats)
    save_json('users.json', users)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/users', methods=['GET'])
@auth_required
def api_get_users():
    users = load_json('users.json')
    return jsonify(users)


@app.route('/admin/api/users', methods=['POST'])
@auth_required
def api_create_user():
    data = request.get_json() or {}
    student = data.get('student_id')
    seat_id = data.get('seat_id')
    if not student or seat_id is None:
        return jsonify({'status': 'fail', 'msg': '需要 student_id 和 seat_id'}), 400
    users = load_json('users.json')
    seats = load_json('seats.json')

    # 检查座位存在
    target = None
    for s in seats:
        if str(s.get('seat_id')) == str(seat_id):
            target = s
            break
    if not target:
        return jsonify({'status': 'fail', 'msg': '座位不存在'}), 404

    # 如果座位已被占用且不是当前学生，拒绝
    if target.get('occupied') and str(target.get('student_id')) != str(student):
        return jsonify({'status': 'fail', 'msg': '座位已被占用'}), 400

    # 如果学生已经有座位，先释放旧座位
    if student in users:
        old = users[student]
        for s in seats:
            if str(s.get('seat_id')) == str(old):
                s['occupied'] = False
                s['student_id'] = None
                break

    # 分配
    target['occupied'] = True
    target['student_id'] = student
    users[student] = seat_id

    save_json('seats.json', seats)
    save_json('users.json', users)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/users/<student_id>', methods=['PUT'])
@auth_required
def api_update_user(student_id):
    data = request.get_json() or {}
    new_seat = data.get('seat_id')
    users = load_json('users.json')
    seats = load_json('seats.json')

    if student_id not in users:
        return jsonify({'status': 'fail', 'msg': '用户不存在'}), 404

    old_seat = users[student_id]
    # 释放旧座位
    for s in seats:
        if str(s.get('seat_id')) == str(old_seat):
            s['occupied'] = False
            s['student_id'] = None
            break

    # 指定新座位
    target = None
    for s in seats:
        if str(s.get('seat_id')) == str(new_seat):
            target = s
            break
    if not target:
        return jsonify({'status': 'fail', 'msg': '新座位不存在'}), 404
    if target.get('occupied'):
        return jsonify({'status': 'fail', 'msg': '新座位已被占用'}), 400

    target['occupied'] = True
    target['student_id'] = student_id
    users[student_id] = new_seat

    save_json('seats.json', seats)
    save_json('users.json', users)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/users/<student_id>', methods=['DELETE'])
@auth_required
def api_delete_user(student_id):
    users = load_json('users.json')
    seats = load_json('seats.json')

    if student_id not in users:
        return jsonify({'status': 'fail', 'msg': '用户不存在'}), 404

    seat_id = users[student_id]
    del users[student_id]

    # 释放对应座位
    for s in seats:
        if str(s.get('seat_id')) == str(seat_id):
            s['occupied'] = False
            s['student_id'] = None
            break

    save_json('users.json', users)
    save_json('seats.json', seats)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/validids', methods=['GET'])
@auth_required
def api_get_validids():
    valid_ids = load_json('valid_ids.json')
    return jsonify(valid_ids)


@app.route('/admin/api/validids', methods=['POST'])
@auth_required
def api_add_validid():
    data = request.get_json() or {}
    sid = data.get('student_id')
    if not sid:
        return jsonify({'status': 'fail', 'msg': '需要 student_id'}), 400
    valid_ids = load_json('valid_ids.json')
    if sid in valid_ids:
        return jsonify({'status': 'fail', 'msg': '已存在'}), 400
    valid_ids.append(sid)
    save_json('valid_ids.json', valid_ids)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/validids/<sid>', methods=['DELETE'])
@auth_required
def api_delete_validid(sid):
    valid_ids = load_json('valid_ids.json')
    if sid not in valid_ids:
        return jsonify({'status': 'fail', 'msg': '学号不存在'}), 404
    valid_ids = [v for v in valid_ids if v != sid]
    save_json('valid_ids.json', valid_ids)
    return jsonify({'status': 'ok'})

# ------------ 查票接口（管理员用） ------------
@app.route("/lookup")
def lookup():
    student_id = request.args.get("sid", "").strip()
    users = load_json("users.json")

    if student_id in users:
        return jsonify({"seat": users[student_id]})
    return jsonify({"seat": None, "msg": "未领取"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
