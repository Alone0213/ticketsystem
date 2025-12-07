import pandas as pd

def extract_ids(excel_path, txt_path):
    # 读取Excel
    df = pd.read_excel(excel_path, sheet_name='Sheet1')

    # 检查是否存在"学号"列
    if '学号' not in df.columns:
        print(f"Excel文件中没有找到 '学号' 列: {excel_path}")
        return

    # 提取学号列并去掉空值
    ids = df['学号'].dropna().astype(str).tolist()

    # 写入txt（追加方式）
    with open(txt_path, 'a', encoding='utf-8') as f:
        f.write(','.join(ids) + ',')   # 最后加一个逗号也可以看情况去掉

    print(f"{len(ids)} 条学号已经写入到 {txt_path}")

# 示例调用
extract_ids("data_get\\25.xlsx", "data_get\stu_num.txt")
