import argparse
import graphviz
import math

# pea.pyからWireStatとWireStatsクラスを流用
class WireStat:
    """wire_stats.txtの1行分のデータを保持するクラス"""
    def __init__(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum, count):
        self.src_x = src_x
        self.src_y = src_y
        self.src_outnum = src_outnum
        self.dst_x = dst_x
        self.dst_y = dst_y
        self.dst_innum = dst_innum
        self.count = count

class WireStats:
    """wire_stats.txtを読み込み、閾値でフィルタリングするクラス"""
    def __init__(self, filename, count=1):
        self.stats = []
        self.readFromFile(filename, count)

    def readFromFile(self, filename, count):
        numTargetWires = 0
        try:
            with open(filename) as f:
                for line in f:
                    try:
                        parts = [int(s) for s in line.split()]
                        if len(parts) != 7:
                            continue
                        wire_count = parts[6]
                        if wire_count >= count:
                            numTargetWires += 1
                            ws = WireStat(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], wire_count)
                            self.stats.append(ws)
                    except (ValueError, IndexError):
                        continue
        except FileNotFoundError:
            print(f"エラー: wire_stats.txtファイル '{filename}' が見つかりません。")
            exit(1)
        print(f"閾値 {count} 以上の配線を {numTargetWires} 本読み込みました。")

def visualize_wire_stats(wire_stats_file, threshold, output_filename):
    """
    WireStatsを読み込んでGraphvizで可視化する関数
    """
    # 1. データの読み込みとフィルタリング
    stats = WireStats(wire_stats_file, count=threshold)

    # 2. Graphvizオブジェクトの作成
    dot = graphviz.Digraph('WireStats', comment='Internal Wiring based on Statistics')
    dot.attr('graph', rankdir='LR', splines='ortho', nodesep='0.8', ranksep='2.0 equally', label=f'Wiring Structure (Threshold >= {threshold})', fontsize='20')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#E3F2FD') # 水色

    # 3. ノードとサブグラフ（レーン）の定義
    lanes = {}  # key: y座標, value: set of x座標
    for ws in stats.stats:
        # 存在するレーンとPAEセルの座標を収集
        for y, x in [(ws.src_y, ws.src_x), (ws.dst_y, ws.dst_x)]:
            if y not in lanes:
                lanes[y] = set()
            lanes[y].add(x)

    # レーンごとにサブグラフを作成し、PAEセル（ノード）を追加
    for y in sorted(lanes.keys()):
        with dot.subgraph(name=f'cluster_lane_{y}') as c:
            c.attr(label=f'Lane {y}', style='rounded', color='gray', fontsize='16')
            # x座標でソートしてノードを追加することで、グラフ内での並び順を固定
            for x in sorted(list(lanes[y])):
                c.node(f'PAE_{y}_{x}', label=f'PAE\n({x}, {y})')

    # 4. エッジ（配線）の作成
    for ws in stats.stats:
        src_node = f'PAE_{ws.src_y}_{ws.src_x}'
        dst_node = f'PAE_{ws.dst_y}_{ws.dst_x}'
        
        # 配線の頻度(count)に応じて線の太さを変える
        # math.logを使うことで、count値の差が大きくても見やすい範囲に収める
        penwidth = max(0.5, math.log(ws.count + 1, 2))

        # 配線の種類で色分け
        color = '#424242' # デフォルト (レーン間)
        if ws.src_y == ws.dst_y:
            color = '#1565C0' # 青 (レーン内)
        elif ws.src_y > ws.dst_y:
            color = '#C62828' # 赤 (フィードバック)

        dot.edge(src_node, dst_node, 
                 label=f' c:{ws.count}', # count
                 color=color, 
                 penwidth=str(penwidth),
                 fontsize='10',
                 fontcolor='#555555')

    # 5. ファイルへ保存
    try:
        print(f"グラフを '{output_filename}.png' に保存します...")
        dot.render(output_filename, format='png', view=True, cleanup=True)
        print("完了しました。")
    except graphviz.backend.execute.ExecutableNotFound:
        print("\nエラー: Graphvizの実行ファイルが見つかりません。")
        print("PATHが通っているか、または正しくインストールされているか確認してください。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Wire statistics visualizer.')
    parser.add_argument('file', default='wire_stats.txt', nargs='?', help='配線統計ファイル名 (デフォルト: wire_stats.txt)')
    parser.add_argument('--ws_count', type=int, default=1, help='表示する配線の最低出現回数 (閾値)')
    parser.add_argument('--output', default='wire_structure', help='出力ファイル名 (拡張子なし)')
    args = parser.parse_args()

    visualize_wire_stats(args.file, args.ws_count, args.output)