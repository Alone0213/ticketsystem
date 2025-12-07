#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 JSON 文件迁移数据到 SQLite 数据库
执行: python migrate_to_sqlite.py
"""

import sqlite3
import json
import os

# 数据库文件路径
DB_PATH = 'ticket.db'

def init_db():
    """创建数据库表结构"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 座位表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seats (
            seat_id INTEGER PRIMARY KEY,
            pos TEXT NOT NULL,
            occupied BOOLEAN NOT NULL DEFAULT 0,
            student_id TEXT
        )
    ''')
    
    # 用户映射表（学号 -> 座位号）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            student_id TEXT PRIMARY KEY,
            seat_id INTEGER NOT NULL,
            FOREIGN KEY (seat_id) REFERENCES seats(seat_id)
        )
    ''')
    
    # 有效学号表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS valid_ids (
            student_id TEXT PRIMARY KEY
        )
    ''')
    
    conn.commit()
    conn.close()
    print("成功: 数据库表结构初始化完成")


def migrate_seats():
    """从 seats.json 导入座位数据"""
    if not os.path.exists('seats.json'):
        print("错误: seats.json 不存在")
        return
    
    with open('seats.json', 'r', encoding='utf-8') as f:
        seats_data = json.load(f)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 清空旧数据（如有）
    cursor.execute('DELETE FROM seats')
    
    # 批量导入
    for seat in seats_data:
        cursor.execute('''
            INSERT INTO seats (seat_id, pos, occupied, student_id)
            VALUES (?, ?, ?, ?)
        ''', (
            seat.get('seat_id'),
            seat.get('pos', ''),
            int(seat.get('occupied', False)),
            seat.get('student_id')
        ))
    
    conn.commit()
    conn.close()
    print(f"成功: 导入 {len(seats_data)} 条座位记录")


def migrate_users():
    """从 users.json 导入用户映射数据"""
    if not os.path.exists('users.json'):
        print("错误: users.json 不存在")
        return
    
    with open('users.json', 'r', encoding='utf-8') as f:
        users_data = json.load(f)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 清空旧数据（如有）
    cursor.execute('DELETE FROM users')
    
    # 批量导入
    for student_id, seat_id in users_data.items():
        cursor.execute('''
            INSERT INTO users (student_id, seat_id)
            VALUES (?, ?)
        ''', (student_id, seat_id))
    
    conn.commit()
    conn.close()
    print(f"成功: 导入 {len(users_data)} 条用户记录")


def migrate_valid_ids():
    """从 valid_ids.json 导入有效学号数据"""
    if not os.path.exists('valid_ids.json'):
        print("错误: valid_ids.json 不存在")
        return
    
    with open('valid_ids.json', 'r', encoding='utf-8') as f:
        valid_ids_data = json.load(f)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 清空旧数据（如有）
    cursor.execute('DELETE FROM valid_ids')
    
    # 批量导入
    for sid in valid_ids_data:
        cursor.execute('''
            INSERT INTO valid_ids (student_id)
            VALUES (?)
        ''', (sid,))
    
    conn.commit()
    conn.close()
    print(f"成功: 导入 {len(valid_ids_data)} 条有效学号")


def verify_migration():
    """验证迁移结果"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM seats')
    seats_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users')
    users_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM valid_ids')
    valid_ids_count = cursor.fetchone()[0]
    
    conn.close()
    
    print("\n--- 迁移结果统计 ---")
    print(f"seats 表：{seats_count} 条记录")
    print(f"users 表：{users_count} 条记录")
    print(f"valid_ids 表：{valid_ids_count} 条记录")


def main():
    print("开始迁移 JSON 数据到 SQLite...\n")
    
    # 删除旧数据库文件（如有）
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("成功: 删除旧数据库文件")
    
    # 初始化数据库
    init_db()
    
    # 导入数据
    print("\n导入数据...")
    migrate_seats()
    migrate_users()
    migrate_valid_ids()
    
    # 验证
    print()
    verify_migration()
    
    print("\n成功: 迁移完成！数据库文件：ticket.db")


if __name__ == '__main__':
    main()

