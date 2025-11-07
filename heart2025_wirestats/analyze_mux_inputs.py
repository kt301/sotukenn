import argparse
import math
from collections import Counter

# ==================================================================
# pea.pyから抜粋したクラス定義
# ==================================================================

class WireStat:
    def __init__(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum, count):
        self.src_x = src_x
        self.src_y = src_y
        self.src_outnum = src_outnum
        self.dst_x = dst_x
        self.dst_y = dst_y
        self.dst_innum = dst_innum
        self.count = count

class WireStats:
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
            print(f"Error: Statistics file '{filename}' not found.")
        print(f"numTargetWires={numTargetWires}")

class PI:
    count = 0
    def __init__(self):
        self.count = PI.count
        PI.count += 1
        self.name = f"I{self.count}"
        self.dsts = []

class IMUX:
    def __init__(self, paecell, inputNum):
        self.inputs = []
        self.paecell = paecell
        self.inputNum = inputNum
        self.name = f"IMUX{self.inputNum}_PAE{self.paecell.count}_lane{self.paecell.lane.count}"

class OMUX:
    count = 0
    def __init__(self, lane, skipLengths=None):
        self.count = OMUX.count
        OMUX.count += 1
        self.lane = lane
        self.inputs = []
        self.dsts = []
        self.skipLengths = skipLengths
        self.name = f"OMUX{self.count}_lane{self.lane.count}"

class PAEOutput:
    def __init__(self, paecell, outputNum):
        self.paecell = paecell
        self.outputNum = outputNum
        self.dsts = []
        self.name = f"OutPort{self.outputNum}_PAE{self.paecell.count}_lane{self.paecell.lane.count}"

class PAECell:
    count = 0
    def __init__(self, lane, nPAEin=4, nPAEout=3):
        self.count = PAECell.count
        PAECell.count += 1
        self.lane = lane
        self.IMUXes = []
        self.outputs = []
        for i in range(nPAEin):
            self.IMUXes.append(IMUX(self, i))
        for i in range(nPAEout):
            self.outputs.append(PAEOutput(self, i))
        self.name = f"PAE{self.count}_lane{self.lane.count}"

class Lane:
    count = 0
    def __init__(self, nPAECells=4, nPAEout=3, nOMUXes=12, skips=None, nSkipOMUXes=0):
        self.count = Lane.count
        Lane.count += 1
        self.PAECells = []
        self.OMUXes = []
        self.skipOMUXes = []
        self.skips = skips
        for _ in range(nPAECells):
            self.PAECells.append(PAECell(self, nPAEout=nPAEout))
        for _ in range(nOMUXes):
            self.OMUXes.append(OMUX(self))
        for _ in range(nSkipOMUXes):
            self.skipOMUXes.append(OMUX(self, skipLengths=skips))
        self.connectPAEOutputToOMUX()
        if skips is not None:
            self.connectPAEOutputToSkipOMUX()

    def connectPAEOutputToOMUX(self):
        outputs = [o for p in self.PAECells for o in p.outputs]
        for i, omux in enumerate(self.OMUXes):
            if i < len(outputs):
                omux.inputs.append(outputs[i])
                outputs[i].dsts.append(omux)

    def connectPAEOutputToSkipOMUX(self):
        outputs = [o for p in self.PAECells for o in p.outputs]
        for omux in self.skipOMUXes:
            omux.inputs.extend(outputs)
            for o in outputs:
                o.dsts.append(omux)

    def connectSkips(self, lanes):
        for m in self.skipOMUXes:
            for l in m.skipLengths:
                target_lane_idx = self.count + l
                if 0 <= target_lane_idx < len(lanes):
                    dstLane = lanes[target_lane_idx]
                    for p in dstLane.PAECells:
                        for im in p.IMUXes:
                            im.inputs.append(m)
                            m.dsts.append(im)

class PEALogic:
    def __init__(self, numPIs=36):
        self.lanes = []
        self.PIs = [PI() for _ in range(numPIs)]
        self.IMUXes = []
        self.PAECells = []

    def addLane(self, lane):
        self.lanes.append(lane)

    def connectPAEs(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum):
        if not (0 <= src_y < len(self.lanes) and 0 <= dst_y < len(self.lanes)): return
        if not (0 <= src_x < len(self.lanes[src_y].PAECells) and 0 <= dst_x < len(self.lanes[dst_y].PAECells)): return

        srcPAE = self.lanes[src_y].PAECells[src_x]
        dstPAE = self.lanes[dst_y].PAECells[dst_x]
        imux = dstPAE.IMUXes[dst_innum]
        
        omux = next((dst for dst in srcPAE.outputs[src_outnum].dsts if isinstance(dst, OMUX) and dst.skipLengths is None), None)
        
        if omux:
            imux.inputs.append(omux)
            omux.dsts.append(imux)

    def collect_components(self):
        """LanesからIMUXとPAECellを収集する"""
        self.IMUXes = [imux for lane in self.lanes for pc in lane.PAECells for imux in pc.IMUXes]
        self.PAECells = [pc for lane in self.lanes for pc in lane.PAECells]

# ==================================================================
# 分析と結果表示のためのメイン処理
# ==================================================================

def main():
    parser = argparse.ArgumentParser(description='Analyze internal wire connections to IMUXes.')
    parser.add_argument('--ws_count', type=int, default=1, help='Minimum wire count from wire_stats.txt')
    args = parser.parse_args()

    print(f"Analyzing architecture with ws_count = {args.ws_count}")

    # 1. pea.py と同じ構成でアーキテクチャを構築
    pl = PEALogic(numPIs=36)
    pl.addLane(Lane(nPAECells=4, nOMUXes=12, nSkipOMUXes=0, nPAEout=3))
    pl.addLane(Lane(nPAECells=4, nOMUXes=12, nSkipOMUXes=0, nPAEout=3))
    pl.addLane(Lane(nPAECells=4, nOMUXes=12, nSkipOMUXes=0, nPAEout=3))
    pl.addLane(Lane(nPAECells=4, nOMUXes=12, nSkipOMUXes=0, nPAEout=3))

    #for lane in pl.lanes:
    #    lane.connectSkips(pl.lanes)

    wirestats = WireStats("wire_stats.txt", args.ws_count)
    for ws in wirestats.stats:
        pl.connectPAEs(ws.src_x, ws.src_y, ws.src_outnum, ws.dst_x, ws.dst_y, ws.dst_innum)

    # LaneオブジェクトからIMUXのリストを収集
    pl.collect_components()

    # 2. 各IMUXへの内部配線数をカウント
    imux_internal_counts = []
    for imux in pl.IMUXes:
        internal_wire_count = 0
        for source in imux.inputs:
            # 入力がOMUX経由であれば内部配線とみなす
            if isinstance(source, OMUX):
                internal_wire_count += 1
        imux_internal_counts.append(internal_wire_count)

    # 3. 結果を集計して表示
    if not imux_internal_counts:
        print("No IMUXes found or no internal connections made.")
        return

    histogram = Counter(imux_internal_counts)
    
    output_filename = f"mux_stats_ws{args.ws_count}.txt"
    print(f"\n--- MUX Internal Input Statistics (ws_count = {args.ws_count}) ---")
    print(f"Saving results to {output_filename}")

    with open(output_filename, "w") as f:
        f.write(f"--- MUX Internal Input Statistics (ws_count = {args.ws_count}) ---\n")
        f.write(f"Total IMUXes analyzed: {len(imux_internal_counts)}\n\n")
        
        header = "Input Count | Number of MUXes\n"
        separator = "-----------------------------\n"
        f.write(header)
        f.write(separator)
        
        # コンソールにも表示
        print(f"Total IMUXes analyzed: {len(imux_internal_counts)}\n")
        print(header, end="")
        print(separator, end="")

        for count, num_muxes in sorted(histogram.items()):
            line = f"     {count:<6} | {num_muxes}\n"
            f.write(line)
            print(line, end="")

        avg_inputs = sum(imux_internal_counts) / len(imux_internal_counts)
        max_inputs = max(imux_internal_counts)
        
        f.write(separator)
        f.write(f"Average internal inputs per MUX: {avg_inputs:.2f}\n")
        f.write(f"Max internal inputs to a single MUX: {max_inputs}\n")

        print(separator, end="")
        print(f"Average internal inputs per MUX: {avg_inputs:.2f}")
        print(f"Max internal inputs to a single MUX: {max_inputs}")

if __name__ == '__main__':
    main()