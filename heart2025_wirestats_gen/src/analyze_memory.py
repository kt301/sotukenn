import os
import math
from collections import defaultdict
import argparse # 引数を扱えるようにする

def main():
    parser = argparse.ArgumentParser(description='Analyze Configuration Memory from a wire statistics file.')
    parser.add_argument('input_file', type=str, 
                        help='Input wire statistics file (e.g., "wirestat_final.txt" or "wire_stats.txt")')
    args = parser.parse_args()

    INPUT_FILE = args.input_file
    OUTPUT_FILE = f"memory_analysis_of_{os.path.basename(INPUT_FILE)}.txt"

    print(f"Loading '{INPUT_FILE}' to analyze configuration memory...")
    
    wirestat_final_set = set()
    total_lines = 0
    is_wire_stats_file = (os.path.basename(INPUT_FILE) == 'wire_stats.txt')

    if not os.path.exists(INPUT_FILE):
        print(f"Error: '{INPUT_FILE}' not found.")
        return

    # 1. wirestat_final.txt または wire_stats.txt から配線セットを読み込む
    with open(INPUT_FILE, 'r') as f:
        for line in f:
            total_lines += 1
            if line.startswith("#"): continue
            try:
                parts = line.strip().split()
                
                # wire_stats.txt (7要素) と wirestat_final.txt (6要素) の両方に対応
                if len(parts) == 6 or (is_wire_stats_file and len(parts) == 7):
                     # PIからの配線 (x, y, -1, ...)
                    if '.' in parts[0]: # x座標が小数か
                        wire = (float(parts[0]), float(parts[1]), int(parts[2]), 
                                int(parts[3]), int(parts[4]), int(parts[5]))
                    # 内部配線
                    else:
                        wire = (int(parts[0]), int(parts[1]), int(parts[2]), 
                                int(parts[3]), int(parts[4]), int(parts[5]))
                    wirestat_final_set.add(wire)
            except (ValueError, IndexError):
                continue

    # 2. 構成メモリ評価
    print(f"Analyzing {len(wirestat_final_set)} unique wires (from {total_lines} lines)...")
    mux_internal_inputs = defaultdict(int)
    mux_external_inputs = defaultdict(int)
    
    for wire in wirestat_final_set:
        src_x, src_y, src_pin, dst_x, dst_y, dst_pin = wire
        mux_key = (dst_x, dst_y, dst_pin) # 宛先のMUX
        
        if src_y < 0 or src_pin == -1: # 外部入力(PI)からの配線
            mux_external_inputs[mux_key] += 1
        else: # 内部セルからの配線
            mux_internal_inputs[mux_key] += 1

    total_conf_bits = 0
    all_mux_keys = set(mux_internal_inputs.keys()) | set(mux_external_inputs.keys())
    
    report_lines = []
    report_lines.append(f"--- Configuration Memory Analysis (based on {INPUT_FILE}) ---")
    report_lines.append(f"Total unique wires: {len(wirestat_final_set)}")
    report_lines.append(f"Total unique MUX ports used: {len(all_mux_keys)}")
    report_lines.append("\nDetailed MUX Input Breakdown (Top 20 most inputs):")
    report_lines.append(f"{'MUX Key (x, y, pin)':<25} | {'Total Inputs':<12} | {'Internal':<10} | {'External (PI)':<10} | {'Conf. Bits'}")
    report_lines.append(f"{'-'*25}-+-{'-'*12}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")

    mux_stats = []
    for mux_key in all_mux_keys:
        internal_count = mux_internal_inputs.get(mux_key, 0)
        external_count = mux_external_inputs.get(mux_key, 0)
        total_inputs = internal_count + external_count
        
        conf_bits = 0
        if total_inputs > 1: # 1入力MUXはワイヤとみなし0ビット
            conf_bits = math.ceil(math.log2(total_inputs))
            
        total_conf_bits += conf_bits
        mux_stats.append((mux_key, total_inputs, internal_count, external_count, conf_bits))

    mux_stats.sort(key=lambda x: x[1], reverse=True) # 合計入力数でソート

    for stat in mux_stats[:20]: # 上位20件だけ表示
        key_str = f"({stat[0][0]}, {stat[0][1]}, {stat[0][2]})"
        line = f"{key_str:<25} | {stat[1]:<12} | {stat[2]:<10} | {stat[3]:<10} | {stat[4]}"
        report_lines.append(line)
        
    report_lines.append("...")
    report_lines.append(f"\nTotal Configuration Bits (All MUXes): {total_conf_bits}")

    # 3. レポートをファイルとコンソールに出力
    print(f"\nSaving configuration memory analysis to '{OUTPUT_FILE}'...")
    with open(OUTPUT_FILE, "w") as f:
        for line in report_lines:
            print(line)
            f.write(line + "\n")
            
    print("Analysis complete.")

if __name__ == "__main__":
    main()