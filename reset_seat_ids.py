#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重新标记seat_ids脚本
将seats表中的seat_id按照当前次序进行赋值(1~267)
并同步更新users表中的引用
"""

import sqlite3
import sys

def reset_seat_ids(db_path='ticket.db'):
    """重新标记所有座位的ID"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询现有所有座位（按原seat_id排序）
        cursor.execute('SELECT seat_id, pos, occupied, student_id, row_num, col_num, group_id FROM seats ORDER BY seat_id')
        seats = cursor.fetchall()
        
        if not seats:
            print("❌ 数据库中没有座位数据")
            conn.close()
            return False
        
        print(f"📊 找到 {len(seats)} 个座位")
        print(f"开始重新标记座位ID (1-{len(seats)})...\n")
        
        # 创建临时表保存新的seat_id映射
        mapping = {}  # 旧ID -> 新ID
        
        # 首先创建新的座位数据
        new_seats = []
        for new_id, seat in enumerate(seats, start=1):
            old_id = seat[0]
            mapping[old_id] = new_id
            new_seats.append((new_id, seat[1], seat[2], seat[3], seat[4], seat[5], seat[6]))
        
        print("⚠️  警告：此操作将更改所有座位ID和相关引用")
        print(f"   将创建seat_id映射: {len(mapping)} 条记录")
        
        # 备份现有数据
        cursor.execute('ALTER TABLE seats RENAME TO seats_backup')
        print("✅ 已创建seats表备份 (seats_backup)")
        
        # 创建新的seats表
        cursor.execute('''
            CREATE TABLE seats (
                seat_id INTEGER PRIMARY KEY,
                pos TEXT NOT NULL,
                occupied BOOLEAN NOT NULL DEFAULT 0,
                student_id TEXT,
                group_id INTEGER DEFAULT 1,
                row_num INTEGER DEFAULT 0,
                col_num INTEGER DEFAULT 0
            )
        ''')
        
        # 插入新的座位数据（使用新的seat_id）
        for new_seat in new_seats:
            cursor.execute('''
                INSERT INTO seats (seat_id, pos, occupied, student_id, row_num, col_num, group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', new_seat)
        
        print(f"✅ 已创建新seats表并插入 {len(new_seats)} 条记录")
        
        # 更新users表中的seat_id引用
        print("🔄 更新users表中的seat_id引用...")
        for old_id, new_id in mapping.items():
            cursor.execute('UPDATE users SET seat_id = ? WHERE seat_id = ?', (new_id, old_id))
        
        affected = cursor.rowcount
        print(f"✅ 已更新users表 {affected} 条记录")
        
        conn.commit()
        print("\n✨ 座位ID重新标记完成！")
        print(f"📝 映射总数: {len(mapping)}")
        print(f"📝 新seat_id范围: 1-{len(seats)}")
        
        # 显示样本映射
        print("\n📊 映射样本 (前10条):")
        for i, (old_id, new_id) in enumerate(sorted(mapping.items())[:10]):
            print(f"   {old_id} → {new_id}")
        
        if len(mapping) > 10:
            print(f"   ... 还有 {len(mapping)-10} 条")
        
        print("\n✅ 操作完成。原表备份为: seats_backup")
        print("⚠️  如需恢复，可使用: ALTER TABLE seats_backup RENAME TO seats")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ 数据库错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 出错: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("        座位ID重新标记工具 (Reset Seat IDs)")
    print("=" * 60)
    print()
    
    db_path = 'ticket.db'
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    print(f"📂 数据库路径: {db_path}\n")
    
    # 确认操作
    confirm = input("⚠️  此操作将修改所有座位ID。是否继续? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ 已取消操作")
        sys.exit(1)
    
    print()
    success = reset_seat_ids(db_path)
    
    if success:
        print("\n✅ 操作成功！")
        sys.exit(0)
    else:
        print("\n❌ 操作失败！")
        sys.exit(1)
