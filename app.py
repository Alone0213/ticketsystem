from flask import Flask, request, jsonify, render_template
import json, random

app = Flask(__name__)

# ------------ JSON 读写工具 ------------
def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ------------ 首页（扫码跳转） ------------
@app.route("/")
def home():
    return render_template("index.html")

# ------------ 领取票 ------------
@app.route("/ticket", methods=["POST"])
def ticket():
    student_id = request.form.get("student_id", "").strip()

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
