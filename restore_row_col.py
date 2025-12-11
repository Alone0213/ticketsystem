#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从seats_backup表恢复row_num和col_num到seats表
"""

import sqlite3

def restore_row_col(db_path='ticket.db'):
    """从备份表恢复row_num和col_num值"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 先检查备份表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='seats_backup'")
        if not cursor.fetchone():
            print("❌ 错误：seats_backup备份表不存在！")
            conn.close()
            return False
        
        print("📊 开始从seats_backup恢复row_num和col_num...")
        
        # 从备份表查询row_num和col_num值
        cursor.execute('SELECT row_num, col_num FROM seats_backup ORDER BY ROWID')
        backup_data = cursor.fetchall()
        
        print(f"✅ 从seats_backup读取 {len(backup_data)} 条记录")
        
        # 更新seats表中的row_num和col_num（按ROWID一一对应）
        for idx, (row_num, col_num) in enumerate(backup_data, start=1):
            cursor.execute('UPDATE seats SET row_num = ?, col_num = ? WHERE ROWID = ?', 
                         (row_num, col_num, idx))
        
        affected = cursor.rowcount
        conn.commit()
        print(f"✅ 已更新 {affected} 条记录的row_num和col_num值")
        
        # 验证
        cursor.execute('SELECT COUNT(*) FROM seats WHERE row_num = 0 OR col_num = 0')
        zero_count = cursor.fetchone()[0]
        if zero_count > 0:
            print(f"⚠️  警告：仍有 {zero_count} 条记录的row_num或col_num为0")
        else:
            print("✨ row_num和col_num恢复完成！所有记录都有有效的值")
        
        # 显示样本数据
        print("\n📊 恢复结果样本（前10条）:")
        cursor.execute('SELECT seat_id, row_num, col_num FROM seats LIMIT 10')
        for row in cursor.fetchall():
            print(f"   seat_id={row[0]:3d}, row_num={row[1]:3d}, col_num={row[2]:3d}")
        
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
    print("   从备份表恢复row_num和col_num (Restore Row/Col Nums)")
    print("=" * 60)
    print()
    
    success = restore_row_col('ticket.db')
    
    if success:
        print("\n✅ 恢复成功！")
    else:
        print("\n❌ 恢复失败！")
