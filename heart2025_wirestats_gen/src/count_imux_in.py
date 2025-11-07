import os
import math
from collections import defaultdict


#  設定項目 (ここでファイル名や閾値を調整します) 
# ===================================================================
# 読み込むファイル (SA_out.pyが出力した7要素のファイル)
INPUT_FILE = "wire_stats.txt" 

# 出力するファイル名 (MUXの入力数が記録される)
OUTPUT_FILE = "imux_in.txt"

# 適用する閾値 (この使用回数「未満」の配線は間引かれます)
THRESHOLD = 10  # (例: 10を指定すると、10回以上の配線が採用される)

# SA_out.pyで設定したグリッドサイズと合わせる
GRID_X = 4
GRID_Y = 4
# ===================================================================

def main():
    # --- 引数(args)の代わりに、先頭で定義した変数を使う ---
    print(f"Loading '{INPUT_FILE}' to count MUX inputs (Threshold >= {THRESHOLD})...")
    
    # 1. 各MUXの入力本数をカウントする辞書を準備
    mux_input_counts = defaultdict(int)

    if not os.path.exists(INPUT_FILE):
        print(f"Error: '{INPUT_FILE}' not found.")
        return

    total_lines = 0
    kept_wires_count = 0
    culled_wires_count = 0

    # 2. wire_stats.txt を読み込み、閾値で振り分けながら集計
    try:
        with open(INPUT_FILE, 'r') as f:
            for line in f:
                total_lines += 1
                if line.startswith("#"): continue
                
                try:
                    parts = line.strip().split()
                    if len(parts) == 7: 
                        count = int(parts[6]) # 7番目の要素（使用回数）
                        
                        # ★★★ 閾値(THRESHOLD)で判定 ★★★
                        if count >= THRESHOLD:
                            # 採用 (Keep)
                            dst_x, dst_y, dst_pin = int(parts[3]), int(parts[4]), int(parts[5])
                            mux_key = (dst_x, dst_y, dst_pin)
                            mux_input_counts[mux_key] += 1
                            kept_wires_count += 1
                        else:
                            # 間引き (Cull)
                            culled_wires_count += 1
                            
                except (ValueError, IndexError):
                    print(f"Skipping malformed line: {line.strip()}")
                    continue

    except Exception as e:
        print(f"An error occurred: {e}")
        return

    print(f"Processed {total_lines} wire entries.")
    print(f"  Kept: {kept_wires_count} wires (>= {THRESHOLD} uses)")
    print(f"  Culled: {culled_wires_count} wires (< {THRESHOLD} uses)")

    # 3. 集計結果を imux_in.txt に書き出す
    print(f"Saving MUX input counts to '{OUTPUT_FILE}'...")
    with open(OUTPUT_FILE, 'w') as f:
        f.write(f"# MUX Input Counts (Threshold >= {THRESHOLD})\n")
        f.write("# Format: MUX_X MUX_Y MUX_PIN INPUT_COUNT\n")
        
        # 4x4グリッドの全MUX(64個)を網羅して書き出す（0本のものも含む）
        for y in range(GRID_Y):
            for x in range(GRID_X):
                for pin in range(4): # 4-input MUX
                    mux_key = (x, y, pin)
                    final_count = mux_input_counts.get(mux_key, 0) # 辞書になければ0
                    f.write(f"{x} {y} {pin} {final_count}\n")
                    
    print("Done.")

if __name__ == "__main__":
    main()