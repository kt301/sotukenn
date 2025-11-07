# run_fail.py

import os
import subprocess

# ##################################################################
# ★★★ ここを編集 ★★★
#
# 1. ネットリストが保存されているディレクトリのパスを指定
DIRECTORY_PATH = './netlists_500'

# 2. 試したいネットリストのファイル名を下のリストに記述
#    例: ['netlist_A.net', 'netlist_B.net']
TARGET_NETLISTS = [
    "0006.net",
]
# ##################################################################


def main():
    """スクリプトのメイン実行関数"""
    # リストが空の場合はエラーメッセージを出して終了
    if not TARGET_NETLISTS:
        print("エラー: スクリプト内の TARGET_NETLISTS リストが空です。")
        print("処理したいファイル名を追加してください。")
        return

    # --- 実行準備 ---
    summary_file_path = 'summary_fail.csv'
    log_file_path = 'log_fail.log'

    # ログファイルとCSVを初期化
    with open(log_file_path, 'w') as log_file:
        log_file.write(f"--- Log file for {', '.join(TARGET_NETLISTS)} initialized. ---\n")
    with open(summary_file_path, 'w') as f:
        f.write("ws_count,successful_netlists,total_netlists,success_rate_percent,configuration_bits\n")

    print(f"--- ディレクトリ '{DIRECTORY_PATH}' を対象とします ---")
    print(f"--- ターゲット: {len(TARGET_NETLISTS)}個の指定ネットリストを処理します ---")
    for fname in TARGET_NETLISTS:
        print(f"  - {fname}")
    print("----------------------------------------------------")

    # --- メイン処理 (ws_countループ) ---
    # ws_countの範囲はここで直接指定します (例: 1から6まで1刻み)
    for count in range(6, 8, 10):
        run_processing(
            ws_count=count,
            directory_path=DIRECTORY_PATH,
            files_to_process=TARGET_NETLISTS,
            summary_file_path=summary_file_path,
            log_file_path=log_file_path
        )

def run_processing(ws_count, directory_path, files_to_process, summary_file_path, log_file_path):
    """指定されたファイルリストに対してP&R処理を実行し、結果を集計する関数"""
    successful_netlists_count = 0
    final_conf_bits = -1
    netlist_counter = 0
    not_found_counter = 0
    failed_netlists = []

    for filename in files_to_process:
        netlist_counter += 1
        file_path = os.path.join(directory_path, filename)
        
        # ファイルが存在しない場合は警告してスキップ
        if not os.path.exists(file_path):
            print(f"警告: ファイルが見つかりません。スキップします: {file_path}")
            failed_netlists.append(f"{filename} (Not Found)")
            not_found_counter += 1
            continue
        
        opt = f'--ws_count={ws_count}'
        command_list = ['python3', 'pea.py', opt, file_path]
        
        print(f"Processing {filename} with ws_count={ws_count}...")
        result = subprocess.run(command_list, capture_output=True, text=True)
        
        # ログファイルに追記
        with open(log_file_path, 'a') as log_file:
            log_file.write(f"\n--- Output for {filename} (ws_count={ws_count}) ---\n")
            log_file.write(result.stdout)
            log_file.write(result.stderr)
            log_file.write("----------------------------------------\n")

        output_text = result.stdout + result.stderr
        
        if 'P&R solution not found' not in output_text:
            successful_netlists_count += 1
            # 最初の成功例からコンフィグビット数を取得
            if final_conf_bits == -1:
                for line in output_text.splitlines():
                    if line.startswith('numConfBits='):
                        try:
                            final_conf_bits = int(line.split('=')[1])
                            print(f"  -> Config Bits: {final_conf_bits}")
                            break
                        except (ValueError, IndexError):
                            break
        else:
            not_found_counter += 1
            failed_netlists.append(filename)

    # --- ws_countごとの結果を表示・記録 ---
    print(f"\n--- Summary for ws_count = {ws_count} ---")
    if netlist_counter > 0:
        success_rate = (successful_netlists_count / netlist_counter) * 100
        print(f"Success Rate: {successful_netlists_count} / {netlist_counter} ({success_rate:.2f}%)")
        with open(summary_file_path, 'a') as f:
            # 成功例がない場合はコンフィグビット数を0として記録
            f.write(f"{ws_count},{successful_netlists_count},{netlist_counter},{success_rate:.2f},{final_conf_bits if final_conf_bits != -1 else 0}\n")
    else:
        print("No netlists were processed.")

    if failed_netlists:
        print("\n--- Failed Netlists ---")
        for fname in failed_netlists:
            print(f" - {fname}")
    print("------------------------------------\n")


if __name__ == '__main__':
    main()