import os
import glob
from collections import defaultdict
import argparse  # ★★★ 引数を扱うために追加 ★★★

def main():
    """
    既存のwire_stats.txtを読み込み、指定された閾値以上で使用された配線のみを対象として、
    各IMUXごとの平均内部配線数を計算する。SAの再実行は一切行わない。
    """
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    # ★★★ コマンドラインから閾値を受け取る処理を追加 ★★★
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    parser = argparse.ArgumentParser(description='Analyze average internal wire usage per IMUX from wire_stats.txt.')
    parser.add_argument('--ws_count', type=int, default=0, help='Minimum wire count to consider for analysis.')
    args = parser.parse_args()
    
    print(f"Analyzing with threshold ws_count >= {args.ws_count}")
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

    # 1. アーキテクチャのグリッドサイズを定義
    GRID_X = 4
    GRID_Y = 4 

    # 2. SA処理の対象となったネットリストの総数をカウント
    netlist_directory = 'data/netlists'
    try:
        netlist_count = len(glob.glob(os.path.join(netlist_directory, '*.net')))
        if netlist_count == 0:
            print(f"Error: No .net files found in '{netlist_directory}'. Cannot calculate average.")
            return
    except Exception as e:
        print(f"Error counting netlist files: {e}")
        return

    print(f"Analysis based on {netlist_count} netlists processed by sa.py.")

    # 3. 各IMUXの総使用回数を格納する辞書を準備
    mux_total_counts = defaultdict(int)

    # 4. wire_stats.txt を読み込んで集計
    wire_stats_file = "wire_stats.txt"
    try:
        with open(wire_stats_file, 'r') as f:
            for line in f:
                try:
                    parts = [int(s) for s in line.strip().split()]
                    if len(parts) == 7:
                        count = parts[6]
                        
                        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
                        # ★★★ 閾値でフィルタリングする処理を追加 ★★★
                        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
                        if count >= args.ws_count:
                            dst_x, dst_y, dst_pin = parts[3], parts[4], parts[5]
                            mux_id = (dst_y, dst_x, dst_pin)
                            mux_total_counts[mux_id] += count

                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        print(f"Error: '{wire_stats_file}' not found. Please run sa.py first.")
        return

    # 5. 平均を計算してファイルに出力
    output_filename = f"mux_average_inputs_ws{args.ws_count}.csv"
    print(f"Calculating averages and saving to {output_filename}...")

    with open(output_filename, "w") as f:
        f.write("imux_name,average_internal_inputs\n")

        for y in range(GRID_Y):
            for x in range(GRID_X):
                for imux_n in range(4):
                    mux_id = (y, x, imux_n)
                    total_usage = mux_total_counts.get(mux_id, 0)
                    average = total_usage / netlist_count if netlist_count > 0 else 0
                    
                    lane_id = y
                    global_pae_id = y * GRID_X + x
                    imux_name = f"IMUX{imux_n}_PAE{global_pae_id}_lane{lane_id}"
                    
                    f.write(f"{imux_name},{average:.4f}\n")

    print("Done.")

if __name__ == '__main__':
    main()