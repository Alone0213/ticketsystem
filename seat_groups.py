"""
座位集合划分脚本
将座位分为两个集合，用于分批放票控制

配置：
- GROUP1_SIZE: 第一集合座位数（默认141）
- GROUP2_SIZE: 第二集合座位数（默认141）

使用：python seat_groups.py
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'ticket.db')

# 集合配置（可自行修改）
GROUP1_SIZE = 141  # 第一集合座位数
GROUP2_SIZE = 141  # 第二集合座位数

def init_seat_groups():
    """初始化座位集合分配"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        
        # 创建座位集合表（如果不存在）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seat_groups (
                id INTEGER PRIMARY KEY CHECK (id IN (1, 2)),
                group_id INTEGER,
                is_open BOOLEAN DEFAULT 0
            )
        ''')
        
        # 清空现有记录
        cursor.execute('DELETE FROM seat_groups')
        
        # 插入默认状态（两个集合都关闭）
        cursor.execute('INSERT INTO seat_groups (id, group_id, is_open) VALUES (1, 1, 0)')
        cursor.execute('INSERT INTO seat_groups (id, group_id, is_open) VALUES (2, 2, 0)')
        
        # 更新座位表，添加 group_id 列（如果不存在）
        cursor.execute("PRAGMA table_info(seats)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'group_id' not in cols:
            cursor.execute('ALTER TABLE seats ADD COLUMN group_id INTEGER DEFAULT 1')
            print('已添加座位表 group_id 列')
        
        # 分配座位到集合
        # 第一集合：座位 1 到 GROUP1_SIZE
        cursor.execute('UPDATE seats SET group_id = 1 WHERE seat_id >= 1 AND seat_id <= ?', (GROUP1_SIZE,))
        updated1 = cursor.rowcount
        
        # 第二集合：座位 GROUP1_SIZE+1 到 GROUP1_SIZE+GROUP2_SIZE
        cursor.execute('UPDATE seats SET group_id = 2 WHERE seat_id > ? AND seat_id <= ?', 
                      (GROUP1_SIZE, GROUP1_SIZE + GROUP2_SIZE))
        updated2 = cursor.rowcount
        
        conn.commit()
        print(f'座位集合分配完成:')
        print(f'  集合1: 座位 1-{GROUP1_SIZE} ({updated1} 座)')
        print(f'  集合2: 座位 {GROUP1_SIZE+1}-{GROUP1_SIZE+GROUP2_SIZE} ({updated2} 座)')
    finally:
        conn.close()

if __name__ == '__main__':
    init_seat_groups()
