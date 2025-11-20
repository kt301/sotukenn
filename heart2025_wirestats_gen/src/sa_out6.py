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
from collections import defaultdict

def initial_placement(G, grid_size_x=4, grid_size_y=4):   
    #1. ノードの種類を判別
    internal_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'internal']
    input_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'input']
    output_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'output']

    #2. 内部ノードをグリッド内にランダム配置
    positions = [(x, y) for x in range(grid_size_x) for y in range(grid_size_y)]
    random.shuffle(positions)
    pos = dict(zip(internal_nodes, positions[:len(internal_nodes)]))

    #3. I/Oノードをグリッドの上下に配置
    if len(input_nodes) > 0:
        for i, node in enumerate(input_nodes):
            x_coord = i
            pos[node] = (x_coord, -1)

    if len(output_nodes) > 0:
        for i, node in enumerate(output_nodes):
            x_coord = i
            pos[node] = (x_coord, grid_size_y)

    return pos

def get_wires(PAENodes, optimized_pos, G):
    """
    最終的な配置(optimized_pos)に基づき、使用された物理配線の「集合(set)」を返す。
    """
    PAEOutputNameToNode = {}  # Dictionary of key: PAE output, value: PAE node
    PAEOutputNameToIndex = {} # Dictionary of key: PAE output, value: PAE output index

    for pn in PAENodes:
        for oname in pn.outputNames:
            PAEOutputNameToNode[oname] = pn
            PAEOutputNameToIndex[oname] = pn.outputNames.index(oname)
    wires_set = set() 

    # 1. 内部セル -> 内部セルの配線
    for pn in PAENodes:
        if pn.name not in optimized_pos: continue 
        for input_index, iname in enumerate(pn.inputNames):
            if iname == 'nc': continue
            output_pn = PAEOutputNameToNode.get(iname)
            if output_pn:
                if output_pn.name not in optimized_pos: continue 
                output_index = PAEOutputNameToIndex.get(iname, -1)
                src_pos = optimized_pos[output_pn.name]
                dst_pos = optimized_pos[pn.name]
                wire = (
                    int(round(src_pos[0])), int(round(src_pos[1])), output_index, 
                    int(round(dst_pos[0])), int(round(dst_pos[1])), input_index
                )
                wires_set.add(wire)

    # 2. PI -> 内部セルの配線
    for u, v in G.edges():
        v_data = G.nodes.get(v, {}) # ノードvが存在するか確認
        # G.nodes[v]['pae_node'] が存在するかどうかでPAEセルか判断する
        if G.nodes[u].get('type') == 'input' and 'pae_node' in v_data:
            if u not in optimized_pos or v not in optimized_pos: continue
            
            dst_pin = -1
            try:
                # G.nodes[v]['pae_node'] は main 関数で設定される
                for i, iname in enumerate(v_data['pae_node'].inputNames):
                    if iname == u:
                        dst_pin = i
                        break
            except KeyError:
                 continue # 'pae_node' がない
            if dst_pin == -1: continue

            src_pos = optimized_pos[u] # PIの物理座標
            dst_pos = optimized_pos[v] # セルの物理座標
            wire = (
                src_pos[0], src_pos[1], -1, # PIのsrc_pinは-1とする
                int(round(dst_pos[0])), int(round(dst_pos[1])), dst_pin
            )
            wires_set.add(wire)
            
    return wires_set

def compute_wireStats(wires_collection, wireStats_total_usage):
    """ 
    今配置が終わったネットリストの配線結果から、使った配線をプラス１して５００個のネットリストでの使用回数を数えてる
    """
    for w in wires_collection:
        wireStats_total_usage[w] += 1


def total_cost(G, pos, PAENodes, wirestat_final_set, M=10000, w_ff=2, w_fb=10,MUX_PENALTY_WEIGHT=10000,SHARED_BONUS=-10000,
               MUX_SIZE_LIMIT=32, OmuxCost=0, w_io=0):
    total = 0
    mux_usage = defaultdict(int) # この配置でのMUX使用数をカウント
    current_wires = set()        # この配置で使う全配線

    # 1. 現時点の配置(pos)から、使う「物理配線」を全て計算
    PAEOutputNameToNode = {oname: pn for pn in PAENodes for oname in pn.outputNames}
    PAEOutputNameToIndex = {oname: pn.outputNames.index(oname) for pn in PAENodes for oname in pn.outputNames}

    # 内部セル -> 内部セルの配線
    for pn in PAENodes:
        if pn.name not in pos: continue 
        for input_index, iname in enumerate(pn.inputNames):
            if iname == 'nc': continue
            output_pn = PAEOutputNameToNode.get(iname)
            if output_pn:
                if output_pn.name not in pos: continue 
                output_index = PAEOutputNameToIndex.get(iname, -1)
                src_pos = pos[output_pn.name]
                dst_pos = pos[pn.name]
                wire = (
                    int(round(src_pos[0])), int(round(src_pos[1])), output_index, 
                    int(round(dst_pos[0])), int(round(dst_pos[1])), input_index
                )
                current_wires.add(wire)
                mux_key = (dst_pos[0], dst_pos[1], input_index)
                mux_usage[mux_key] += 1

    # PI -> 内部セルの配線
    for u, v in G.edges():
        v_data = G.nodes.get(v, {})
        if G.nodes[u].get('type') == 'input' and 'pae_node' in v_data:
            if u not in pos or v not in pos: continue
            dst_pin = -1
            try:
                for i, iname in enumerate(v_data['pae_node'].inputNames):
                    if iname == u:
                        dst_pin = i
                        break
            except KeyError:
                 continue 
            if dst_pin == -1: continue

            src_pos = pos[u] # PIの物理座標
            dst_pos = pos[v] # セルの物理座標
            wire = (
                src_pos[0], src_pos[1], -1, 
                int(round(dst_pos[0])), int(round(dst_pos[1])), dst_pin
            )
            current_wires.add(wire)
            mux_key = (dst_pos[0], dst_pos[1], dst_pin)
            mux_usage[mux_key] += 1

    #  2. 配線コストの計算
    for wire in current_wires:
        
        # ルール1: 配線共有ボーナス （既存配線ならばコストは０、マイナスの方がいいかもしれない要調整）
        if wire in wirestat_final_set: #(既存の配線)
            total += SHARED_BONUS
            continue   
            
        # 以下は新規配線の場合
        x1, y1, src_pin, x2, y2, dst_pin = wire
        
        # ルール2: 隣接ボーナス＆配線長コスト
        if src_pin == -1: # PI -> Cell の場合
            total += w_io
        else: # Cell -> Cell の場合
            if y2 - y1 == 1: Ce_y = -M # 隣接するセルへの入力　ボーナスを与える
            elif y2 - y1 >= 2: Ce_y = w_ff * (y2 - y1) + OmuxCost #フィードフォワード　ペナルティを与える
            else: Ce_y = w_fb * (abs(y2 - y1) + 1) + OmuxCost #フィードバック 一番重いペナルティ
            Ce_x = abs(x2 - x1) #x座標はマンハッタン距離で計算
            total += Ce_x + Ce_y 

    # ルール3:MUX溢れペナルティ
    for mux_key, count in mux_usage.items():
        if count > MUX_SIZE_LIMIT:
            total += MUX_PENALTY_WEIGHT

    return total


def simulated_annealing(G, initial_pos, PAENodes, wirestat_final_set, grid_size_x=4, grid_size_y=4, initial_temp=1000,
                        cooling_rate=0.995, iterations=100000, M=10000, w_ff=2, w_fb=10,MUX_PENALTY_WEIGHT=10000,SHARED_BONUS=-10000,
                        MUX_SIZE_LIMIT=32, OmuxCost=0, w_io=0):    
    current_pos = initial_pos.copy()
    best_pos = current_pos.copy()
    current_cost = total_cost(G, current_pos, PAENodes, wirestat_final_set, M, w_ff, w_fb, 
                              MUX_PENALTY_WEIGHT, SHARED_BONUS, MUX_SIZE_LIMIT, OmuxCost, w_io)
    best_cost = current_cost
    temp = initial_temp

    # 全ての可能な位置を生成
    all_positions = [(x, y) for x in range(grid_size_x) for y in range(grid_size_y)]
    internal_nodes = [n for n in G.nodes() if G.nodes[n].get('type') == 'internal']

    for _ in range(iterations):
        if not internal_nodes:
            break
        node_to_move = random.choice(internal_nodes) 

        #現在の位置を除外
        possible_positions = [pos for pos in all_positions if pos != current_pos[node_to_move]]
            
        # ノードを新しい位置に移動（空いている位置または他のノードと交換）
        new_pos = current_pos.copy()
        new_position = random.choice(possible_positions)
        
        # 移動先に「別の内部セル」がいないか探す
        node_at_new_position = None
        for node, pos in current_pos.items():
            if node in internal_nodes and pos == new_position:
                node_at_new_position = node
                break
        
        # 選択した位置に他のノードがある場合は交換、なければ単に移動
        if node_at_new_position:
            new_pos[node_at_new_position] = current_pos[node_to_move]
        new_pos[node_to_move] = new_position

        '''
        # 「純粋なスワップのみ」のロジック -
        possible_targets = [n for n in internal_nodes if n != node_to_move]
        if not possible_targets: continue
        node_to_swap = random.choice(possible_targets)
        new_pos = current_pos.copy()
        new_pos[node_to_move] = current_pos[node_to_swap]
        new_pos[node_to_swap] = current_pos[node_to_move]
        '''
        new_cost = total_cost(G, new_pos, PAENodes, wirestat_final_set, M, w_ff, w_fb, 
                              MUX_PENALTY_WEIGHT, SHARED_BONUS, MUX_SIZE_LIMIT, OmuxCost, w_io)
        cost_diff = new_cost - current_cost

        # 採否判定 (遷移ルール)
        if cost_diff < 0 or random.random() < math.exp(-cost_diff / temp):
            current_pos = new_pos
            current_cost = new_cost
            
            # ベスト解の更新
            if current_cost < best_cost:
                best_pos = current_pos.copy()
                best_cost = current_cost

        temp *= cooling_rate # 冷却

    return best_pos

def main():  
    # --- 1. 初期化と初期設定 ---
    wirestat_final_set = set()     #逐次学習用の「配線データベース」を初期化
    wireStats_total_usage = defaultdict(int) # wire_stats.txt用の合計使用回数

    netlist_path_pattern = 'data/netlists_500/*.net'
    all_netlist_files = glob.glob(netlist_path_pattern) # 1. リストを取得
    random.seed(6) # 2. ★ここをファイルごとに変える★ (1, 2, 3...)
    random.shuffle(all_netlist_files) # 3. シードに基づいてシャッフル
    print(f"Starting Incremental SA (Sequential Learning) run...")
    print(f"Processing netlists from: {netlist_path_pattern}")
    
    # SAパラメータ定義 
    ITERATIONS_COUNT = 100000
    COOLING_RATE = 0.995
    grid_size_x = 4
    grid_size_y = 4

    M_PARAM = 10000
    W_FF_PARAM = 2
    W_FB_PARAM = 10
    MUX_PENALTY_WEIGHT_PARAM = 0
    SHARED_BONUS_PARAM = -10
    MUX_SIZE_LIMIT_PARAM = 32
    OMUX_COST_PARAM = 0
    W_IO_PARAM = 0
    #--- 2.SAの実行 ---
    for filename in tqdm.tqdm(glob.glob(netlist_path_pattern)):
        try:
            with open(filename) as f:
                G, PAENodes = parse_circuit(f.read())
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
            continue
            
        #  pae_node 属性を G.nodes に追加 (コスト関数で参照するため) 
        for pn in PAENodes:
            if pn.name in G.nodes():
                G.nodes[pn.name]['pae_node'] = pn
                
        initial_pos = initial_placement(G, grid_size_x, grid_size_y)
            
        # SA本体に「現在の配線DB」を渡す 
        optimized_pos = simulated_annealing(
            G, initial_pos, PAENodes, wirestat_final_set,grid_size_x=grid_size_x, grid_size_y=grid_size_y,
            iterations=ITERATIONS_COUNT,cooling_rate=COOLING_RATE,
            M=M_PARAM, w_ff=W_FF_PARAM, w_fb=W_FB_PARAM, MUX_PENALTY_WEIGHT=MUX_PENALTY_WEIGHT_PARAM,
            SHARED_BONUS=SHARED_BONUS_PARAM,MUX_SIZE_LIMIT=MUX_SIZE_LIMIT_PARAM,OmuxCost=OMUX_COST_PARAM,w_io=W_IO_PARAM
        )

        # SAが使った「最終的な配線」を取得 
        final_wires_for_this_netlist = get_wires(PAENodes, optimized_pos, G)

        # 「配線データベース」に新しい配線を追加 
        new_wires_added_count = 0
        for wire in final_wires_for_this_netlist:
            if wire not in wirestat_final_set:
                wirestat_final_set.add(wire)
                new_wires_added_count += 1
                
        if new_wires_added_count > 0:
            print(f"  -> Added {new_wires_added_count} new wires to wirestat_final_set.")

        # 統計収集
        # (フィードバック数の計算)
        feedback_count = 0
        internal_nodes = {n for n in G.nodes() if G.nodes[n].get('type') == 'internal'}
        for u, v in G.edges():
            if u in internal_nodes and v in internal_nodes and u in optimized_pos and v in optimized_pos: 
                if optimized_pos[u][1] > optimized_pos[v][1]:
                    feedback_count += 1

        # (グラフ解析用の個別ファイル書き出し)
        output_dir = "individual_wire_results"
        os.makedirs(output_dir, exist_ok=True)
        base_filename = os.path.basename(filename).replace(".net", "")
        output_path = os.path.join(output_dir, f"wires_{base_filename}.txt")
        try:
            with open(output_path, "w") as f_out:
                for wire_tuple in final_wires_for_this_netlist:
                    f_out.write(" ".join(map(str, wire_tuple)) + "\n")
        except IOError as e:
            print(f"Error writing individual wire file for {base_filename}: {e}")

        # (wire_stats.txt用の合計使用回数を集計)
        compute_wireStats(final_wires_for_this_netlist, wireStats_total_usage)

    # --- 3. 最終的な統計ファイルの書き出し ---
    sortedWireStats = dict(sorted(wireStats_total_usage.items(), key=lambda item: item[1], reverse=True))
    print(f"\nTotal {len(sortedWireStats)} unique wires used (sum). Saving to wire_stats.txt...")
    with open("wire_stats.txt", "w") as f:
        for wire_tuple, count in sortedWireStats.items():
            f.write(f"{' '.join(map(str, wire_tuple))} {count}\n")

    # --- 4. 最終アーキテクチャの構成メモリ評価 ---
    print("\nAnalyzing final architecture configuration memory...")
    
    mux_internal_inputs = defaultdict(int)
    mux_external_inputs = defaultdict(int)
    final_feedback_count = 0 # 最終フィードバック数をカウントする変数
    
    for wire in wirestat_final_set:
        src_x, src_y, src_pin, dst_x, dst_y, dst_pin = wire
        mux_key = (dst_x, dst_y, dst_pin) # 宛先のMUX
        
        if src_y < 0 or src_pin == -1: # 外部入力(PI)からの配線
            mux_external_inputs[mux_key] += 1
        else: # 内部セルからの配線
            mux_internal_inputs[mux_key] += 1
            
            # 内部配線の場合のみフィードバックかチェック
            if src_y > dst_y:
                final_feedback_count += 1

    total_conf_bits = 0
    all_mux_keys = set(mux_internal_inputs.keys()) | set(mux_external_inputs.keys())
    
    report_lines = []
    report_lines.append("========================================================")
    report_lines.append(f"--- Configuration Memory Analysis ---")
    report_lines.append("========================================================")
    report_lines.append(f"[Execution Parameters]")
    report_lines.append(f"  Iterations:       {ITERATIONS_COUNT}")
    report_lines.append(f"  Cooling Rate:     {COOLING_RATE}")
    report_lines.append(f"  Grid Size:        {grid_size_x} x {grid_size_y}")
    report_lines.append(f"")
    report_lines.append(f"[Cost Function Weights]")
    report_lines.append(f"  Shared Bonus:     {SHARED_BONUS_PARAM} (Rule 3)")
    report_lines.append(f"  Adjacency Bonus:  {M_PARAM} (Rule 1: -M)")
    report_lines.append(f"  Skip Penalty:     {W_FF_PARAM} (w_ff)")
    report_lines.append(f"  Feedback Penalty: {W_FB_PARAM} (w_fb)")
    report_lines.append(f"  MUX Penalty:      {MUX_PENALTY_WEIGHT_PARAM} (Limit: {MUX_SIZE_LIMIT_PARAM})")
    report_lines.append(f"  New PI Penalty:   {W_IO_PARAM} (w_io)")
    report_lines.append("========================================================")
    report_lines.append(f"")
    report_lines.append(f"--- Configuration Memory Analysis (based on {len(wirestat_final_set)} unique wires) ---")
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

    mux_stats.sort(key=lambda x: x[1], reverse=True)

    for stat in mux_stats[:20]: # 上位20件だけ表示
        key_str = f"({stat[0][0]}, {stat[0][1]}, {stat[0][2]})"
        line = f"{key_str:<25} | {stat[1]:<12} | {stat[2]:<10} | {stat[3]:<10} | {stat[4]}"
        report_lines.append(line)
        
    report_lines.append("...")
    
    #  最終フィードバック数をレポートに追加
    report_lines.append(f"\nTotal Feedback Wires in Final Architecture: {final_feedback_count}")
    report_lines.append(f"Total Configuration Bits (All MUXes): {total_conf_bits}")

    # レポートをファイルとコンソールに出力
    cost_report_file = "final_architecture_cost6.txt"
    print(f"\nSaving configuration memory analysis to '{cost_report_file}'...")
    with open(cost_report_file, "w") as f:
        for line in report_lines:
            print(line)
            f.write(line + "\n")

    print("SA_out6.py run complete.")

    '''
    ######描画したいときはコメントアウト外す(500個全部描画するので滅茶苦茶遅い)
    def create_plot(G, pos, grid_size_x=4, grid_size_y=4):
        plt.figure(figsize=(12, 12))
        for i in range(grid_size_x + 1):
            plt.axvline(x=i - 0.5, color='gray', linestyle='--', alpha=0.5)
        for i in range(grid_size_y + 1):
            plt.axhline(y=i - 0.5, color='gray', linestyle='--', alpha=0.5)
        internal_nodes = [n for n in G.nodes() if not G.nodes[n].get('is_io', False)]
        io_nodes = [n for n in G.nodes() if G.nodes[n].get('is_io', True)]
    
        drawable_internal = [n for n in internal_nodes if n in pos]
        drawable_io = [n for n in io_nodes if n in pos] 
    
        nx.draw_networkx_nodes(G, pos, nodelist=drawable_internal, node_size=500, node_color='lightblue')
        nx.draw_networkx_nodes(G, pos, nodelist=drawable_io, node_size=500, node_color='lightgreen')
        nx.draw_networkx_labels(G, pos, font_size=8)
    
        for u, v in G.edges():
            if u not in pos or v not in pos: continue # 配置されてないノードは描画しない
            u_data = G.nodes[u]; v_data = G.nodes[v]
            y1, y2 = pos[u][1], pos[v][1]
            edge_color = 'black'
            if u_data.get('type') == 'input': edge_color = 'blue'
            elif v_data.get('type') == 'output': edge_color = 'red'
            elif y1 > y2: edge_color = 'orange'
            start, end = pos[u], pos[v]
            plt.arrow(start[0], start[1], end[0] - start[0], end[1] - start[1], 
                      shape='full', lw=1, length_includes_head=True, head_width=0.2, color=edge_color)
        plt.title("Place and Route"); plt.xlim(-1.5, grid_size_x + 0.5); plt.ylim(-1.5, grid_size_y + 0.5)
        plt.gca().invert_yaxis(); plt.axis('off'); plt.tight_layout()

    def save_fpga(G, pos, grid_size_x=4, grid_size_y=4, filename='place_and_route.png'):#画像保存
        create_plot(G, pos, grid_size_x, grid_size_y)
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close() 
    '''

if __name__ == '__main__':
    main()