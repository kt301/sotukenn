import networkx as nx

class PAENode:
    def __init__(self, name, inputs, outputs):
        self.name = name
        self.inputNames = inputs
        self.outputNames = outputs
        
def parse_circuit(circuit_description: str):
    
    G = nx.DiGraph()
    PAENodes = []
    
    # 空白行を除外し、各行の先頭と末尾の空白を削除
    lines = [line.strip() for line in circuit_description.strip().split('\n') if line.strip()]

    # ヘッダ情報のパース
    max_input_num = int(lines[0].split()[1])
    max_output_num = int(lines[1].split()[1])
    input_port_names = lines[2].split()[1:]
    output_port_names = lines[3].split()[1:]

    # PAE (内部) ノードの情報を先に収集
    pae_lines = lines[4:]
    internal_node_names = [line.split()[1] for line in pae_lines]

    # --- 1. 全てのノードを属性付きでグラフに追加 ---
    # 外部入力ノード
    for name in input_port_names:
        G.add_node(name, is_io=True, type='input')
    
    # 外部出力ノード
    for name in output_port_names:
        G.add_node(name, is_io=True, type='output')

    # 内部ノード
    for name in internal_node_names:
        G.add_node(name, is_io=False, type='internal')

    # --- 2. 信号のソース(源)を特定するためのマップを作成 ---
    signal_source_map = {}
    
    # 外部入力ポート自身が信号のソース
    for name in input_port_names:
        signal_source_map[name] = name

    # PAEノードの出力をパースして、信号のソースをマップに追加
    for line in pae_lines:
        parts = line.split()
        node_name = parts[1]
        
        # 'nc' (not connected) を除外する
        node_inputs = [inp for inp in parts[2: 2 + max_input_num] if inp != 'nc']
        node_outputs = [out for out in parts[2 + max_input_num: 2 + max_input_num + max_output_num] if out != 'nc']

        # PAENodeオブジェクトの作成
        PAENodes.append(PAENode(node_name, node_inputs, node_outputs))
        
        # このPAEノードが出力する信号をマップに登録
        for out_signal in node_outputs:
            signal_source_map[out_signal] = node_name

    # --- 3. マップを使ってエッジ(配線)を構築 ---
    # 内部ノードへの接続
    for pn in PAENodes:
        destination_node = pn.name
        for in_signal in pn.inputNames:
            source_node = signal_source_map.get(in_signal)
            if source_node:
                G.add_edge(source_node, destination_node, label=in_signal)

    # 外部出力ポートへの接続
    for out_port in output_port_names:
        source_node = signal_source_map.get(out_port)
        if source_node:
            G.add_edge(source_node, out_port, label=out_port)

    return G, PAENodes

    
'''        
def parse_circuit(circuit_description:str) -> nx.DiGraph:

    PAENodes = []
    
    edges = {}

    lines = circuit_description.strip().split('\n')
    lines = list(filter(lambda x: len(x) > 0, map(lambda x: x.strip(), lines)))

    max_input_num = int(lines[0].split()[1])
    max_output_num = int(lines[1].split()[1])

    inputs = lines[2].split()[1:]
    outputs = lines[3].split()[1:]
    
    for inp in inputs:
        edges[inp] = ('inputs', [])
    for out in outputs:
        edges[out] = (None, ['outputs'])
    
    for line in lines[4:]:
        parts = line.split()
        node_name = parts[1]
        node_inputs = parts[2: 2 + max_input_num]
        node_outputs = parts[2 + max_input_num: 2 + max_input_num + max_output_num]


        pn = PAENode(node_name, node_inputs, node_outputs) # added
        PAENodes.append(pn)
        

        for inp in filter(lambda x: x != 'nc', node_inputs):
            if edges.get(inp) is None:
                edges[inp] = (None, [node_name])
            else:
                edges[inp][1].append(node_name)

        for out in filter(lambda x: x != 'nc', node_outputs):
            if edges.get(out) is None:
                edges[out] = (node_name, [])
            else:
                edges[out]= (node_name, edges[out][1])


    # 本来ならこれは必要ないはず
    edges = {k: v for k, v in edges.items() if v[0] is not None and len(v[1]) > 0}

    # グラフの作成
    G = nx.DiGraph()
    nodes = set()
    
    for k, v in edges.items():
        nodes.add(v[0])
        nodes.update(v[1])

    for node in nodes:
        G.add_node(node)
    
    for k, v in edges.items():
        for out in v[1]:
            G.add_edge(v[0], out, label=k)

    return G, PAENodes
'''