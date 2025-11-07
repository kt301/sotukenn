import networkx as nx
import glob
import matplotlib.pyplot as plt
from networkx.drawing.nx_agraph import graphviz_layout
from yggdrasill.utils import parse_circuit

filename = 'mux4.net'
#filename = 'subtractor_4bit.net'

with open(f'data/netlists/{filename}') as f:
    G = parse_circuit(f.read())

   # グラフの描画
    plt.figure(figsize=(12, 8))
    pos = graphviz_layout(G, prog='dot')
    
    # ノードの色を設定
    color_map = []
    for node in G:
        if node == 'inputs':
            color_map.append('lightgreen')
        elif node == 'outputs':
            color_map.append('lightblue')
        else:
            color_map.append('lightgray')

    nx.draw(G, pos, with_labels=True, node_color=color_map, node_size=3000, font_size=8, font_weight='bold', arrows=True)
    
    # エッジラベルを追加
    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6)

    plt.title("Circuit Graph")
    plt.axis('off')
    plt.tight_layout()
    plt.show()

exit()    

for i in glob.glob('data/netlists/*.net'):
    with open(i) as f:
        parse_circuit(f.read())
        