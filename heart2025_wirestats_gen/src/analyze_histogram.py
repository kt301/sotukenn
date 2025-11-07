import matplotlib.pyplot as plt
import pandas as pd
import os

# --- 設定 ---
INPUT_FILE = "wire_stats.txt" # SA_out.py が出力した「使用回数付き」のファイル
OUTPUT_IMAGE = "wire_usage_histogram.png"
# グラフのX軸（使用回数）の最大値
X_AXIS_LIMIT = 100 
# ---

def main():
    print(f"Loading '{INPUT_FILE}' to generate usage histogram...")
    
    if not os.path.exists(INPUT_FILE):
        print(f"Error: '{INPUT_FILE}' not found. Please run SA_out.py first.")
        return

    usage_counts = []
    try:
        with open(INPUT_FILE, 'r') as f:
            for line in f:
                if line.startswith("#"): continue
                try:
                    parts = line.strip().split()
                    if len(parts) == 7:
                        count = int(parts[6]) # 7番目の要素（使用回数）
                        usage_counts.append(count)
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    if not usage_counts:
        print("No valid wire data found.")
        return

    # --- データをPandasで集計 ---
    df = pd.DataFrame(usage_counts, columns=['UsageCount'])
    
    # --- 統計サマリーの表示 ---
    print("\n--- Wire Usage Statistics ---")
    print(df['UsageCount'].describe(percentiles=[.25, .5, .75, .9, .99]))
    
    # --- ヒストグラムの描画 ---
    plt.figure(figsize=(12, 7))
    # X軸を 0 から X_AXIS_LIMIT まで、1刻みのビン（棒）で区切る
    bins = range(0, X_AXIS_LIMIT + 2) 
    
    ax = df['UsageCount'].plot(kind='hist', bins=bins, rwidth=0.8, log_y=True)
    ax.set_title(f'Wire Usage Histogram (from {INPUT_FILE}) - Log Scale')
    ax.set_xlabel('Total Usage Count (回数)')
    ax.set_ylabel('Number of Wire Types (種類数) [Log Scale]')
    ax.set_xlim(0, X_AXIS_LIMIT) # X軸の表示範囲を設定
    
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(OUTPUT_IMAGE, dpi=150)
    
    print(f"\nHistogram image saved to '{OUTPUT_IMAGE}'")

if __name__ == "__main__":
    main()