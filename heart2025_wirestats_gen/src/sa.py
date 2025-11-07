import networkx as nx
import random
import math
import matplotlib.pyplot as plt
import glob
from yggdrasill.utils import parse_circuit
from yggdrasill.utils import PAENode
import tqdm
import pandas as pd 
import os

'''''
def initial_placement(G, grid_size_x=4, grid_size_y=4):
    nodes = [n for n in G.nodes() if n not in ['inputs', 'outputs']]
    positions = [(x, y) for x in range(grid_size_x) for y in range(grid_size_y)]
    random.shuffle(positions)
    pos = dict(zip(nodes, positions))
    mid_x = (grid_size_x - 1) / 2
    pos['inputs'] = (mid_x, -1)
    pos['outputs'] = (mid_x, grid_size_y)

    return pos
'''

import random

def initial_placement(G, grid_size_x=4, grid_size_y=4, input_spacing=0.18, output_spacing=0.3):
    """
    ノードの初期配置を行う。入力と出力のピン間隔を個別に調整する機能付き。
    """
    # --- 1. ノードの種類を判別 ---
    internal_nodes = [n for n in G.nodes() if not G.nodes[n].get('is_io', False)]
    input_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'input']
    output_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'output']

    # --- 2. 内部ノードをグリッド内にランダム配置 ---
    positions = [(x, y) for x in range(grid_size_x) for y in range(grid_size_y)]
    random.shuffle(positions)
    pos = dict(zip(internal_nodes, positions))

    # --- 3. I/Oノードをグリッドの上下に配置 ---
    grid_mid_x = (grid_size_x - 1) / 2

    # ★★★ 入力ノードの配置 (input_spacing を使用) ★★★
    if len(input_nodes) > 0:
        total_input_width = (len(input_nodes) - 1) * input_spacing
        start_x = grid_mid_x - total_input_width / 2
        for i, node in enumerate(input_nodes):
            pos[node] = (start_x + i * input_spacing, -1)

    # ★★★ 出力ノードの配置 (output_spacing を使用) ★★★
    if len(output_nodes) > 0:
        total_output_width = (len(output_nodes) - 1) * output_spacing
        start_x = grid_mid_x - total_output_width / 2
        for i, node in enumerate(output_nodes):
            pos[node] = (start_x + i * output_spacing, grid_size_y)

    return pos
             
def total_cost(G, pos, M=10000, w_ff=2, w_fb=10, OmuxCost=100, w_io=5):
    # --- 計算方法を切り替えるスイッチ ---
    # True:  シンプル計算 (ファンアウト数やI/Oを特別扱いしない)
    # False: 従来の計算 (ファンアウト数やI/Oを考慮する)
    USE_SIMPLE_CALCULATION = True  # ★★★ ここをTrue/Falseで切り替えるだけ ★★★

    total = 0
    for u, v in G.edges():
        x1, y1 = pos[u]
        x2, y2 = pos[v]

        # スイッチの状態に応じて、使用するロジックを分岐
        if USE_SIMPLE_CALCULATION:
            # --- 【シンプル版】のコスト計算ロジック ---
            if y2 - y1 == 1:
                Ce_y = -M
            elif y2 - y1 >= 2:
                Ce_y = w_ff * (y2 - y1) + OmuxCost
            else:  # y2 - y1 < 0 (フィードバック)
                Ce_y = w_fb * (abs(y2 - y1) + 1) + OmuxCost
            
            Ce_x = abs(x2 - x1)
            total += Ce_x + Ce_y
        
        else:
            # --- 【従来版（複雑な方）】のコスト計算ロジック ---
            v_data = G.nodes[v]
            if v_data.get('type') == 'output':
                # 出力ピンへの配線を特別扱い
                total += w_io * (abs(x1 - x2) + abs(y1 - y2))
            else:
                # ファンアウト数を取得して重み付け
                fanout = G.out_degree(u)
                weight = fanout if fanout > 1 else 1
                
                if y2 - y1 == 1:
                    Ce_y = -M
                elif y2 - y1 >= 2:
                    Ce_y = w_ff * (y2 - y1) + OmuxCost
                else:  # y2 - y1 < 0
                    Ce_y = w_fb * (abs(y2 - y1) + 1) + OmuxCost
                
                Ce_x = abs(x2 - x1)
                base_cost = Ce_x + Ce_y
                total += weight * base_cost
                
    return total

'''
def total_cost(G, pos, M=10000, w_ff=2, w_fb=10, OmuxCost=100):
#def total_cost(G, pos, M=1000, w_ff=1, w_fb=5, OmuxCost=10):    
    total = 0
    for u, v in G.edges():
        if u == 'inputs' or v == 'outputs':
            continue
        
        x1, y1 = pos[u]
        x2, y2 = pos[v]

        
        if y2 - y1 == 1:
            Ce_y = -M
        elif y2 - y1 >= 2:
            Ce_y = w_ff * (y2 - y1) + OmuxCost
            #Ce_y = w_ff * (y2 - y1)
        else:# y2 - y1 < 0:
            Ce_y = w_fb * (abs(y2 - y1) + 1) + OmuxCost
            #Ce_y = w_fb * (y1 - y2) + OmuxCost
        Ce_x = abs(x2 - x1)
        

''''''
        if y2 == y1:
            Ce_y = M            
        elif y2 - y1 > 0:
            Ce_y = w_ff * (y2 - y1)
        else:# y2 - y1 < 0:
            Ce_y = w_fb * (y1 - y2) + OmuxCost            
        Ce_x = abs(x2 - x1) + abs(y2 - y1)        
        

        total += Ce_x + Ce_y
    return total        
'''      


def simulated_annealing(G, initial_pos, grid_size_x=4, grid_size_y=4, initial_temp=1000, cooling_rate=0.995, iterations=100000):
#def simulated_annealing(G, initial_pos, grid_size=4, initial_temp=3000, cooling_rate=0.995, iterations=300000):        
    current_pos = initial_pos.copy()
    best_pos = current_pos.copy()
    current_cost = total_cost(G, current_pos)
    best_cost = current_cost
    temp = initial_temp

    # 全ての可能な位置を生成
    all_positions = [(x, y) for x in range(grid_size_x) for y in range(grid_size_y)]

    # --- ★★★ ここが変更点 ★★★ ---
    # 動かす対象となる「内部ノード」のリストを事前に作成する
    internal_nodes = [n for n in G.nodes() if not G.nodes[n].get('is_io', False)]
    # --------------------------------

    for _ in range(iterations):
        '''
        nodes = [n for n in G.nodes() if n not in ['inputs', 'outputs']]
        node_to_move = random.choice(nodes)
        '''

        if not internal_nodes: # 内部ノードが一つもない場合はループを抜ける
            break
        node_to_move = random.choice(internal_nodes)
        
        # 現在の位置を除外
        possible_positions = [pos for pos in all_positions if pos != current_pos[node_to_move]]
        
        # ノードを新しい位置に移動（空いている位置または他のノードと交換）
        new_pos = current_pos.copy()
        new_position = random.choice(possible_positions)
        
        # 選択した位置に他のノードがある場合は交換、なければ単に移動
        node_at_new_position = next((node for node, pos in new_pos.items() if pos == new_position), None)
        if node_at_new_position:
            new_pos[node_at_new_position] = current_pos[node_to_move]
        new_pos[node_to_move] = new_position
        
        new_cost = total_cost(G, new_pos)
        cost_diff = new_cost - current_cost

        if cost_diff < 0 or random.random() < math.exp(-cost_diff / temp):
            current_pos = new_pos
            current_cost = new_cost

            if current_cost < best_cost:
                best_pos = current_pos.copy()
                best_cost = current_cost

        temp *= cooling_rate

    return best_pos

'''
def create_plot(G, pos, grid_size_x=4, grid_size_y=4):
    plt.figure(figsize=(12, 12))
    
    for i in range(grid_size_x+1):
        plt.axvline(x=i-0.5, color='gray', linestyle='--', alpha=0.5)

    for i in range(grid_size_y+1):
        plt.axhline(y=grid_size_y-i+0.5, color='gray', linestyle='--', alpha=0.5)



        
    inverted_pos = {node: (x, grid_size_y - y) for node, (x, y) in pos.items()}
    
    nx.draw_networkx_nodes(G, inverted_pos, node_size=500, node_color='lightblue')
    #nx.draw_networkx_nodes(G, inverted_pos, node_size=2000, node_color='lightblue')    
    nx.draw_networkx_labels(G, inverted_pos, font_size=8)
    
    nx.draw_networkx_nodes(G, inverted_pos, nodelist=['inputs', 'outputs'], node_size=3000, node_color='lightgreen')
    
    for u, v in G.edges():
        if u == 'inputs' or v == 'outputs':
            continue        
        start = inverted_pos[u]
        end = inverted_pos[v]
        plt.arrow(start[0], start[1], end[0]-start[0], end[1]-start[1], 
                  shape='full', lw=1, length_includes_head=True, head_width=0.3)
#            shape='full', lw=1, length_includes_head=True, head_width=0.2)        
    
    plt.title("Place and Route")
    plt.xlim(-1, grid_size_x)
    plt.ylim(-1, grid_size_y + 2)
    plt.axis('off')
    plt.tight_layout()
'''
def create_plot(G, pos, grid_size_x=4, grid_size_y=4):
    plt.figure(figsize=(12, 12))
    
    # --- 1. グリッド線を描画 ---
    for i in range(grid_size_x + 1):
        plt.axvline(x=i - 0.5, color='gray', linestyle='--', alpha=0.5)
    for i in range(grid_size_y + 1):
        plt.axhline(y=i - 0.5, color='gray', linestyle='--', alpha=0.5)

    # --- 2. ノードの種類を明確に分類 ---
    # is_io属性がFalseのノードだけを内部ノードとする
    internal_nodes = [n for n in G.nodes() if not G.nodes[n].get('is_io', False)]
    # is_io属性がTrueのノードだけをI/Oノードとする
    io_nodes = [n for n in G.nodes() if G.nodes[n].get('is_io', True)]

    # --- 3. 種類ごとにノードを描画 ---
    # 内部ノードを水色で描画
    nx.draw_networkx_nodes(G, pos, nodelist=internal_nodes, node_size=500, node_color='lightblue')
    # I/Oノードを緑色で描画
    nx.draw_networkx_nodes(G, pos, nodelist=io_nodes, node_size=500, node_color='lightgreen')
    
    # 全てのノードのラベルを描画
    nx.draw_networkx_labels(G, pos, font_size=8)
    
    # --- 4. 全てのエッジ（配線）を描画 ---
    for u, v in G.edges():
        # 配線の始点と終点の情報を取得
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        y1 = pos[u][1]
        y2 = pos[v][1]
        
        # デフォルトの色を黒（内部配線）に設定
        edge_color = 'black'
        
        # 条件に応じて色を決定
        if u_data.get('type') == 'input':
            edge_color = 'blue'  # 入力ピンからの配線
        elif v_data.get('type') == 'output':
            edge_color = 'red'   # 出力ピンへの配線
        elif y1 > y2:
            edge_color = 'orange' # 逆方向の配線（フィードバック）

        start = pos[u]
        end = pos[v]
        plt.arrow(start[0], start[1], end[0] - start[0], end[1] - start[1], 
                  shape='full', lw=1, length_includes_head=True, head_width=0.2, 
                  color=edge_color) # ★ 色を指定

    # --- 5. グラフの見た目を調整 ---
    plt.title("Place and Route")
    plt.xlim(-1.5, grid_size_x + 0.5)
    plt.ylim(-1.5, grid_size_y + 0.5)
    
    # Y軸の向きを反転させ、上が0になるようにする (上から下への流れを表現)
    plt.gca().invert_yaxis()
    
    plt.axis('off')
    plt.tight_layout()
    

def draw_fpga(G, pos, grid_size_x=4, grid_size_y=4):
    create_plot(G, pos, grid_size_x, grid_size_y)
    plt.show()

def save_fpga(G, pos, grid_size_x=4, grid_size_y=4, filename='place_and_route.png'):
    create_plot(G, pos, grid_size_x, grid_size_y)
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

def get_grid_size(num_nodes):
    # 入力と出力ノードを除外

    #return 5
    #return 16
    return 4
    
    num_nodes -= 2
    num_nodes *= 2
    sqrt_nodes = math.sqrt(num_nodes)
    grid_size = math.ceil(sqrt_nodes)
    # sqrt_nodes = math.sqrt(num_nodes)    
    # grid_size = math.ceil(sqrt_nodes / 2) * 2    
    #return max(4, grid_size)



# count wires and compute histgram (statistics) (wireStats)    
def compute_wireStats(wires, wireStats):
    for w in wires:
        v = wireStats.get(w)
        if v is None:
            wireStats[w] = 1
        else:
            wireStats[w] = wireStats[w] + 1
        
    
    
# Get interconnects from PAE output to PAE input
def get_wires(PAENodes, optimized_pos):

    # edge count dictionary

    PAEOutputNameToNode = {}  # Dictionary of key: PAE output, value: PAE node
    PAEOutputNameToIndex = {} # Dictionary of key: PAE output, value: PAE output index

    # re-organize PAE netlist (gather information PAEOutputNameToNode[], PAEOutputNameToIndex[])
    for pn in PAENodes:
        for oname in pn.outputNames:
            PAEOutputNameToNode[oname] = pn
            PAEOutputNameToIndex[oname] = pn.outputNames.index(oname)

    # build edge information
    edges = []

    for pn in PAENodes:

#        print(">>> pn : ", pn.name)
        for input_index, iname in enumerate(pn.inputNames):
            if iname == 'nc':
                continue

#            print(">>>>>> pn input: ", iname)            
            output_pn = PAEOutputNameToNode.get(iname, None)
            output_index = PAEOutputNameToIndex.get(iname, -1)
            if output_pn != None:
 #               print(">>>>>>>>> output pn: ", output_pn.name, ", index=", output_index)
                edge = [] # (output PAE node, output index, PAE node, input index)
                edge.append(output_pn.name)
                edge.append(output_index)
                edge.append(pn.name)
                edge.append(input_index)
                edges.append(edge)

    wires = []
    for e in edges:
  #      print("edge:")
   #     print(e)
        
        # replace PAE name to PAE coordinate
        src_pos = optimized_pos[e[0]]  # position of output PAE cell
        dst_pos = optimized_pos[e[2]]  # position of PAE Cell

        wire = (src_pos[0], src_pos[1], e[1], dst_pos[0], dst_pos[1], e[3])
        wires.append(wire)
        
                
    return wires

wireStats = {} # dictionary for wire and wire count

# ===============================================================
# 統計情報集計用の変数を初期化 (ここから追加)
# ===============================================================
total_netlists_processed = 0
all_feedback_counts = [] # 各ネットリストのフィードバック数を格納するリスト

# 各入力ピンの「位置インデックス」ごとのファンアウト数をリストで格納する辞書
# 例: {0: [3, 5], 1: [2, 2, 6], ...}
all_input_fanouts_by_position = {}
# ===============================================================
# (ここまで追加)
# ===============================================================



target_files_to_save = ["0632.net", "0984.net","0652.net","0987.net","0985.net","0572.net"]
# 処理したいネットリストのリストを自分で作成
files_to_process = [
    'data/netlists/0632.net',
    'data/netlists/0984.net',
    'data/netlists/0652.net',
    'data/netlists/0987.net',
    'data/netlists/0985.net',
    'data/netlists/0572.net'
]


#for filename in tqdm.tqdm(files_to_process): ##debug用
for filename in tqdm.tqdm(glob.glob('data/netlists_500/*.net')):
    with open(filename) as f:
        G, PAENodes = parse_circuit(f.read())

#    for pn in PAENodes:
#        print("print node")
#        print("name:", pn.name, "inputNames:", pn.inputNames, "outputNames", pn.outputNames)

    #grid_size = get_grid_size(len(G.nodes()))
    grid_size_x = 4
    grid_size_y = 4
    initial_pos = initial_placement(G, grid_size_x, grid_size_y)
    #print("Initial cost:", total_cost(G, initial_pos))     # added
    optimized_pos = simulated_annealing(G, initial_pos, grid_size_x=grid_size_x, grid_size_y=grid_size_y)

    # ===============================================================
    # 統計情報の計算と蓄積 
    # ===============================================================
    
    # --- 1. フィードバック数の計算 ---
    feedback_count = 0
    internal_nodes = {n for n in G.nodes() if not G.nodes[n].get('is_io', False)}
    for u, v in G.edges():
        if u in internal_nodes and v in internal_nodes:
            if optimized_pos[u][1] > optimized_pos[v][1]:
                feedback_count += 1

    # --- 2. 外部入力のファンアウト計算 ---
    input_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'input']
    input_fanout_stats = {node: G.out_degree(node) for node in input_nodes}
    
     # --- 3. 計算結果を集計用の変数に蓄積 ---
    total_netlists_processed += 1
    all_feedback_counts.append(feedback_count)
    
    # ★★★ 各入力ノードの「位置」をキーとしてファンアウト情報を蓄積 ★★★
    # enumerateを使い、各入力ノードの位置インデックス(i)を取得します
    for i, node_name in enumerate(input_nodes):
        fanout = input_fanout_stats[node_name]
        # 位置インデックス(i)をキーとしてファンアウト数を追加
        all_input_fanouts_by_position.setdefault(i, []).append(fanout)
    # ===============================================================
    # 
    # ===============================================================

     # もし、現在のファイル名に、保存したいファイル名が含まれていたら(ここ下３行コメントアウトで描画とメレル)
    #if any(target in filename for target in target_files_to_save):
    #    print(f"\nSaving image for {filename}...") # どのファイルが保存されたか分かるようにprint文を入れると親切
    #    save_fpga(G, optimized_pos, grid_size_x=grid_size_x, grid_size_y=grid_size_y, filename=f'output/{filename.split("/")[-1].replace(".net", ".png")}')

    #draw_fpga(G, optimized_pos, grid_size_x=grid_size_x, grid_size_y=grid_size_y) ######kokotuika
    #print("Optimized cost:", total_cost(G, optimized_pos)) # added
    #save_fpga(G, optimized_pos, grid_size_x=grid_size_x, grid_size_y=grid_size_y, filename=f'output/{filename.split("/")[-1].replace(".net", ".png")}')
    #save_fpga(G, optimized_pos, grid_size=grid_size, filename=f'output/{filename.split("/")[-1].replace(".net", ".png")}')


    wires = get_wires(PAENodes, optimized_pos)
    #for w in wires:
        #print("wire:")
        #print(w)

    # ★★★ ここから追加 ★★★
    # ---------------------------------------------------------------
    # 各ネットリストの配線結果を個別のファイルに保存する
    # ---------------------------------------------------------------
    # 出力ディレクトリを作成 (なければ)
    output_dir = "individual_wire_results"
    os.makedirs(output_dir, exist_ok=True) # Python 3.2+
    
    # ネットリスト名から拡張子を除いた部分を取得
    base_filename = os.path.basename(filename).replace(".net", "")
    output_path = os.path.join(output_dir, f"wires_{base_filename}.txt")
    
    try:
        with open(output_path, "w") as f_out:
            for wire_tuple in wires:
                # タプルをスペース区切りの文字列に変換して書き出す
                # 例: (0, 0, 1, 1, 0, 2) -> "0 0 1 1 0 2"
                f_out.write(" ".join(map(str, wire_tuple)) + "\n")
        # print(f"Saved individual wires for {base_filename} to {output_path}") # デバッグ用
    except IOError as e:
        print(f"Error writing individual wire file for {base_filename}: {e}")
    # ---------------------------------------------------------------
    # ★★★ ここまで追加 ★★★




    compute_wireStats(wires, wireStats)

sortedWireStats = dict(sorted(wireStats.items(), key=lambda item: item[1], reverse=True))

# 新しいきれいな`wire_stats.txt`をカレントディレクトリに書き出す
print(f"Total {len(sortedWireStats)} unique wires found. Saving to wire_stats.txt...")
with open("wire_stats.txt", "w") as f:
    for wire_tuple, count in sortedWireStats.items():
        # 例: (2, 0, 2, 0, 3, 2) と 1 -> "2 0 2 0 3 2 1"
        f.write(f"{' '.join(map(str, wire_tuple))} {count}\n")

print("Done.")


# ===============================================================
# 全ネットリストの統計情報を集計しファイルに書き出す
# ===============================================================
print("\nCalculating final statistics over all processed netlists...")

# --- 1. フィードバック数の平均を計算 ---
avg_feedback = sum(all_feedback_counts) / len(all_feedback_counts) if all_feedback_counts else 0

# --- 2. 各「位置」の外部入力の平均ファンアウトを計算 ---
avg_input_fanouts_by_pos = {}
for pos_index, fanouts in all_input_fanouts_by_position.items():
    avg_input_fanouts_by_pos[pos_index] = {
        'average': sum(fanouts) / len(fanouts),
        'count': len(fanouts) # そのピン位置が使われたネットリスト数
    }

# 結果を平均ファンアウト数の降順でソート
sorted_avg_fanouts = sorted(avg_input_fanouts_by_pos.items(), key=lambda item: item[1]['average'], reverse=True)

# --- 3. 結果をファイルに書き出す ---
stats_filename = "netlist_statistics_by_position.txt"
with open(stats_filename, "w") as f:
    f.write("--- Overall Circuit Statistics ---\n")
    f.write(f"Total netlists processed: {total_netlists_processed}\n\n")
    
    f.write("--- Feedback Statistics ---\n")
    f.write(f"Average feedback wires per netlist: {avg_feedback:.2f}\n\n")
    
    f.write("--- Input Pin Position Fan-out Statistics (Sorted by Average Fan-out) ---\n")
    f.write(f"{'Pin Index':<15} | {'Average Fan-out':<20} | {'Usage Count (Netlists)'}\n")
    f.write(f"{'-'*15}-+-{'-'*20}-+-{'-'*25}\n")
    
    for pos_index, stats in sorted_avg_fanouts:
        f.write(f"{pos_index:<15} | {stats['average']:<20.2f} | {stats['count']}\n")

print(f"Overall statistics based on pin position have been saved to '{stats_filename}'")

# ===============================================================
# Excelファイルへの書き出し処理 (このブロックを丸ごと差し替え)
# ===============================================================

# --- 1. Excelに出力するためのデータを作成 ---

# a) ピンごとのファンアウト統計データ 
df_fanout_data = []
for pos_index, stats in sorted_avg_fanouts:
    df_fanout_data.append({
        'Pin Index': pos_index,
        'Average Fan-out': stats['average'],
        'Usage Count (Netlists)': stats['count']
    })
df_fanout = pd.DataFrame(df_fanout_data)

# b) 全体的な統計データ (フィードバック数の平均など)
df_summary_data = {
    'Statistic': [
        'Total netlists processed',
        'Average feedback wires per netlist'
    ],
    'Value': [
        total_netlists_processed,
        f"{avg_feedback:.2f}"
    ]
}
df_summary = pd.DataFrame(df_summary_data)


# --- 2. 複数のシートを持つExcelファイルとして保存 ---
excel_filename = "netlist_statistics.xlsx"
with pd.ExcelWriter(excel_filename) as writer:
    df_summary.to_excel(writer, sheet_name='Summary', index=False)
    df_fanout.to_excel(writer, sheet_name='Fan-out by Position', index=False)

print(f"All statistics have been saved to '{excel_filename}' with two sheets.")
# ===============================================================
# 
# ===============================================================

'''
sortedWireStats = dict(sorted(wireStats.items(), key=lambda item: item[1], reverse=True))
    
print("wireStats: ", len(sortedWireStats), " wires")
i = 0
for k, v in sortedWireStats.items():
    print("[",i,"]",k, "count=", v)
    i+=1
    

exit()
'''