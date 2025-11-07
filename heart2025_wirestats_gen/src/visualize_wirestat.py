import matplotlib.pyplot as plt
import os
from collections import defaultdict

# --- 設定項目 ---
GRID_SIZE_X = 4
GRID_SIZE_Y = 4
INPUT_FILE = "wirestat_final.txt" # SA_out.pyが出力する最終的な配線セット
OUTPUT_IMAGE = "wirestat_map.png"
# ---

def draw_grid(ax, grid_x, grid_y):
    """グリッド線とセル（ノード）を描画する"""
    # グリッド線
    for i in range(grid_x + 1):
        ax.axvline(x=i - 0.5, color='gray', linestyle='--', alpha=0.5, zorder=1)
    for i in range(grid_y + 1):
        ax.axhline(y=i - 0.5, color='gray', linestyle='--', alpha=0.5, zorder=1)
        
    # セルを描画
    nodes_pos = {}
    for y in range(grid_y):
        for x in range(grid_x):
            nodes_pos[f"({x},{y})"] = (x, y)
            
    # networkxを使わずに円を描画
    for (x, y) in nodes_pos.values():
        ax.add_patch(plt.Circle((x, y), 0.3, color='lightblue', zorder=2))
        ax.text(x, y, f"({x},{y})", ha='center', va='center', fontsize=8)

def main():
    print(f"Loading '{INPUT_FILE}' to generate visualization...")
    
    # 1. wirestat_final.txt を読み込み、セル間の接続本数を集計
    # キー: ((src_x, src_y), (dst_x, dst_y)), 値: 本数(count)
    link_counts = defaultdict(int)
    
    if not os.path.exists(INPUT_FILE):
        print(f"Error: '{INPUT_FILE}' not found. Please run SA_out.py first.")
        return

    with open(INPUT_FILE, 'r') as f:
        for line in f:
            if line.startswith("#"): continue # コメント行をスキップ
            
            try:
                parts = line.strip().split()
                if len(parts) == 6: # PI->Cell の配線 (例: 0.18 -1 -1 0 0 2)
                    # PIからの配線は、今は集計対象外とする (主にセル間が見たいため)
                    # (もしPIも見たい場合は、ここのロジックを変更)
                    if float(parts[1]) < 0: 
                        continue
                elif len(parts) == 7: # sa.pyのwire_stats.txt形式(回数付き)の場合
                    # (このスクリプトはwirestat_final.txt用だが、念のため)
                    parts = parts[:6] 
                else:
                    continue # 不正な行
                
                # parts[0]...[5] は (src_x, src_y, src_pin, dst_x, dst_y, dst_pin)
                src_x, src_y = int(parts[0]), int(parts[1])
                dst_x, dst_y = int(parts[3]), int(parts[4])
                
                # セル間の接続キーを作成
                link_key = ((src_x, src_y), (dst_x, dst_y))
                link_counts[link_key] += 1
                
            except (ValueError, IndexError):
                continue

    if not link_counts:
        print("No valid internal wires found in the file.")
        return

    # 2. Matplotlibで描画
    fig, ax = plt.subplots(figsize=(15, 15))
    draw_grid(ax, GRID_SIZE_X, GRID_SIZE_Y)

    print(f"Drawing {len(link_counts)} unique cell-to-cell links...")

    # 3. 集計したリンク（配線）を矢印として描画
    for (src, dst), count in link_counts.items():
        src_x, src_y = src
        dst_x, dst_y = dst
        
        # 線の太さを本数(count)に応じて変える
        linewidth = 0.5 + (count * 0.5)
        
        # 矢印の色を方向で変える
        color = 'black'
        if src_y > dst_y:
            color = 'orange' # フィードバック (逆流)
        elif src_y == dst_y and src_x != dst_x:
            color = 'purple' # 水平
            
        # 矢印を描画
        ax.annotate("",
                    xy=(dst_x, dst_y), xycoords='data',
                    xytext=(src_x, src_y), textcoords='data',
                    arrowprops=dict(arrowstyle="->",
                                    shrinkA=5, shrinkB=5, # ノードの円を避ける
                                    lw=linewidth,
                                    color=color,
                                    alpha=0.6,
                                    zorder=3))
        
        # 本数のラベルを配線の中間に表示
        mid_x = (src_x + dst_x) / 2
        mid_y = (src_y + dst_y) / 2
        # 少しだけずらして矢印と被らないようにする
        ax.text(mid_x + 0.1, mid_y + 0.1, str(count), 
                color='red', fontsize=10, weight='bold', zorder=4)

    # 4. グラフの見た目を調整
    ax.set_title(f"Wire Resource Map (from {INPUT_FILE})\nThicker lines = More pin-to-pin connections")
    ax.set_xlim(-1.5, GRID_SIZE_X + 0.5)
    ax.set_ylim(-1.5, GRID_SIZE_Y + 0.5)
    ax.invert_yaxis() # (0,0)を左上にする
    ax.set_aspect('equal') # アスペクト比を1:1に
    ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_IMAGE, dpi=300)
    print(f"Map saved to '{OUTPUT_IMAGE}'")

if __name__ == "__main__":
    main()