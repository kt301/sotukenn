import os
import subprocess
import argparse

# カウンターの初期化
netlist_counter = 0
not_found_counter = 0
not_enough_numPI_counter = 0

# netlistディレクトリのパス
directory_path = './netlists'


parser = argparse.ArgumentParser()
parser.add_argument('--ws_count', type=int, default=1, help='配線ヒストグラムファイルでの配線数の下限値')
args = parser.parse_args()
print('ws_count=' + str(args.ws_count))    


# ディレクトリ内のすべてのファイルを処理
for filename in os.listdir(directory_path):
    if filename.endswith('.net'):
        netlist_counter += 1
        file_path = os.path.join(directory_path, filename)

        opt = '--ws_count='+str(args.ws_count)
        
        # com.pyコマンドを実行し、出力をキャプチャ
        command_list = ['python', 'pea.py', opt, file_path]
        print(f"command_list: {command_list}")
        result = subprocess.run(command_list, capture_output=True, text=True)
        
        # 標準出力と標準エラー出力をログファイルに書き込む
        with open('log', 'w') as log_file:
            log_file.write(result.stdout)
            log_file.write(result.stderr)
        
        # ログファイルを読み込み、"pass"キーワードをチェック
        with open('log', 'r') as log_file:
            log_content = log_file.read()
            if 'P&R solution not found' in log_content:            
            #if 'pass' in log_content:
                not_found_counter += 1
                
            if 'not enough numPI' in log_content:            
                not_enough_numPI_counter += 1

        print(f'#netlists: {netlist_counter}, P&R not found: {not_found_counter}, not enough PIs: {not_enough_numPI_counter}')                


# カウンターの値を出力
print(f'Final: #netlists: {netlist_counter}, P&R not found: {not_found_counter}, not enough PIs: {not_enough_numPI_counter}')
