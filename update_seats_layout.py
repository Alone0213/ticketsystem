"""
更新座位布局脚本：
- 为 `seats` 表添加 `row_num` 与 `col_num` 列（如不存在）
- 从 `pos` 字段解析行/列并写回 `row_num`/`col_num`
- 删除第5排、第7-21列的座位（并清理相关 users 映射）
- 将 rows 6-14 且 cols 7-21 的座位设置为 group_id=1，其余设置为 group_id=2

运行：
    python update_seats_layout.py

注意：此脚本会直接修改数据库，请先备份 `ticket.db`（例如复制一份）。
"""
import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'ticket.db')

POS_RE = re.compile(r"第\s*(\d+)\s*[排行]\s*[，,\s]*第\s*(\d+)\s*[列]")

def ensure_columns(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(seats)")
    cols = [r[1] for r in cur.fetchall()]
    if 'row_num' not in cols:
        cur.execute('ALTER TABLE seats ADD COLUMN row_num INTEGER')
        print('添加列 row_num')
    if 'col_num' not in cols:
        cur.execute('ALTER TABLE seats ADD COLUMN col_num INTEGER')
        print('添加列 col_num')
    if 'group_id' not in cols:
        cur.execute('ALTER TABLE seats ADD COLUMN group_id INTEGER DEFAULT 2')
        print('添加列 group_id (默认2)')
    conn.commit()


def parse_pos_to_rowcol(pos):
    if not pos:
        return None, None
    m = POS_RE.search(pos)
    if m:
        try:
            r = int(m.group(1))
            c = int(m.group(2))
            return r, c
        except:
            return None, None
    # 兼容其他格式：寻找所有数字
    nums = re.findall(r"(\d+)", pos)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    return None, None


def main():
    if not os.path.exists(DB_PATH):
        print('未找到数据库:', DB_PATH)
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_columns(conn)
        cur = conn.cursor()
        # 解析未填写 row_num/col_num 的座位
        cur.execute('SELECT seat_id, pos, row_num, col_num FROM seats')
        rows = cur.fetchall()
        parsed = 0
        for r in rows:
            seat_id = r['seat_id']
            row_num = r['row_num']
            col_num = r['col_num']
            pos = r['pos']
            if (row_num is None) or (col_num is None):
                rn, cn = parse_pos_to_rowcol(pos)
                if rn is not None and cn is not None:
                    cur.execute('UPDATE seats SET row_num = ?, col_num = ? WHERE seat_id = ?', (rn, cn, seat_id))
                    parsed += 1
        print(f'解析并写入 row/col: {parsed} 条')
        conn.commit()

        # 删除第5排 7-21列的座位
        cur.execute('SELECT seat_id FROM seats WHERE row_num = 5 AND col_num >= 7 AND col_num <= 21')
        to_delete = [r['seat_id'] for r in cur.fetchall()]
        if to_delete:
            print(f'将删除第5排 7-21列共 {len(to_delete)} 个座位')
            # 删除对应的 users 映射
            cur.executemany('DELETE FROM users WHERE seat_id = ?', [(sid,) for sid in to_delete])
            cur.executemany('DELETE FROM seats WHERE seat_id = ?', [(sid,) for sid in to_delete])
            conn.commit()
        else:
            print('未发现需删除的座位 (第5排 7-21列)')

        # 根据规则设置 group_id：rows 6-14 cols 7-21 -> group 1, 其余为 group 2
        cur.execute('UPDATE seats SET group_id = 2')
        cur.execute('UPDATE seats SET group_id = 1 WHERE row_num >= 6 AND row_num <= 14 AND col_num >= 7 AND col_num <= 21')
        conn.commit()

        # 汇总
        cur.execute('SELECT COUNT(*) as cnt FROM seats')
        total = cur.fetchone()['cnt']
        cur.execute('SELECT COUNT(*) as cnt FROM seats WHERE group_id = 1')
        g1 = cur.fetchone()['cnt']
        cur.execute('SELECT COUNT(*) as cnt FROM seats WHERE group_id = 2')
        g2 = cur.fetchone()['cnt']
        print(f'总座位数: {total}，集合1: {g1}，集合2: {g2}')
        if total != 267:
            print('警告：当前总座位数 != 267，请确认座位数据来源或手动调整。')
        else:
            print('座位数量符合 267 的目标')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
