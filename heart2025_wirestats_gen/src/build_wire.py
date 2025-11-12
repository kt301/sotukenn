import os
import math
from collections import defaultdict

# 設定項目################################################################
# 統計ファイルのパス(間引かれた配線を復活させる時に使用)
STATS_FILE = "wire_stats.txt"
# MUXごとの入力本数ファイルのパス
IMUX_COUNT_FILE = "imux_in.txt"
# 最終的なアーキテクチャのファイル名
OUTPUT_FILE = "wirestat_final.txt"
# 閾値（count_imux_in.py の THRESHOLD と必ず「同じ値」にしてください）
THRESHOLD = 10 
# 目標とするMUXの物理サイズ (2のべき乗)
TARGET_POWER_OF_2 = True 
# もし2のべき乗がこの値を超えたら、この値でキャップする
# (例: 60本入力があった場合、64本ではなく32本に制限する)
MUX_SIZE_CAP = 32
# グリッドサイズとPIの総数 (物理ピンの生成に使用)
GRID_X = 4
GRID_Y = 4
NUM_PIS = 36 
###################################################################################

def load_wire_stats(input_file, threshold):
    """
    wire_stats.txt (7要素) を読み込み、
    「採用された配線(set)」と「間引かれた配線(dict)」に分離する
    """
    kept_wires = set()     # 採用された内部配線 (set)
    # キー: MUX (dst_x, dst_y, dst_pin), 値: そのMUX宛の間引き配線のリスト
    culled_wires_by_mux = defaultdict(list)
    
    if not os.path.exists(input_file):
        print(f"Error: '{input_file}' not found.")
        return kept_wires, culled_wires_by_mux

    with open(input_file, 'r') as f:
        for line in f:
            if line.startswith("#"): continue
            try:
                parts = line.strip().split()
                if len(parts) == 7:
                    count = int(parts[6])
                    
                    # 6要素の配線タプルを作成
                    wire_tuple = (
                        float(parts[0]) if '.' in parts[0] else int(parts[0]), # src_x (PIは小数)
                        float(parts[1]) if '.' in parts[0] else int(parts[1]), # src_y
                        int(parts[2]), # src_pin
                        int(parts[3]), # dst_x
                        int(parts[4]), # dst_y
                        int(parts[5])  # dst_pin
                    )
                    
                    if count >= threshold:
                        kept_wires.add(wire_tuple)
                    else:
                        # 間引かれた配線
                        mux_key = (wire_tuple[3], wire_tuple[4], wire_tuple[5])
                        culled_wires_by_mux[mux_key].append(wire_tuple)
                        
            except (ValueError, IndexError):
                continue
                
    print(f"Loaded {len(kept_wires)} 'kept' wires.")
    print(f"Found {sum(len(w) for w in culled_wires_by_mux.values())} 'culled' wires, categorized by destination MUX.")
    return kept_wires, culled_wires_by_mux

def load_imux_counts(input_file):
    """
    imux_in.txt を読み込み、辞書 { (x,y,pin): count } を返す
    """
    mux_counts = {}
    if not os.path.exists(input_file):
        print(f"Error: '{input_file}' not found. Run count_imux_in.py first.")
        return mux_counts
        
    with open(input_file, 'r') as f:
        for line in f:
            if line.startswith("#"): continue
            try:
                parts = [int(s) for s in line.strip().split()]
                if len(parts) == 4:
                    # key = (x, y, pin), value = count
                    mux_key = (parts[0], parts[1], parts[2])
                    mux_counts[mux_key] = parts[3]
            except (ValueError, IndexError):
                continue
    print(f"Loaded {len(mux_counts)} MUX count entries from '{input_file}'.")
    return mux_counts

def get_physical_pi_list(num_pins, grid_width):
    """
    SA_out.pyの整数座標ロジックに基づき、物理PIのリストを生成
    ( (x, y, src_pin), ... )
    """
    pins = []
    for i in range(num_pins):
        x_coord = i % grid_width
        pins.append((x_coord, -1, -1)) # (x, y, src_pin=-1)
    return pins

def main():
    # 1. 内部配線を「採用」と「間引き（宛先別）」に分離
    kept_wires, culled_by_mux = load_wire_stats(STATS_FILE, THRESHOLD)
    
    # 2. 「採用」された本数をMUXごとに読み込む
    mux_counts = load_imux_counts(IMUX_COUNT_FILE)
    
    if not mux_counts:
        print("Cannot proceed without MUX count data.")
        return

    # 3. 最終的なアーキテクチャ配線を構築 (まず採用された配線を入れる)
    final_architecture_wires = kept_wires.copy()
    
    print(f"Padding MUX inputs up to the next power of 2 (max {MUX_SIZE_CAP})...")
    
    # 利用可能な物理PIのリスト (整数座標)
    physical_pis = get_physical_pi_list(NUM_PIS, GRID_X)
    pi_to_add_index = 0
    
    padded_wire_count = 0
    padded_pi_count = 0

    # 4. MUXごとにパディング（2のべき乗への調整）処理
    for mux_key, current_count in mux_counts.items():
        
        if current_count == 0:
            continue # 0本のMUXはパディングしない
            
        target_count = current_count
        if TARGET_POWER_OF_2:
            # 目標とする2のべき乗の数を計算 (例: 13 -> 16, 30 -> 32)
            target_count = 2**math.ceil(math.log2(current_count))
        
        # ただし、ユーザ指定の最大目標（例: 32）を超えることは許さない
        if target_count > MUX_SIZE_CAP:
            target_count = MUX_SIZE_CAP
            
        slots_to_fill = target_count - current_count
        if slots_to_fill <= 0:
            continue # 既に2のべき乗か、目標サイズを超えている

        # --- パディング実行 ---
        filled_count = 0
        dst_x, dst_y, dst_pin = mux_key
        
        # 4a. まず「間引かれた配線」で埋める
        if mux_key in culled_by_mux:
            while filled_count < slots_to_fill and culled_by_mux[mux_key]:
                wire_to_add_back = culled_by_mux[mux_key].pop() # このMUX宛の配線を1本取り出す
                final_architecture_wires.add(wire_to_add_back)
                filled_count += 1
                padded_wire_count += 1
        
        slots_remaining = slots_to_fill - filled_count
        
        # 4b. 残りを「外部入力(PI)」で埋める
        for _ in range(slots_remaining):
            # 利用可能なPIを順番に割り当てる
            src_x, src_y, src_pin = physical_pis[pi_to_add_index % len(physical_pis)]
            new_pi_wire = (src_x, src_y, src_pin, dst_x, dst_y, dst_pin)
            
            final_architecture_wires.add(new_pi_wire)
            pi_to_add_index += 1
            padded_pi_count += 1

    print(f"Padding complete. Added back {padded_wire_count} culled wires and {padded_pi_count} new PI wires.")

    # 5. 最終的な配線リストをファイルに書き出す
    print(f"Saving final architecture to '{OUTPUT_FILE}'...")
    with open(OUTPUT_FILE, 'w') as f:
        f.write(f"# Final architecture: {len(final_architecture_wires)} unique wires\n")
        f.write(f"# (Based on '{STATS_FILE}' w/ threshold {THRESHOLD}, padded to {MUX_SIZE_CAP})\n")
        
        # (x, y, pin) でソートして、見やすくする
        sorted_wires = sorted(list(final_architecture_wires)) 
        
        for wire in sorted_wires:
             # PIは (0, -1, -1, ...) のように整数で保存する
             f.write(" ".join(map(str, wire)) + "\n")
             
    print("Done.")

if __name__ == "__main__":
    # SA_out.pyの整数座標ロジックに合わせて、PIも整数で扱う
    # (load_wire_stats と get_physical_pi_list で対応済み)
    main()