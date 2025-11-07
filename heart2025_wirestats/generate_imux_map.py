import argparse
import math
from collections import Counter

# (pea.pyから抜粋したクラス定義 - analyze_mux_inputs.py と同じなので省略)
# (もし手元で動かす際にクラス定義が必要な場合は、前回の回答からコピーしてください)
# 以下に、必要なクラス定義を再度含めておきます。

# ==================================================================
# pea.pyから抜粋したクラス定義
# ==================================================================

class WireStat:
    def __init__(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum, count):
        self.src_x, self.src_y, self.src_outnum = src_x, src_y, src_outnum
        self.dst_x, self.dst_y, self.dst_innum = dst_x, dst_y, dst_innum
        self.count = count

class WireStats:
    def __init__(self, filename, count=1):
        self.stats = []
        self.readFromFile(filename, count)

    def readFromFile(self, filename, count):
        try:
            with open(filename) as f:
                for line in f:
                    try:
                        parts = [int(s) for s in line.split()]
                        if len(parts) == 7 and parts[6] >= count:
                            self.stats.append(WireStat(*parts))
                    except (ValueError, IndexError):
                        continue
        except FileNotFoundError:
            print(f"Error: Statistics file '{filename}' not found.")
        print(f"Loaded {len(self.stats)} wires with count >= {count}")

class PI:
    count = 0
    def __init__(self):
        self.count = PI.count; PI.count += 1
        self.name = f"I{self.count}"
        self.dsts = []

class IMUX:
    def __init__(self, paecell, inputNum):
        self.inputs = []; self.paecell = paecell; self.inputNum = inputNum
        self.name = f"IMUX{self.inputNum}_PAE{self.paecell.count}_lane{self.paecell.lane.count}"

class OMUX:
    count = 0
    def __init__(self, lane, skipLengths=None):
        self.count = OMUX.count; OMUX.count += 1
        self.lane = lane; self.inputs = []; self.dsts = []; self.skipLengths = skipLengths
        self.name = f"OMUX{self.count}_lane{self.lane.count}"

class PAEOutput:
    def __init__(self, paecell, outputNum):
        self.paecell = paecell; self.outputNum = outputNum; self.dsts = []
        self.name = f"OutPort{self.outputNum}_PAE{self.paecell.count}_lane{self.paecell.lane.count}"

class PAECell:
    count = 0
    def __init__(self, lane, nPAEin=4, nPAEout=3):
        self.count = PAECell.count; PAECell.count += 1
        self.lane = lane; self.IMUXes = []; self.outputs = []
        for i in range(nPAEin): self.IMUXes.append(IMUX(self, i))
        for i in range(nPAEout): self.outputs.append(PAEOutput(self, i))
        self.name = f"PAE{self.count}_lane{self.lane.count}"

class Lane:
    count = 0
    def __init__(self, nPAECells=4, nPAEout=3, nOMUXes=12, nSkipOMUXes=0, skips=None):
        self.count = Lane.count; Lane.count += 1
        self.PAECells = []; self.OMUXes = []; self.skipOMUXes = []
        for _ in range(nPAECells): self.PAECells.append(PAECell(self, nPAEout=nPAEout))
        for _ in range(nOMUXes): self.OMUXes.append(OMUX(self))
        self.connectPAEOutputToOMUX()

    def connectPAEOutputToOMUX(self):
        outputs = [o for p in self.PAECells for o in p.outputs]
        for i, omux in enumerate(self.OMUXes):
            if i < len(outputs):
                omux.inputs.append(outputs[i]); outputs[i].dsts.append(omux)

class PEALogic:
    def __init__(self, numPIs=36):
        self.lanes = []; self.PIs = [PI() for _ in range(numPIs)]
        self.IMUXes = []; self.PAECells = []
    def addLane(self, lane): self.lanes.append(lane)
    def connectPAEs(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum):
        if not (0 <= src_y < len(self.lanes) and 0 <= dst_y < len(self.lanes)): return
        srcPAE = self.lanes[src_y].PAECells[src_x]
        dstPAE = self.lanes[dst_y].PAECells[dst_x]
        omux = next((d for d in srcPAE.outputs[src_outnum].dsts if isinstance(d, OMUX)), None)
        if omux: dstPAE.IMUXes[dst_innum].inputs.append(omux); omux.dsts.append(dstPAE.IMUXes[dst_innum])
    def collect_components(self):
        self.IMUXes = [imux for l in self.lanes for pc in l.PAECells for imux in pc.IMUXes]

# ==================================================================
# 新しい分析とマップファイル生成のメイン処理
# ==================================================================

def main():
    parser = argparse.ArgumentParser(description='Generate a detailed map of internal wire connections to IMUXes.')
    parser.add_argument('--ws_count', type=int, default=1, help='Minimum wire count from wire_stats.txt')
    args = parser.parse_args()

    print(f"Generating IMUX map for ws_count = {args.ws_count}")

    # 1. pea.py と同じ構成でアーキテクチャを構築 (スキップ接続なし)
    pl = PEALogic(numPIs=36)
    for _ in range(4): # 4レーン作成
        pl.addLane(Lane(nPAECells=4, nOMUXes=12, nSkipOMUXes=0, nPAEout=3))

    wirestats = WireStats("wire_stats.txt", args.ws_count)
    for ws in wirestats.stats:
        pl.connectPAEs(ws.src_x, ws.src_y, ws.src_outnum, ws.dst_x, ws.dst_y, ws.dst_innum)

    pl.collect_components()

    # 2. 各IMUXへの内部配線数を記録し、ファイルに出力
    output_filename = f"imux_usage_map_ws{args.ws_count}.csv"
    print(f"Saving detailed map to {output_filename} ...")

    with open(output_filename, "w") as f:
        f.write("imux_name,internal_inputs\n") # ヘッダー行
        for imux in pl.IMUXes:
            internal_wire_count = sum(1 for source in imux.inputs if isinstance(source, OMUX))
            f.write(f"{imux.name},{internal_wire_count}\n")

    print("Done.")

if __name__ == '__main__':
    # クラスのカウンタをリセット
    PI.count = 0; OMUX.count = 0; PAECell.count = 0; Lane.count = 0
    main()