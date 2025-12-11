#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复group_id列的值
从seats_backup表恢复原始的group_id值到seats表
"""

import sqlite3

def fix_group_id(db_path='ticket.db'):
    """从备份表恢复group_id值"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 先检查备份表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='seats_backup'")
        if not cursor.fetchone():
            print("❌ 错误：seats_backup备份表不存在！")
            conn.close()
            return False
        
        print("📊 开始修复group_id列...")
        
        # 从备份表查询原始的group_id值
        cursor.execute('SELECT group_id FROM seats_backup ORDER BY ROWID')
        backup_group_ids = [row[0] for row in cursor.fetchall()]
        
        print(f"✅ 从seats_backup读取 {len(backup_group_ids)} 条group_id记录")
        
        # 更新seats表中的group_id（按ROWID一一对应）
        count = 0
        for idx, group_id in enumerate(backup_group_ids, start=1):
            cursor.execute('UPDATE seats SET group_id = ? WHERE ROWID = ?', (group_id, idx))
            count += cursor.rowcount
        
        conn.commit()
        print(f"✅ 已更新 {count} 条记录的group_id值")
        
        # 验证
        cursor.execute('SELECT COUNT(*) FROM seats WHERE group_id IS NULL OR group_id = 0')
        null_count = cursor.fetchone()[0]
        if null_count > 0:
            print(f"⚠️  警告：仍有 {null_count} 条记录的group_id为空或为0")
        else:
            print("✨ group_id修复完成！所有记录都有有效的group_id值")
        
        # 显示修复前后的对比
        print("\n📊 修复结果校验：")
        cursor.execute('SELECT COUNT(*), SUM(CASE WHEN group_id = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN group_id = 2 THEN 1 ELSE 0 END) FROM seats')
        total, group1, group2 = cursor.fetchone()
        print(f"   总座位数: {total}")
        print(f"   group_id = 1: {group1}")
        print(f"   group_id = 2: {group2}")
        
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
    print("        group_id修复工具 (Fix Group IDs)")
    print("=" * 60)
    print()
    
    success = fix_group_id('ticket.db')
    
    if success:
        print("\n✅ 修复成功！")
    else:
        print("\n❌ 修复失败！")
