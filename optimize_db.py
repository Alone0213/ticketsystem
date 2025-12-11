#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库优化脚本 - 添加索引以加快查询速度
"""

import sqlite3

def optimize_database(db_path='ticket.db'):
    """为数据库添加优化索引"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("📊 开始优化数据库...")
        print()
        
        # 获取现有索引
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = {row[0] for row in cursor.fetchall()}
        
        # 定义需要创建的索引
        indexes = [
            ("idx_seats_occupied", "CREATE INDEX IF NOT EXISTS idx_seats_occupied ON seats(occupied)"),
            ("idx_seats_group_id", "CREATE INDEX IF NOT EXISTS idx_seats_group_id ON seats(group_id)"),
            ("idx_seats_student_id", "CREATE INDEX IF NOT EXISTS idx_seats_student_id ON seats(student_id)"),
            ("idx_ip_ticket_log_ip", "CREATE INDEX IF NOT EXISTS idx_ip_ticket_log_ip ON ip_ticket_log(ip_address)"),
            ("idx_users_student_id", "CREATE INDEX IF NOT EXISTS idx_users_student_id ON users(student_id)"),
            ("idx_valid_ids_student_id", "CREATE INDEX IF NOT EXISTS idx_valid_ids_student_id ON valid_ids(student_id)"),
        ]
        
        count = 0
        for idx_name, sql in indexes:
            try:
                cursor.execute(sql)
                count += 1
                status = "✅ 新建" if idx_name not in existing_indexes else "✓ 已存在"
                print(f"{status} {idx_name}")
            except sqlite3.Error as e:
                print(f"⚠️  {idx_name}: {e}")
        
        conn.commit()
        
        print()
        print(f"✨ 共创建/验证 {count} 个索引")
        print()
        
        # 显示索引统计
        print("📈 数据库索引统计：")
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index'")
        for idx_name, tbl_name in cursor.fetchall():
            print(f"   {idx_name} (表: {tbl_name})")
        
        conn.close()
        print()
        print("✅ 数据库优化完成！")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ 数据库错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 出错: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("        数据库优化工具 (Database Optimization)")
    print("=" * 60)
    print()
    
    success = optimize_database('ticket.db')
    
    if success:
        print("\n✅ 优化成功！")
    else:
        print("\n❌ 优化失败！")
