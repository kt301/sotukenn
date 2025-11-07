import os
import subprocess
import argparse

# netlistディレクトリのパス
directory_path = './netlists_500'
#directory_path = './failnetlist'

# ログファイルを空にする
with open('log', 'w') as log_file:
    log_file.write("--- Log file initialized. ---\n")

# CSVサマリーファイルを用意し、ヘッダーを書き込む
summary_file_path = 'conf_bits_summary.csv'
with open(summary_file_path, 'w') as f:
    # ヘッダー名を'average_conf_bits'から変更
    f.write("ws_count,successful_netlists,total_netlists,success_rate_percent,configuration_bits\n")

parser = argparse.ArgumentParser()
parser.add_argument('--ws_count', type=int, default=1, help='配線ヒストグラムファイルでの配線数の下限値')
args = parser.parse_args()

for count in range (2,4, 10):
    
    # === ループごとの集計用変数を初期化 ===
    successful_netlists_count = 0
    final_conf_bits = -1  # -1は「未計算」を意味する
    # ====================================
    
    # カウンターの初期化
    netlist_counter = 0
    not_found_counter = 0
    not_enough_numPI_counter = 0
    failed_netlists = []

    for filename in os.listdir(directory_path):
        if filename.endswith('.net'):
            netlist_counter += 1
            file_path = os.path.join(directory_path, filename)
            
            opt = '--ws_count='+str(count)
            
            command_list = ['python3', 'pea.py', opt, file_path]
            print(f"Processing {filename} with ws_count={count}...")
            result = subprocess.run(command_list, capture_output=True, text=True)
            
            with open('log', 'w') as log_file:
                log_file.write(result.stdout)
                log_file.write(result.stderr)

            output_text = result.stdout + result.stderr
            
            if 'P&R solution not found' not in output_text:
                # P&Rに成功
                successful_netlists_count += 1
                
                # ### === まだコンフィグビット数を計算していない場合のみ、一度だけ計算 === ###
                if final_conf_bits == -1:
                    for line in output_text.splitlines():
                        if line.startswith('numConfBits='):
                            try:
                                bits = int(line.split('=')[1])
                                final_conf_bits = bits
                                print(f"  -> Config Bits calculated: {final_conf_bits} (from {filename})")
                                break # 計算が終わったのでこれ以上探さない
                            except (ValueError, IndexError):
                                break
                # ####################################################################

            else:
                # P&R失敗
                not_found_counter += 1
                failed_netlists.append(filename)
            
            if 'not enough numPI' in output_text:
                not_enough_numPI_counter += 1
            
            print(f'  (Progress: #total: {netlist_counter}, #failed: {not_found_counter}, #not_enough_PIs: {not_enough_numPI_counter})')

    # === ws_countループの最後に結果を表示・記録 ===
    print(f"\n--- Summary for ws_count = {count} ---")
    
    if successful_netlists_count > 0:
        success_rate = (successful_netlists_count / netlist_counter) * 100
        
        print(f"Success Rate: {successful_netlists_count} / {netlist_counter} ({success_rate:.2f}%)")
        print(f"Configuration Bits: {final_conf_bits}") # 平均ではなく固定値を表示

        # CSVファイルにサマリーを1行追記
        with open(summary_file_path, 'a') as f:
            f.write(f"{count},{successful_netlists_count},{netlist_counter},{success_rate:.2f},{final_conf_bits}\n")
            
    else:
        print("No netlists were processed successfully.")
        with open(summary_file_path, 'a') as f:
            f.write(f"{count},0,{netlist_counter},0.00,0\n") # 失敗時は0として記録

    print("------------------------------------\n")

    if failed_netlists:
        print(f"--- Failed Netlists (ws_count={count}) ---")
        for fname in failed_netlists:
            print(f" - {fname}")
        print("------------------------------------\n")