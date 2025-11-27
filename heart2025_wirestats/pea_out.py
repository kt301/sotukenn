import itertools
import argparse
import subprocess
import math
import glob
import graphviz
import GraphLegends as GL
import re
import sys
import os 
from collections import defaultdict 

# ------------------------------------------------------------------
# WireStats読み込みパート
# ------------------------------------------------------------------
class WireStat:
    def __init__(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum, count=1):
        self.src_x = src_x
        self.src_y = src_y
        self.src_outnum = src_outnum # PIの場合は-1が入る想定
        self.dst_x = dst_x
        self.dst_y = dst_y
        self.dst_innum = dst_innum   # PAE入力ピン
        self.count = count           # ファイルにはないためデフォルト1

class WireStats: 
    def __init__(self, filename):
        self.stats = []
        self.readFromFile(filename)
    
    def readFromFile(self, filename): 
        numTargetWires = 0
        print(f"Loading architecture structure from {filename}...")
        try:
            with open(filename, 'r') as f:
                for line in f:
                    # コメントと空行の処理
                    if line.startswith("#") or not line.strip(): 
                        continue
                    
                    try:
                        parts = [int(s) for s in line.split()]
                        
                        # 6要素のみを対象とする
                        if len(parts) == 6:
                            # 引数: src_x, src_y, src_outnum, dst_x, dst_y, dst_innum, (count=1)
                            ws = WireStat(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], 1)
                            self.stats.append(ws)
                            numTargetWires += 1
                        
                    except (ValueError, IndexError):
                        continue
                        
        except FileNotFoundError:
            print(f"Error: Statistics file '{filename}' not found.")
            exit(1)

        print(f"numTargetWires={numTargetWires} (Loaded from file)")



'''
 部品の定義
'''
class PI: # PEA論理(レーンの集合)への外部入力
    count = 0    
    def __init__(self):
        self.count = PI.count  # PIのID番号
        PI.count += 1        
        self.name = self.name()
        self.dsts = [] # PIの接続先(IMUX)

    def name(self):
        name = "I{}".format(self.count)
        return name
        
    def show(self):
        print("Primary Input {}".format(self.name))

class PO: # PEA論理(レーンの集合)からの外部出力
    count = 0
    def __init__(self):
        self.count = PO.count  # POのID番号
        PO.count += 1
        self.name = self.name()
        self.srcs = [] # POの接続元(PEAOutput/OMUX)

    def name(self):
        name = "O{}".format(self.count)
        return name
        
    def show(self):
        print("Primary Output {}".format(self.name))


class IMUX: # PAEセルの入力に付加される入力MUX
    def __init__(self, paecell, inputNum, maxIn=4):
        self.inputs = []          # IMUXの入力リスト(前段レーンの出力MUXなど)
        self.maxIn = maxIn        # IMUXの最大入力数
        self.paecell = paecell    # 所属するPAEセル
        self.inputNum = inputNum  # PAEセルにおける入力番号
        self.name = self.name()

    def numConfBits(self):  # 必要なコンフィギュレーションビットを計算
        return math.ceil(math.log2(len(self.inputs)))

    def name(self):           # IMUXの名前を表示
        name = "IMUX{}_PAE{}_lane{}".format(self.inputNum, self.paecell.count, self.paecell.lane.count)
        return name
    
    def show(self):
        print(self.name)
        #print("-- inputs to IMUX begin")
        #for i in self.inputs:
        #    i.show()
        #print("-- inputs to IMUX end")
            
class OMUX: # レーンの出力に付加される出力MUX
    count = 0
    def __init__(self, lane, withFF=False, skipLengths=None):
        self.count = OMUX.count  # OMUXの番号(PAELogic全体での通し番号)
        OMUX.count += 1
        self.lane = lane      # 所属するレーン
        self.inputs = []      # OMUXの入力リスト(PAEの出力) 一つの場合もある
        self.dsts = []        # OMUX出力の接続先(IMUX/PO)
        self.withFF = withFF  # 出力にFFを不可するか
        self.skipLengths = skipLengths # どれだけ離れたレーンに接続するか
                              # 0:現在(所属)、-1:１個前, +1: 次段(通常接続)
                              # +2:一個飛ばした後段レーン
        self.name = self.name()

    def numConfBits(self):  # 必要なコンフィギュレーションビットを計算
        return math.ceil(math.log2(len(self.inputs)))

    def name(self):           # OMUXの名前を表示
        name = "OMUX{}_lane{}".format(self.count, self.lane.count)
        return name
        
                              
    def show(self):
        print(self.name)
        #print(f"OMUX[{self.count}] for lane[{self.lane.count}]",end="")
        if self.skipLengths != None:
            print(" : OMUX for skip connections", end="")
        else:
            print("", end="")
        #print("OMUX inputs")
        #for i in self.inputs:
        #    i.show()


class PAEOutput: # PAEセルの出力
    def __init__(self, paecell, outputNum):
        self.paecell = paecell
        self.outputNum = outputNum # PAEセルにおける出力番号  
        self.dsts = []             # PAEOutputの接続先(OMUX/PO)
        self.name = self.name()
        

    def name(self):                # PAEOutputの名前を表示
        name = "OutPort{}_PAE{}_lane{}".format(self.outputNum, self.paecell.count, self.paecell.lane.count)
        return name


    def show(self):
        #print("-----start printing PAEOutput")
        print(self.name)        
        #print("Destinations")
        #for m in self.dsts:
        #    m.show()
        #print("-----end printing PAEOutput")            
        
class PAECell: # PAEセル
    count = 0
    def __init__(self, lane, nPAEin=4, nPAEout=1):
        self.count = PAECell.count  # PEAセル番号
        PAECell.count += 1
        self.lane = lane            # 所属するレーン
        self.nPAEin = nPAEin        # 入力数
        self.nPAEout = nPAEout      # 出力数
        self.IMUXes = []            # 入力MUXのリスト
        self.outputs = []           # このPAEセルの出力(PAEOutput)のリスト
        #print(f"CCCC nPAEin={nPAEin}")        
        self.buildIMUXes(nPAEin)
        self.buildOutputs(nPAEout)
        self.name = self.name()

    def buildIMUXes(self, nPAEin):   # 入力MUXを準備
        #print(f"BBBB nPAEin={nPAEin}")
        for i in range(nPAEin):
            self.IMUXes.append(IMUX(self, i))

    def buildOutputs(self, nPAEout):  # 出力を準備
        for i in range(nPAEout):
            self.outputs.append(PAEOutput(self,i))

    def name(self):           # PAECellの名前を表示
        name = "PAE{}_lane{}".format(self.count, self.lane.count)
        return name

            
    def show(self):
        print(f"lane[{self.lane.count}]: PAECell[{self.count}]")
        #for m in self.IMUXes:
        #    m.show()

'''
 SATの変数定義
'''
class Var: # SAT変数
    count = 1 # SATソルバーで、0は特別な区切り文字を表すので、1からスタート
    def __init__(self, mgr):
        self.count = Var.count   # 変数のID番号
        Var.count += 1
        self.mgr = mgr

    @classmethod
    def numVars(cls):
       return cls.count-1 # 変数をすべて作りおえて、Var.countを+1してるので、その分を引く

    def cnfStr(self):
        return "{}".format(self.count)

class BindVar(Var):
    def __init__(self, mgr, instance, target):
        super().__init__(mgr)
        self.instance = instance  # Netlistのnode(PAEInstance, netlistPI/PO)
        self.target = target      # PAE Logicのブロック(PAECell, PI/PO)
        self.name = self.name()
        mgr.vars[self.count] = self

    def name(self):
        name = "b_" + self.instance.name + "_" + self.target.name
        return name

class ConnectVar(Var):
    def __init__(self, mgr, src, omux, dst):
        super().__init__(mgr)
        self.src = src
        self.omux = omux
        self.dst = dst
        self.name = self.name()
        mgr.vars[self.count] = self        

    def name(self):
        name = "c_" + self.src.name
        if self.omux != None:
            name += "--" + self.omux.name
        name += "--" + self.dst.name
        return name
        
class OMUXUseVar(Var): # OMUX omuxが使われるときに、1となる
    def __init__(self, mgr, src, omux):
        super().__init__(mgr)
        self.src = src
        self.omux = omux
        self.name = self.name()
        mgr.vars[self.count] = self

    def name(self):
        name = "u_" + self.src.name
        name += "--" + self.omux.name
        return name

class WireVar(Var):
    def __init__(self, mgr, src, dst):
        super().__init__(mgr)
        self.src = src
        self.dst = dst
        self.name = self.name()
        mgr.vars[self.count] = self        

    def name(self):
        name = "w_" + self.src.name + "--" + self.dst.name
        return name


# ------------------------------------------------------------------
# eFPGA関係のクラス（wirestatをもとに物理的な配線を組み立てている）
# ------------------------------------------------------------------
        
class Interconnect:      # PEA Logic内の配線(wirestat読み込んで分類してるだけ)
    count = 0
    def __init__(self, src, omux, dst):
        self.count =Interconnect.count     # インターコネクト番号 (0,1,2,...)
        Interconnect.count += 1                
        self.src = src   # 接続元(PAE出力, PI)        
        self.omux = omux # 途中経由のOMUX (Noneの場合もあり)
        self.dst = dst   # 接続先(IMUX, PO)

    def show(self):
        print("Interconnect (id={}) {} -> ".format(self.count, self.src.name), end="")
        if self.omux != None:
            print("{} ->".format(self.omux.name), end="")        
        print("{} ".format(self.dst.name))
        
class PEALogic:
    def __init__(self, numPIs=36, numPOs=-1):
        self.lanes = []
        self.numPIs = numPIs
        self.numPOs = numPOs 
        self.PAEOutputs = []
        self.PAECells = []
        self.OMUXes = []
        self.skipOMUXes = [] # (使わないが空リストで残す)
        self.IMUXes = []
        self.PIs = []
        self.POs = []
        self.Interconnects = [] #配線のリスト
        self.buildPIs()
        if self.numPOs != -1:
            self.buildPOs()

    #　1:外部入力　→　MUX
    def connectPI_wire(self, pi_object, dst_x, dst_y, dst_pin):
        try:
            dstPAE = self.lanes[dst_y].PAECells[dst_x]
            imux = dstPAE.IMUXes[dst_pin]
            imux.inputs.append(pi_object)
            pi_object.dsts.append(imux)
        except Exception as e:
            print(f"Warning: Error connecting PI wire: {e}")

    #  2:MUX　→　MUX（内部配線の接続）
    def connectPAEs(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum):
        try:
            # PAE出力ピンに対応するOMUXを特定
            srcLane = self.lanes[src_y]
            omux_index = (src_x * 3) + src_outnum 
            if omux_index >= len(srcLane.OMUXes): # 例外処理
                print(f"Error: OMUX index {omux_index} out of range.")
                return
            omux = srcLane.OMUXes[omux_index]
            dstPAE = self.lanes[dst_y].PAECells[dst_x]
            imux = dstPAE.IMUXes[dst_innum]
            
            imux.inputs.append(omux)
            omux.dsts.append(imux)

        except Exception as e:
            print(f"Error connecting PAE wire: {e}")

    def buildPIs(self): 
        for i in range(self.numPIs):
            self.PIs.append(PI())

    def buildPOs(self): 
        for i in range(self.numPOs):
            self.POs.append(PO())
            
    def addLane(self, lane):
        self.lanes.append(lane)


    # 3:外部出力
    def generateAndconnectPOs(self, directOutput=True, outputLastLane=False):
        # 部品収集 (LaneからPEALogicへリストアップ)
        self.OMUXes = []
        self.PAECells = []
        self.PAEOutputs = []
        self.IMUXes = []
        
        for l in self.lanes:
            self.OMUXes.extend(l.OMUXes)
            self.PAECells.extend(l.PAECells)
            for pc in l.PAECells:
                self.PAEOutputs.extend(pc.outputs)
                self.IMUXes.extend(pc.IMUXes)

        # PO接続
        PAEOutputsToConnect = []
        if directOutput == True:
            if outputLastLane == True:
                lastLane = self.lanes[-1]
                for p in lastLane.PAECells: PAEOutputsToConnect.extend(p.outputs)
            else:
                for p in self.PAECells: PAEOutputsToConnect.extend(p.outputs)
            
            for o in PAEOutputsToConnect:
                po = PO()
                self.POs.append(po)
                o.dsts.append(po)
                po.srcs.append(o)

    # SAT用にリストアップ
    def enumerateInterconnects(self):
        # OMUX -> IMUX/PO
        for omux in self.OMUXes:
            for s in omux.inputs: # src (PAEOutput)
                for d in omux.dsts: # dst (IMUX)
                    self.Interconnects.append(Interconnect(s, omux, d))

        # PI -> IMUX 
        for pi in self.PIs:
            for d in pi.dsts:
                if type(d) is IMUX:
                    self.Interconnects.append(Interconnect(pi, None, d))

        # PAEOutput -> PO (直接出力の場合)
        for o in self.PAEOutputs:
            for d in o.dsts:
                if type(d) is PO:
                    self.Interconnects.append(Interconnect(o, None, d))
                    
class Lane:
    count = 0
    def __init__(self, nPAECells=4, nIMUXins=4, nOMUXes=12, nOMUXins=2, nPAEin=4, nPAEout=3, noOMUX=False, nSkipOMUXes=0, skips = None):
        self.count =Lane.count     # レーン番号 (0,1,2,...)
        Lane.count += 1        
        self.nPAECells = nPAECells # PAEセル数
        self.nOMUXes = nOMUXes     # 出力MUX数
        self.nIMUXins = nIMUXins   # 入力MUXの入力数(レーンで共通と仮定) -> この前提は外す (wirestatsを使うため) (nIMUXinsは使われていない。気にする必要なし)
        self.nOMUXins = nOMUXins   # 出力MUXの入力数(レーンで共通と仮定) (nOMUXinsは使われていない。気にする必要なし)
        self.PAECells = []         # PAEセルのリスト
        self.OMUXes = []           # 出力MUXのリスト
        self.nPAEin = nPAEin       # PEAセルの入力数
        self.nPAEout = nPAEout     # PEAセルの出力数
        #self.nOMUXes = nPAEout * nPAECells # PAE Cellの出力数3×PAE Cell数に設定（OMUX無しにするため）

        self.buildPAECells(nPAECells, nPAEin, nPAEout)
        if noOMUX == False:
            self.buildOMUXes(nOMUXes)
            self.connectPAEOutputToOMUX()

    def buildPAECells(self, nPAECells, nPAEin, nPAEout):
        for i in range(nPAECells):
            print(f"nPAEout = {nPAEout}")
            self.PAECells.append(PAECell(self, nPAEin, nPAEout))
        #PAECell.count = 0      # カウンタをリセット
    
    # レーン内に出力MUXを作る
    def buildOMUXes(self,nOMUXes):
        for i in range(nOMUXes):
            self.OMUXes.append(OMUX(self))

    # 出力MUXの入力にPAEセルの出力を接続する
    def connectPAEOutputToOMUX(self):         
        print("##### connectPAEOutputToOMUX() ####")
        outputs = []
        for p in self.PAECells:
            for o in p.outputs:
                outputs.append(o)
                       
        for i, omux in enumerate(self.OMUXes):
            omux.inputs.append(outputs[i])
            outputs[i].dsts.append(omux)      

    '''
    #デバッグ関連の表示機能（コメントアウトしても問題なし）
    '''                
    def show(self):
        print("--- start printing lane")
        print(f"cnt={self.count}, nPAECells={self.nPAECells}, nIMUXins={self.nIMUXins},\
        noMUX={self.nOMUXes},nOMUXins={self.nOMUXins}")
        for p in self.PAECells:
            p.show()
            for o in p.outputs:
                o.show()
        for m in self.OMUXes:
            m.show()
        print("\n--- end printing lane")

    def showConnections(self): #他のレーンからの接続を表示
        print("Showing connections for lane{}".format(self.count))
        for i, p in enumerate(self.PAECells):
            for j, m in enumerate(p.IMUXes):
                m.show()

# ------------------------------------------------------------------
# ネットリスト関係のクラス
# ------------------------------------------------------------------


class NetlistPI:  # ネットリストの外部入力
    count = 0
    def __init__(self, netlist, name):
        self.count = NetlistPI.count  # PI/POのID番号
        NetlistPI.count += 1
        self.netlist = netlist # PIが所属するネットリスト
        self.name = name       # PIの名前
        self.fanouts = []      # PIの場合のみ: ファンアウト(外部出力か、PAEの入力(何番目)か)

    def show(self):
        print(f"PI[{self.name}]",end="")


class NetlistPO:  # ネットリストの外部出力
    count = 0
    def __init__(self, netlist, name):
        self.count = NetlistPO.count  # PI/POのID番号
        NetlistPO.count += 1
        self.netlist = netlist # POが所属するネットリスト
        self.name = name       # POの名前
        self.input = None      # POの場合のみ: どのPAEインスタンスの出力/PIが入ってくるか

    def show(self):
        print(f"PO[{self.name}]",end="")

        
        
class PAEInstanceInput: # PAEインスタンスの入力
    def __init__(self, pae, inputNum):
        self.PAEInstance = pae     # どのPAEインスタンスの入力か
        self.inputNum = inputNum   # 何番目の入力か

    def show(self):
        print("PAE[{}].in[{}]".format(self.PAEInstance.name, self.inputNum),end="")

        
class PAEInstanceOutput: # PAEインスタンスで新たに生成される中間出力t1, t2, ..
    def __init__(self, name, pae, outputNum):
        self.name = name           # 入力ファイルでの名前 (t1, t2, ...)
        self.PAEInstance = pae     # どのPAEインスタンスの出力か
        self.outputNum = outputNum # 何番目の出力か
        
    def show(self):
        print("PAE[{}].out[{}]".format(self.PAEInstance.name, self.outputNum),end="")
        

class PAEInstance:  # ネットリストのPAEインスタンス
    count = 0
    def __init__(self, netlist, name):
        self.count = PAEInstance.count  # PAEインスタンスID番号
        PAEInstance.count += 1
        self.netlist = netlist   # ノードが所属するネットリスト
        self.name = name         # PAEインスタンス名
        self.inputNames = []     # ノードの入力(名前)(読み込み用)
        self.outputNames = []    # ノードの出力(名前)(読み込み用)
        self.inputs = []         # 入力リスト(外部入力か、PAEの出力(何番目)か, None)
        self.outputs = []        # 出力リスト(外部出力か、PAEの入力(何番目)か, None)
        self.fanouts = []        # 各出力のファンアウト(外部出力か、PAEの入力(何番目)か)
        self.initFanouts()


    def initFanouts(self): # 出力数分のfanoutリストを作る
        numPAEoutputs = self.netlist.numPAEoutputs
        for i in range(numPAEoutputs):
            fanouts = []
            self.fanouts.append(fanouts)

    def show(self):
        print(f"PAEInstance [{self.name}]")

    def showFanouts(self):
        print(f"Fanouts for PAEInstance [{self.name}]")
        for i, fo in enumerate(self.fanouts):
            
            print("{}-th fanout :".format(i), end="")
            for e in fo:
                e.show()
                print("  ",end="")
            print("\n")
        


class Wire:
    count = 0
    def __init__(self, netlist, srcname, dstname):
        self.count = Wire.count  # wireのID番号
        Wire.count += 1
        self.srcname = srcname   # 配線の送信元(PAE出力/PI)の名前
        self.dstname = dstname   # 配線の送信先(PAE入力/PO)の名前
        

class Edge:
    count = 0
    def __init__(self, netlist, src, dst):
        self.count = Edge.count  # edgeのID番号
        Edge.count += 1
        self.src = src   # エッジの元(PAE出力/PI)
        self.dst = dst   # エッジの先(PAE入力/PO)
        
    def show(self):
        print("edge[{}]: ".format(self.count), end="")
        
        # ★修正: src が None でないか確認する
        if self.src is not None:
            self.src.show()
        else:
            print("None", end="")
            
        print(" -> ",end="")
        
        # ★修正: dst が None でないか確認する
        if self.dst is not None:
            self.dst.show()
        else:
            print("None", end="")
            
        print("\n")

        
class Netlist:
    def __init__(self, filename, numPAEinputs = 4, numPAEoutputs = 3):
        self.numPIs = -1
        self.numPOs = -1    
        self.numPAEinputs = numPAEinputs    # PAEセルの入力数
        self.numPAEoutputs = numPAEoutputs  # PAEセルの出力数
        self.netlistPIs = {}                # ネットリストの外部入力の辞書
        self.netlistPOs = {}                # ネットリストの外部出力の辞書
        self.PAEInstances = {}              # 名前とPAEインスタンスの辞書
        self.PAEGeneratedOutputs = {}       # 名前とPAEインスタンスの中間出力
        self.edges = []                     # ネットリスト内の接続リスト
        self.readFromFile(filename)         # ファイルからネットリストの読み込み
        self.connect()                      # ネットリストの接続構築
        self.buildEdges()                   # ネットリスト内の接続リスト(fanoutもついでに)を構築
        self.writeDot()

    # 【修正点】Noneチェックを追加した安全なwriteDot
    def writeDot(self): 
        with open('sample.dot', 'w') as f:
            str = "digraph netlist {\n"
            f.write(str)
            for e in self.edges:
                srcname = "None"
                dstname = "None"

                if e.src is not None:
                    if type(e.src) == PAEInstanceOutput:
                        srcname = e.src.PAEInstance.name
                    elif type(e.src) == NetlistPI:
                        srcname = e.src.name
                    else:
                        srcname = "Unknown"

                if e.dst is not None:
                    if type(e.dst) == PAEInstanceInput:
                        dstname = e.dst.PAEInstance.name
                    elif type(e.dst) == NetlistPO:
                        dstname = e.dst.name
                    else:
                        dstname = "Unknown"
                
                if srcname != "None" and dstname != "None":
                    str = "\t{}->{}\n".format(srcname, dstname)
                    f.write(str)
            str = "}\n"
            f.write(str)            
        
        

    def buildEdges(self): # すでに情報はほぼ準備されている
        # 各PAEインスタンスごとに、実行。PAEの入力に入ってくるエッジ
        for paeInst in self.PAEInstances.values():
            for i, src in enumerate(paeInst.inputs): # 各PAEインスタンスの入力ごとに実行

                # エッジ作成
                if src is None: # PAEの入力がnot-connected (nc)。何もしない
                    continue
                paeInput = PAEInstanceInput(paeInst, i)
                self.edges.append(Edge(self, src, paeInput))

                # ファンアウト情報追加
                if type(src) is PAEInstanceOutput:
                    src.PAEInstance.fanouts[src.outputNum].append(paeInput)
                elif type(src) is NetlistPI:
                    src.fanouts.append(paeInput)
                        
        # 外部出力に入ってくるエッジ
        for po in self.netlistPOs.values():
            
            # エッジ作成            
            self.edges.append(Edge(self, po.input, po))

            # ファンアウト情報追加
            if type(po.input) is PAEInstanceOutput:
                po.input.PAEInstance.fanouts[po.input.outputNum].append(po)
            elif type(po.input) is NetlistPI:
                po.input.show()
                po.input.fanouts.append(po)
                

        #for e in self.edges:
        #    e.show()

        #for p in self.PAEInstances.values():
        #    p.showFanouts()
                

        
    def connect(self): # ネットリストの接続構築

        # 各PAEインスタンスごとに、実行        
        for paeInst in self.PAEInstances.values(): 
            # PAE毎に、出力ごとに、オブジェクト接続・生成
            for i, name in enumerate(paeInst.outputNames): 
                    
                if name == "nc": # 接続無し
                    paeInst.outputs.append(None) # outputsにNoneをセット
                else: # 出力は、新たにこのPAEで生成された信号

                    paeOutput = PAEInstanceOutput(name, paeInst, i)                    

                    if name in self.netlistPOs: # 外部出力
                        
                        #paeInst.outputs.append(paeOutput)
                        #paeInst.outputs.append(self.netlistPOs[name]) # outputsにPOをセット
                        self.netlistPOs[name].input = paeOutput
                    
                    paeInst.outputs.append(paeOutput)
                    self.PAEGeneratedOutputs[name] = paeOutput
                    
        # 各PAEインスタンスごとに、実行        
        for paeInst in self.PAEInstances.values(): 
            # PAE毎に、入力ごとに、オブジェクト接続
            for i, name in enumerate(paeInst.inputNames):
                if name in self.netlistPIs: # 外部入力
                    paeInst.inputs.append(self.netlistPIs[name]) # inputsにPIをセット
                elif name == "nc": # 接続無し
                    paeInst.inputs.append(None) # outputsにNoneをセット
                else: # 入力は、PAEで生成された信号

                    paeOutput = self.PAEGeneratedOutputs.get(name)
                    #paeOutput = self.PAEGeneratedOutputs[name]
                    if paeOutput is None:
                        print(f"PaeOutput is None is connect for {name}")

                    
                    paeInst.inputs.append(paeOutput) # outputsに生成信号をセット

                    
        # 各PAEインスタンスごとに、実行        
        for paeInst in self.PAEInstances.values(): 
                
            # デバッグ用表示
            print("Inputs for PAE[{}]".format(paeInst.name))
            for i, e in enumerate(paeInst.inputs):
                if e is None:
                    print("[{}] : None".format(i))
                    
                elif type(e) is NetlistPI:
                    print("[{}] : PI[{}])".format(i, e.name))
                
                elif type(e) is PAEInstanceOutput:
                    print("[{}] : PAEO[{}] gen. by {}[{}]".format(i, e.name, e.PAEInstance.name, e.outputNum))

            print("Outputs for PAE[{}]".format(paeInst.name))
            for i, o in enumerate(paeInst.outputs):
                if o is None:
                    print("[{}] : None".format(i))
                    
                elif type(o) is NetlistPO:
                    print("[{}] : PO[{}]".format(i, o.name))
                
                elif type(o) is PAEInstanceOutput:
                    print("[{}] : PAEO[{}]".format(i, o.name))
            print("\n")
            
    def readFromFile(self, filename): # ファイルからネットリストの読み込み
        with open(filename) as f:
            for line in f:
                l = line.split()
                for i, e in enumerate(l): # コメント削除
                    if '#' in e:
                        del l[i:]
                        break
                if len(l) == 0:
                    continue

                if l[0] == "inputs":
                        numPIs = 0
                        for e in l[1:]:
                            self.netlistPIs[e] = NetlistPI(self,e)
                            numPIs += 1
                        self.numPIs = numPIs

                elif l[0] == "outputs":
                    numPOs = 0
                    for e in l[1:]:
                        self.netlistPOs[e] = NetlistPO(self,e)
                        numPOs += 1
                    self.numPOs = numPOs
                elif l[0] == "pae":
                    pae = PAEInstance(self,l[1])
                    print("pae{}".format(pae))
                    self.PAEInstances[l[1]] = pae
                    for e in l[2:6]:
                        pae.inputNames.append(e)
                    for e in l[6:]:
                        pae.outputNames.append(e)
                elif l[0] == "wire":
                    wire = Wire(self,l[1],l[2])
                elif l[0] == "PAEinputs":
                    self.numPAEinputs = l[1]
                elif l[0] == "PAEOutputs":
                    self.numPAEoutputs = l[1]

            #print("netlistPIs:{}".format(self.netlistPIs))
            #print("netlistPOs:{}".format(self.netlistPOs))            
            #print("PAEInstances:{}".format(self.PAEInstances))
            #print("numPAEinputs:{}".format(self.numPAEinputs))
            #print("numPAEoutputs:{}\n".format(self.numPAEoutputs))


# ------------------------------------------------------------------
# SAT式作成関係のクラス
# ------------------------------------------------------------------

class Literal: # リテラル。SAT変数の肯定形、または、否定形
    count = 0
    def __init__(self, var, polarity=True):
        self.count = Literal.count  # リテラルのID番号
        Literal.count += 1
        self.var = var              # 対応する変数
        self.polarity = polarity    # 極性(True:肯定形, False:否定形)
        self.str = self.str()       # 変数名を使用したリテラル文字列
        self.cnfStr = self.cnfStr() # 変数のID番号を使用したリテラル文字列
        
    def str(self):
        if self.polarity is True:
            return self.var.name
        else:
            return "!" + self.var.name            

    def cnfStr(self):
        if self.polarity is True:
            return self.var.cnfStr()
        else:
            return "-" + self.var.cnfStr()

# SAT Clauseを表す。Clauseの集合が制約。制約の集合がSAT問題
# Clause はリテラルの集合
class Clause:
    count = 0    
    def __init__(self):
        self.count = Clause.count  # リテラルのID番号
        Clause.count += 1        
        self.literals = []

    @classmethod
    def numClauses(cls):
        return cls.count

    def addLiteral(self, literal):
        self.literals.append(literal)

    def str(self):
        str = ""
        for i, literal in enumerate(self.literals):
            str += literal.str
            if i < len(self.literals)-1:
                str += " + "
        return str

    def cnfStr(self):
        str = ""
        for i, literal in enumerate(self.literals):
            str += literal.cnfStr + " "
        str += "0"
        return str


class Constraint: # SATの各制約を表す
    # 関係する情報を蓄える
    # SAT制約(CNF)で出力する機能
    # clause の集合
    def __init__(self):
        self.clauses = []
        
    def addClause(self, clause):
        self.clauses.append(clause)

    def printStr(self):
        str = ""
        for cl in self.clauses:
            print("("+cl.str()+")")
        print("")
        
    def Str(self):
        str = ""
        for cl in self.clauses:
            str += "("+cl.str()+")"
        return str

    def printCnfStr(self):
        str = ""
        for cl in self.clauses:
            print(cl.cnfStr())

    def cnfStr(self):
        str = ""
        for cl in self.clauses:
            str += cl.cnfStr() + "\n"
        return str

            
# BindConnect制約作成時に使用
# srcが、netlistPI, netlistPOであれば、それをそのまま返す
# srcがPAEインスタンスの入力や出力であれば、対応するPAEインスタンスを返す
def PAEInstanceOrPIPO(src):
    if type(src) is NetlistPI or type(src) is NetlistPO:
        return src
    elif type(src) is PAEInstanceInput or type(src) is PAEInstanceOutput:
        return src.PAEInstance
    else:
        return None
        #assert("Invalid input argumet at PAEInstanceOrPIPO()")
        

# BindConnect制約作成時に使用
# srcがPAEインスタンスの出力/netlistPIであった場合、PAEセル/PIの"binding"(引数)に
# バインドされるときの、対応するPAEセルの出力ポート/PIを返す。
# 同様に、srcがPAEインスタンスの入力/netlistPOであった場合、
# PAEセル/POのbindingにバインドされるときの、対応するPAEセル/POの入力ポートを返す。
# (PAEセルの入力ポートは直接対応するクラスがないので、IMUXにしたが、大丈夫か？。。)
# binding: srcがバインドされるPAEセル/PI/PO
def bindingPort(src, binding):
    if type(src) is PAEInstanceOutput:
        outputNum = src.outputNum
        return binding.outputs[outputNum]
    elif type(src) is PAEInstanceInput:
        inputNum = src.inputNum        
        return binding.IMUXes[inputNum]
    elif type(src) is NetlistPI or type(src) is NetlistPO: 
        return binding
    else:
        return None
        #assert("Invalid input argumet at bindingPort()")
    

class SATmgr: # SAT関係の情報を蓄えるクラス
    def __init__(self, PEALogic, Netlist):
        self.PEALogic = PEALogic
        self.Netlist = Netlist
        self.vars = {}        # 変数の辞書(key: ID番号, val: 変数へのポインタ)
        self.BindVars = {}    # 辞書(PAEインスタンス、セルで引く)
        self.ConnectVars = {} # 辞書(src, omux, dstで引く)
        self.OMUXUseVars = {} # 辞書(src, omuxで引く)
        self.WireVars = {}    # 辞書(src, dstで引く)
        self.makeBindVars()
        self.makeConnectVars()
        self.MappingConstraints = []      # Mapping制約の集合
        self.buildMappingConstraints()
        self.MaxMappingConstraints = []   # MaxMapping制約の集合
        self.buildMaxMappingConstraints()
        self.OMUXUsageConstraints = []     # OMUXUsage制約の集合
        self.buildOMUXUsageConstraints()
        self.OMUXUsageVarConstraints = []  # OMUXUsageVar制約の集合
        self.buildOMUXUsageVarConstraints()
        self.IMUXUsageConstraints = []     # IMUXUsage制約の集合
        self.buildIMUXUsageConstraints()
        self.WireVarConstraints = []      # WireVar制約の集合
        self.buildWireVarConstraints()        
        self.BindConnectConstraints = []  # BindConnect制約の集合
        self.buildBindConnectConstraints()
        self.writeCNF()                   # SATのCNFをファイルに出力
        self.writeReadableCNF()           # SATのCNFをデバッグ用に出力
        self.solveSAT()                   # 出力したCNFをSATソルバーで解く
        self.readSATResult()              # SATソルバーの結果を読み込み


    # SATの結果を読み込んで、配置配線結果に翻訳する機能
    def readSATResult(self):
        #for k, v in self.vars.items():
        #    print("var_id={}, var_name={}".format(k, v.name))

        trueVars = []

        with open('sample.output', 'r') as f:
            satOutput = f.read()
            #print(satOutput)
            tokens = satOutput.split()
            if tokens[0] == "SAT": # SAT
                for t in tokens[1:]:
                    if t.startswith('-'):   # 変数=0
                        #print("t[1:]= {}".format(t[1:]))
                        var = self.vars.get(int(t[1:]))
                        #print("1. satVar: !{}".format(var.name))

                    else: # 変数=1 これだけ、trueVarsに格納する
                        #print(f"t={t}, int(t)={int(t)}")
                        if t=="0": # 最後の終端文字　(意味無し)
                            continue
                        var = self.vars.get(int(t))
                        trueVars.append(var)
                        #print("2. satVar: {}".format(var.name))                        

            else:                  # UNSAT
                print("########### SAT could not find solution")
                pass

        print("1を割り当てられた決定変数は以下です")
        for i, v in enumerate(trueVars):
            print("i={}: ".format(i), end="")
            print(v.name)

        return trueVars # Graphviz接続で参照したい



    # SATの結果を読み込んで、配置配線結果に翻訳する機能

    def readSATResultKissat(self):
        #for k, v in self.vars.items():
        #    print("var_id={}, var_name={}".format(k, v.name))

        print("using Kissat")

        trueVars = []

        isSAT = False
        
        with open('sample.output', 'r') as f:
            lines = f.readlines()

        index = 0
        finish = False

        while index < len(lines):
            line = lines[index]
            tokens = line.split()

            print("tokens:")
            print(tokens)

            if tokens[0] == "c": # comment
                index += 1
                continue

            if tokens[0] == "s": # result
                if tokens[1] == "SATISFIABLE": # SAT
                    isSAT = True
                    index += 1
                    continue
                else:                  # UNSAT
                    print("########### SAT could not find solution")
                    break

            if tokens[0] == "v": # variable assignment

                for t in tokens[1:]:

                    print(f"token: {t}")
                    
                    if t.startswith('-'):   # 変数=0
                        #print("t[1:]= {}".format(t[1:]))
                        var = self.vars.get(int(t[1:])) # var使われないので、何もしていない(削除する)
                        #print("1. satVar: !{}".format(var.name))

                    else: # 変数=1 これだけ、trueVarsに格納する
                        #print(f"t={t}, int(t)={int(t)}")
                        #print(f"numVars = {Var.numVars()}")
                        if t=="0": # 最後の終端文字　(意味無し)
                            #print("Finish")
                            finish = True
                            break
                        #print(f"getting var for var id = {int(t)}")
                        var = self.vars.get(int(t))
                        #print("var:")
                        #var.cnfStr()
                        trueVars.append(var)
                        #print("2. satVar: {}".format(var.name))                        
            if finish == True:
                break

            index += 1

        print("1を割り当てられた決定変数は以下です")
        for i, v in enumerate(trueVars):
            print("i={}: ".format(i), end="")
            print(v.name)

        return trueVars # Graphviz接続で参照したい

    

    # SATソルバーを実行
    def solveSAT(self):

        #command = ['minisat', '-cpu-lim=10', 'sample.cnf', 'sample.output']
        #command = ['cadical', 'sample.cnf', 'sample.output']
        # for minisat
        #res = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)        

        command = ['kissat', '--time=60', '--no-binary', 'sample.cnf']        
        # for kissat
        with open('sample.output', 'w') as output_file:
            with open('sample.cnf', 'r') as input_file:
                res = subprocess.run(command, stdin=input_file, stdout=output_file, shell=False)
                #res = subprocess.run(command, stdin=input_file, stdout=output_file, shell=True)                


    # 全体のSAT式をファイルに出力する機能
    def writeCNF(self):
        with open('sample.cnf', 'w') as f:
            str = "p cnf {} {}\n".format(Var.numVars(), Clause.numClauses())
            f.write(str)

            for c in self.MappingConstraints:
                str = c.cnfStr()
                f.write(str)
            for c in self.MaxMappingConstraints:
                str = c.cnfStr()
                f.write(str)                
            for c in self.OMUXUsageConstraints:
                str = c.cnfStr()
                f.write(str)                                
            for c in self.OMUXUsageVarConstraints:
                str = c.cnfStr()
                f.write(str)
            for c in self.IMUXUsageConstraints:
                str = c.cnfStr()
                f.write(str)
            for c in self.WireVarConstraints:
                str = c.cnfStr()
                f.write(str)
            for c in self.BindConnectConstraints:
                str = c.cnfStr()
                f.write(str)

    # 全体のSAT式をデバッグ用にファイル出力する機能 (人間が読めるように、変数名を使用)
    def writeReadableCNF(self):
        with open('sample.rcnf', 'w') as f:
            f.write("MappingConstraints\n")
            for c in self.MappingConstraints:
                str = c.Str()+"\n"
                f.write(str)
            f.write("\nMaxMappingConstraints\n")                
            for c in self.MaxMappingConstraints:
                str = c.Str()+"\n"
                f.write(str)
            f.write("\nOMUXUsageConstraints\n")                
            for c in self.OMUXUsageConstraints:
                str = c.Str()+"\n"
                f.write(str)
            f.write("\nOMUXUsageVarConstraints\n")
            for c in self.OMUXUsageVarConstraints:
                str = c.Str()+"\n"
                f.write(str)
            f.write("\nIMUXUsageConstraints\n")
            for c in self.IMUXUsageConstraints:
                str = c.Str()+"\n"
                f.write(str)
            f.write("\nWireVarConstraints\n")
            for c in self.WireVarConstraints:
                str = c.Str()+"\n"
                f.write(str)
            f.write("\nBindConnectConstraints\n")
            for c in self.BindConnectConstraints:
                str = c.Str()+"\n"
                f.write(str)

        
    # BindConnect制約を作る
    def buildBindConnectConstraints(self):
        # return
        for e in self.Netlist.edges:
            src = e.src
            dst = e.dst
            srcInst = PAEInstanceOrPIPO(src)
            dstInst = PAEInstanceOrPIPO(dst)
            
            # 【修正】ここでNoneチェックを行う
            if srcInst is None or dstInst is None: continue

            srcBindings = [] 
            srcBindingPorts = [] 
            for k, v in self.BindVars.items():
                if k[0] == srcInst:
                    srcBindings.append(k[1])
                    srcBindingPort = bindingPort(src, k[1])
                    srcBindingPorts.append(srcBindingPort)
            
            dstBindings = [] 
            dstBindingPorts = [] 
            for k, v in self.BindVars.items():
                if k[0] == dstInst:
                    dstBindings.append(k[1])
                    dstBindingPort = bindingPort(dst, k[1])
                    dstBindingPorts.append(dstBindingPort)

            for j1, srcBinding in enumerate(srcBindings):
                for j2, dstBinding in enumerate(dstBindings):
                    srcBindingPort = srcBindingPorts[j1]
                    dstBindingPort = dstBindingPorts[j2]
                    
                    # 【修正】ここでもNoneチェックを行う
                    if srcBindingPort is None or dstBindingPort is None: continue

                    bindConnectConstraint = Constraint()                    
                    wv = self.WireVars.get((srcBindingPort, dstBindingPort))
                    if wv is None:
                        #print("Following WireVars not found:")
                        #print("from ", end="")
                        #srcBindingPort.show()
                        #print("to ", end="")
                        #dstBindingPort.show()
                        
                        # srcからdstに接続する配線が存在しないことを意味する。
                        # このような状況で、srcInstをsrcBindingに、かつ、同時に
                        # dstInstをdstBindingにバインド(配置)することはできない。
                        # これを条件に表現する。
                        # つまり、バインド変数を0に設定する必要がある。

                        sbv = self.BindVars.get((srcInst, srcBinding))
                        #print(f"src: Illegal binding vars, {sbv.name}")

                        dbv = self.BindVars.get((dstInst, dstBinding))
                        #print(f"dst: Illegal binding vars, {dbv.name}")

                        cl = Clause()
                        l = Literal(sbv, False)
                        cl.addLiteral(l)
                        l = Literal(dbv, False)
                        cl.addLiteral(l)
                        bindConnectConstraint.addClause(cl)
                        #print("bindConnectConstraint")
                        #bindConnectConstraint.printStr()
                        
                        self.BindConnectConstraints.append(bindConnectConstraint)
                        continue

                    cl = Clause()

                    bv = self.BindVars.get((srcInst, srcBinding))
                    l = Literal(bv, False)
                    cl.addLiteral(l)
                    bv = self.BindVars.get((dstInst, dstBinding))
                    l = Literal(bv, False)
                    cl.addLiteral(l)
                        
                    l = Literal(wv, True)
                    cl.addLiteral(l)

                    bindConnectConstraint.addClause(cl)
                    self.BindConnectConstraints.append(bindConnectConstraint)
                        

    # WireVar制約を作る
    def buildWireVarConstraints(self):
        # Wire変数ごとに、制約を作る
        # src, dstが共通のConnectVarを選び出す
        for wk, wv in self.WireVars.items():
            connectvars = []
            for ck, cv in self.ConnectVars.items():
                if wk[0] == ck[0] and wk[1] == ck[2]:
                    connectvars.append(cv)

            # Wire変数に関してw、制約を作る
            wireVarConstraint = Constraint()
            cl = Clause()
            l = Literal(wv, False)
            cl.addLiteral(l)
            for cv in connectvars:
                l = Literal(cv, True)
                cl.addLiteral(l)
            wireVarConstraint.addClause(cl)
            self.WireVarConstraints.append(wireVarConstraint)

        
    # OMUXUsageVar制約を作る
    def buildOMUXUsageVarConstraints(self):

        return # コメントアウト　2024/12/23
        
        # OMUX m, PAEOutput sごとに、制約を作る

        OMUXes = self.PEALogic.OMUXes + self.PEALogic.skipOMUXes
        print("len(OMUXes)={}".format(len(self.PEALogic.OMUXes)))
        print("len(skipOMUXes)={}".format(len(self.PEALogic.skipOMUXes)))
        
        print("resulting OMUXes begin")
        for m in OMUXes:
            m.show()
            print("\n")
        print("resulting OMUXes end")
        
        #for OMUX in self.PEALogic.OMUXes:
        for OMUX in OMUXes:            
            for PAEOutput in self.PEALogic.PAEOutputs:
                
                # OMUX m, PAEOutput sに関するOMUXUse変数を取り出す
                omuxusevar = self.OMUXUseVars.get((PAEOutput,OMUX))
                if omuxusevar is None:
                    continue

                # OMUX m, PAEOutput sに関するConnect変数を取り出す
                connectvars = []
                for k, v in self.ConnectVars.items():
                    if k[0] != PAEOutput:
                        continue
                    if k[1] != OMUX:
                        continue
                    connectvars.append(v)
            
                # OMUX m, PAEOutput sに関して、OMUXUsageVar制約を作る
                OMUXUsageVarConstraint = Constraint()
                for u in connectvars:
                    cl = Clause()
                    l = Literal(u, False)
                    cl.addLiteral(l)                
                    l = Literal(omuxusevar, True)
                    cl.addLiteral(l)
                    OMUXUsageVarConstraint.addClause(cl)
                self.OMUXUsageVarConstraints.append(OMUXUsageVarConstraint)



    # Mapping制約を作る
    def buildMappingConstraints(self):

        # PAEインスタンス、netlistPI, netlistPOごとに、制約を作る
        # まずそれらすべてを含んだリストを作る
        
        instances = []
        for PAEInstance in self.Netlist.PAEInstances.values():
            instances.append(PAEInstance)
        for netlistPI in self.Netlist.netlistPIs.values():
            instances.append(netlistPI)
        for netlistPO in self.Netlist.netlistPOs.values():
            instances.append(netlistPO)
            
        #for PAEInstance in self.Netlist.PAEInstances.values():        
        for instance in instances:
            # Bind変数から、PAEInstance iに関するものだけ取り出す
            bindvars = []
            for k, v in self.BindVars.items():
                #if k[0] != PAEInstance:
                if k[0] != instance:
                    continue
                bindvars.append(v)
                #print("=== In MappingConstraints, print bindvar")
                #print(v.name)
                
            # PAEInstance iに関して、Mapping制約を作る
            mappingConstraint = Constraint()
            cl = Clause()            
            for v in bindvars:
                l = Literal(v, True)
                cl.addLiteral(l)
            mappingConstraint.addClause(cl)
            self.MappingConstraints.append(mappingConstraint)
            

    # MaxMapping制約を作る
    def buildMaxMappingConstraints(self):

        # PAEセル、PIセル, POセルごとに、制約を作る
        # まずそれらすべてを含んだリストを作る
        
        cells = []
        for PAECell in self.PEALogic.PAECells:
            cells.append(PAECell)
        for PI in self.PEALogic.PIs:
            cells.append(PI)
        for PO in self.PEALogic.POs:
            cells.append(PO)
        
        #for PAECell in self.PEALogic.PAECells:
        for cell in cells:
            cell.show()
            # Bind変数から、Cell jに関するものだけ取り出す
            bindvars = []
            for k, v in self.BindVars.items():
                #if k[1] != PAECell:
                if k[1] != cell:
                    continue
                bindvars.append(v)
                #print("!!!=== In MaxMappingConstraints, print bindvar")
                #print(v.name)
                
            # Cell jに関して、MaxMapping制約を作る
            pairs = list(itertools.combinations(bindvars, 2))
            if len(pairs) == 0:
                continue

            #for p in pairs:
            #    print("======= PAIR")
            #    print(p[0].name)
            #    print(p[1].name)
                
            maxMappingConstraint = Constraint()            

            for p in pairs:
                u = p[0]
                v = p[1]
                
                if u == v: # 同じbind変数はスキップ
                    continue
                
                cl = Clause()
                l = Literal(u, False)
                cl.addLiteral(l)
                l = Literal(v, False)
                cl.addLiteral(l)

                maxMappingConstraint.addClause(cl)
                #print("=== In MaxMappingConstraints, print clause")
                #print(cl.str())
                
            self.MaxMappingConstraints.append(maxMappingConstraint)


    # OMUXUsage制約を作る
    def buildOMUXUsageConstraints(self):

        return # コメントアウト　2024/12/23 配線評価のため
    
        # OMUXごとに、制約を作る

        OMUXes = self.PEALogic.OMUXes + self.PEALogic.skipOMUXes        
        #for OMUX in self.PEALogic.OMUXes:
        for OMUX in OMUXes:
            # OMUXUse変数から、OMUX mに関するものだけ取り出す
            omuxusevars = []
            for k, v in self.OMUXUseVars.items():
                if k[1] != OMUX:
                    continue
                omuxusevars.append(v)
                
            # OMUX mに関して、MUXUsage制約を作る
            OMUXUsageConstraint = Constraint()

            pairs = list(itertools.combinations(omuxusevars, 2))

            #print("len={}".format(len(pairs)))
            #for p in pairs:
            #    print("======= PAIR2")
            #    print(p[0].name)
            #    print(p[1].name)

            #for u in omuxusevars:
                #for v in omuxusevars:

            for p in pairs:
                u = p[0]
                v = p[1]

                if u == v:
                    continue
                
                cl = Clause()
                l = Literal(u, False)
                cl.addLiteral(l)                    
                l = Literal(v, False)
                cl.addLiteral(l)
                OMUXUsageConstraint.addClause(cl)
                #print("=== In OMUXUsageConstraints, print clause")
                #print(cl.str())

            self.OMUXUsageConstraints.append(OMUXUsageConstraint)


    # IMUXUsage制約を作る            
    def buildIMUXUsageConstraints(self):
        
        #return # コメントアウト　2024/12/23 配線評価のため
        
        # IMUXごとに、制約を作る
        for IMUX in self.PEALogic.IMUXes:
            # Connect変数から、IMUX dに関するものだけ取り出す
            imuxusevars = []
            for k, v in self.ConnectVars.items():
                if k[2] != IMUX:
                    continue
                imuxusevars.append(v)
                
            # IMUX dに関して、IMUXUsage制約を作る
            IMUXUsageConstraint = Constraint()
            pairs = list(itertools.combinations(imuxusevars, 2))

            #print("len={}".format(len(pairs)))
            #for p in pairs:
            #    print("======= PAIR3")
            #    print(p[0].name)
            #    print(p[1].name)

            for p in pairs:
                u = p[0]
                v = p[1]

                if u == v:
                    continue
                
                cl = Clause()
                l = Literal(u, False)
                cl.addLiteral(l)                    
                l = Literal(v, False)
                cl.addLiteral(l)
                IMUXUsageConstraint.addClause(cl)
                #print("=== In IMUXUsageConstraints, print clause")
                #print(cl.str())

            self.IMUXUsageConstraints.append(IMUXUsageConstraint)

            
    # Bind変数を準備する
    def makeBindVars(self):
        # PAEインスタンスをPAEセルにバインドする場合
        for PAEInstance in self.Netlist.PAEInstances.values():
            for PAECell in self.PEALogic.PAECells:
                bindvar = BindVar(self, PAEInstance, PAECell)
                #print(bindvar.name)
                bind = (PAEInstance, PAECell)
                self.BindVars[bind] = bindvar
  #              print("Bind var (PEAinstance)")
  #              print(bindvar.name)                
        # netlistPIをPEA LogicのPIにバインドする場合
        for netlistPI in self.Netlist.netlistPIs.values():
            for PI in self.PEALogic.PIs:
                bindvar = BindVar(self, netlistPI, PI)
                bind = (netlistPI, PI)
                self.BindVars[bind] = bindvar
  #              print("Bind var (PI)")
  #              print(bindvar.name)
        # netlistPOをPEA LogicのPOにバインドする場合
        for netlistPO in self.Netlist.netlistPOs.values():
            for PO in self.PEALogic.POs:
                bindvar = BindVar(self, netlistPO, PO)
                bind = (netlistPO, PO)
                self.BindVars[bind] = bindvar
  #              print("Bind var (PO)")
  #              print(bindvar.name)


    # Connect変数, OMUXUseVar変数, Wire変数を準備する
    def makeConnectVars(self):
        for ic in self.PEALogic.Interconnects:
            # connect vars
            connectvar = ConnectVar(self, ic.src, ic.omux, ic.dst)
 #           print(connectvar.name)
            connect = (ic.src, ic.omux, ic.dst)
            self.ConnectVars[connect] = connectvar

        for ic in self.PEALogic.Interconnects:            
            # wire vars
            wirevar = WireVar(self, ic.src, ic.dst)
 #           print(wirevar.name)
            wire = (ic.src, ic.dst)
            self.WireVars[wire] = wirevar

        for ic in self.PEALogic.Interconnects:
            # omuxuse vars
            if ic.omux == None:
                continue
            omuxuse = (ic.src, ic.omux)
            if omuxuse in self.OMUXUseVars:
                #print("Found duplication in OMUXUseVars")
                continue
            omuxusevar = OMUXUseVar(self, ic.src, ic.omux)
 #           print(omuxusevar.name)
            self.OMUXUseVars[omuxuse] = omuxusevar
            
#        print("----- ConnectVars")                        
#        for v in self.ConnectVars.keys():
#            print(f"{v[0].name}, ", end="")            
#            if v[1] != None:
#                print(f"{v[1].name}, ", end="")
#            print(f"{v[2].name}")

#        print("----- OMUXUseVars")            
#        for v in self.OMUXUseVars.keys():
#            print(f"{v[0].name}, ", end="")
#            print(f"{v[1].name}")            

#        print("----- WireVars")            
#        for v in self.WireVars.keys():
#            print(f"{v[0].name}, ", end="")
#            print(f"{v[1].name}")            

# ... (SATmgrクラスなどの後) ...




def main():
    # ================= 設定 =================
    NETLIST_DIR = "netlists_500/*.net" # 環境に合わせて書き換えてください
    STRUCT_FILE = "wirestat_final2.txt"
    LOG_FILE = "sat_debug.log"              # デバッグログの出力先
    # ========================================

    # 実行のたびにログファイルを空にする（上書きモードで開いてすぐ閉じる）
    with open(LOG_FILE, "w") as f:
        f.write("=== SAT Debug Log ===\n")

    print(f"Loading Architecture Structure from: {STRUCT_FILE}")
    print(f"Debug logs will be saved to: {LOG_FILE}")
    
    # 1. PEA Logic 构建
    pl = PEALogic(numPIs=36) 
    for _ in range(4):
        pl.addLane(Lane(nPAECells=4, nIMUXins=4, nOMUXes=12, nPAEout=3, noOMUX=False))

    # 2. 配線構造読み込み
    wirestats = WireStats(STRUCT_FILE)
    for ws in wirestats.stats:
        is_external = (ws.src_y == -1) or (ws.src_outnum == -1)
        if is_external:
            if 0 <= ws.src_x < len(pl.PIs):
                pl.connectPI_wire(pl.PIs[ws.src_x], ws.dst_x, ws.dst_y, ws.dst_innum)
        else:
            pl.connectPAEs(ws.src_x, ws.src_y, ws.src_outnum, ws.dst_x, ws.dst_y, ws.dst_innum)

    pl.generateAndconnectPOs(directOutput=True, outputLastLane=False)
    pl.enumerateInterconnects()

    # 3. 500個処理
    netlist_files = sorted(glob.glob(NETLIST_DIR))
    
    if not netlist_files:
        print(f"Error: No .net files found in {NETLIST_DIR}")
        return

    print(f"Found {len(netlist_files)} netlists. Start processing...")

    success_count = 0
    total_count = 0
    failed_list = []

    for net_file in netlist_files:
        # =======================================================
        # ★【重要】カウンターのリセット (ここを追加！)
        # ループ毎にIDを初期化しないと、CNFのヘッダー数と中身がズレます
        # =======================================================
        Var.count = 1      # SAT変数は1からスタート
        Clause.count = 0   # 制約数は0から
        Literal.count = 0
        
        # ネットリスト読み込みクラスのカウンターもリセット
        NetlistPI.count = 0
        NetlistPO.count = 0
        PAEInstance.count = 0
        Wire.count = 0
        Edge.count = 0
        # =======================================================
        total_count += 1
        short_name = os.path.basename(net_file)
        
        # 進捗表示 (これはターミナルに出したいので、リダイレクト前に実行)
        print(f"\rProcessing [{total_count}/{len(netlist_files)}] ... {short_name:<20}", end="", flush=True)

        # ★ここからログファイルへ出力を切り替え
        # -------------------------------------------------------
        original_stdout = sys.stdout  # 元の出力先(ターミナル)を保存
        try:
            with open(LOG_FILE, "a") as log_f: # 追記モードで開く
                sys.stdout = log_f             # 出力先をファイルに変更
                
                # ファイルの中に区切り線を入れる
                print(f"\n\n{'='*30}\nProcessing: {short_name}\n{'='*30}")

                # --- ここから下のprintはすべてファイルに書かれます ---
                netlist = Netlist(net_file)
                
                # リソースチェック
                if (pl.numPIs < netlist.numPIs) or (sum(l.nPAECells for l in pl.lanes) < len(netlist.PAEInstances)):
                    print("-> Skipped (Resource shortage)")
                    # 出力を戻してからリスト追加
                    sys.stdout = original_stdout
                    failed_list.append(short_name)
                    continue

                # SAT実行
                satmgr = SATmgr(pl, netlist)
                trueVars = satmgr.readSATResultKissat()
                
                if len(trueVars) > 0:
                    print("-> SAT Success")
                    # 出力を戻してからカウント
                    sys.stdout = original_stdout
                    success_count += 1
                else:
                    print("-> UNSAT Failed")
                    # 出力を戻してからリスト追加
                    sys.stdout = original_stdout
                    failed_list.append(short_name)

        except Exception as e:
            # エラーが起きても必ず出力をターミナルに戻す
            sys.stdout = original_stdout 
            print(f" Error: {e}", end="") # ターミナルにもエラー表示
            with open(LOG_FILE, "a") as log_f:
                log_f.write(f"\nEXCEPTION: {e}\n")
            failed_list.append(short_name)
            continue
        finally:
            # 安全のため、確実に元に戻す
            sys.stdout = original_stdout
        # -------------------------------------------------------
        # ★ここまで切り替え完了

    # 4. 最終結果表示 (ターミナルに表示)
    print("\n\n" + "="*40)
    print("            FINAL RESULT            ")
    print("="*40)

    if len(failed_list) > 0:
        print("Failed Netlists:")
        for name in failed_list:
            print(f"  - {name}")
    else:
        print("Failed Netlists: None (All Perfect!)")
    
    print("-" * 40)
    print(f"Success Rate      : {success_count} / {len(netlist_files)}  ({(success_count/len(netlist_files))*100:.2f}%)")

    numConfBits = 0
    for l in pl.lanes:
        for pae in l.PAECells:
            for m in pae.IMUXes:
                numConfBits += m.numConfBits()
    print(f"Configuration Bits: {numConfBits}")
    print(f"Debug Log Saved to: {LOG_FILE}")
    print("="*40)

    
'''
    #以下は描画関連
    def saveGraph_AC(self, filename:str="cell_graph"):

        cellgraph = graphviz.Digraph('cell graph', format='png', filename='cell_graph')

        cellgraph.graph_attr['ranksep'] = "3"

        # label subgraph r with
        with cellgraph.subgraph(name="root") as r:
            #r.graph_attr['rankdir'] = 'TB'

            # in
            with r.subgraph(name="cluster_in") as cluster_in:
                cluster_in.graph_attr['rankdir'] = 'LR'
                for pi in self.PIs:
                    cluster_in.node(pi.name,shape=GL.ShapePI,
                                    fillcolor=GL.ColorPI,style="filled")
                    
            with r.subgraph(name="cluster_out") as cluster_out:
                cluster_out.graph_attr['rankdir'] = 'LR'
                for po in self.POs:
                    cluster_out.node(po.name,shape=GL.ShapePO,
                                     fillcolor=GL.ColorPO,style="filled")
                    
            for i, lane in enumerate(self.lanes): # label LANE loop node
                ## laneごとにサブグラフを作成
                # label subgraph l with
                with r.subgraph(name="cluster_lane{}".format(i)) as l:
                    #l.graph_attr['rankdir'] = 'TB'
                    # 最終レーンならsink属性をつける
                    if i == len(self.lanes) - 1 :
                        l.graph_attr['rank'] = "sink"

                    freq = len(GL.LaneBGColorList)
                    l.graph_attr['bgcolor'] = GL.LaneBGColorList[i%freq]

                    # PAECell, それに属するIMUXを用意
                    with l.subgraph(name="cluster_imux_lane{}".format(i)) as ig:
                        
                        ig.graph_attr['rankdir'] = 'LR'
                        ig.graph_attr['rank'] = 'source'
                        for PAECell in lane.PAECells:
                            # IMUX
                            for imux in PAECell.IMUXes:
                                imuxname = imux.name

                                ig.node(imuxname, shape=GL.ShapeIMUX,
                                        fillcolor=GL.ColorIMUX, style="filled")
                            
                    # PAE
                    # IMUXより下に置く
                    with l.subgraph(name="cluster_pae_lane{}".format(i)) as pg:
                        pg.graph_attr['rankdir'] = 'LR'
                        pg.graph_attr['rank'] = 'same'

                        for PAECell in lane.PAECells:
                            paename = PAECell.name
                            pg.node(paename, shape=GL.ShapePAECell,
                                    fillcolor=GL.ColorPAECell, style="filled")

                    # OMUX, skipOMUXを用意
                    with l.subgraph(name="cluster_omuxes_lane{}".format(i)) as osg:
                        osg.graph_attr['rankdir'] = 'LR'
                        osg.graph_attr['rank'] = 'sink'

                        with osg.subgraph(name="cluster_omux_lane{}".format(i)) as og:
                            og.graph_attr['rank'] = "min"
                            for omux in lane.OMUXes:
                                # 先頭を決め打ち
                                # 現状、OMUXのinputは同一laneのPAEのみなので決め打ちできる。
                                omuxname = omux.name
                                og.node(omuxname, shape=GL.ShapeOMUX,
                                        fillcolor=GL.ColorOMUX, style="filled")
                        with osg.subgraph(name="cluster_somux_lane{}".format(i)) as sog:
                            sog.graph_attr['rank'] = "max"
                            for skipOMUX in lane.skipOMUXes:
                                omuxname = skipOMUX.name
                                sog.node(omuxname,shape=GL.ShapeSkipOMUX,
                                        fillcolor=GL.ColorSkipOMUX, style="filled")
        # ノード作成            
        #---------------------------------------------------------------------
        # エッジ作成
                                
        for lane in self.lanes: # label LANE loop edge
            # PAECellを探索
            for PAECell in lane.PAECells: # label PAECELL loop
                paename = PAECell.name
                # 入力されているIMUXを探索
                for imux in PAECell.IMUXes:
                    imuxname = imux.name

                    cellgraph.edge(imuxname, paename) # imux -> paeの接続を作成

                    for input_signal in imux.inputs: # LABEL inputs loop
                        in_name = input_signal.name
                        # skipOMUXなら矢印の色を変える
                        # 自分への接続
                        if hasattr(input_signal, 'skipLength') == False:
                            cellgraph.edge(in_name, imuxname) # pi or omux -> imuxの接続を作成
                        elif input_signal in lane.skipOMUXes:
                            cellgraph.edge(in_name, imuxname, color = GL.ColorSkipArrowOutSelf)
                        elif input_signal.skipLengths != None:
                            cellgraph.edge(in_name, imuxname, color = GL.ColorSkipArrowOutNotSelf)
                        else:
                            # 通常色
                            cellgraph.edge(in_name, imuxname) # pi or omux -> imuxの接続を作成

            # #################
            # label PAECELL loop
            # #################

            # OMUXを探索
            for omux in lane.OMUXes:
                # 入力されているPAEOutを探索
                # 2入力なら2本接続したいので、重複を考慮しない
                for PAEOut in omux.inputs:
                    omuxname = omux.name
                    paename = PAEOut.paecell.name
                    cellgraph.edge(paename, omuxname) # pae -> omuxの接続を作成

            # skipOMUXを探索
            for skipOMUX in lane.skipOMUXes:
                # 入力されているPAEOutを探索
                # 3入力なら3本接続したいので、重複を考慮しない
                for PAEOut in skipOMUX.inputs:
                    omuxname = skipOMUX.name
                    paename = PAEOut.paecell.name
                    cellgraph.edge(paename, omuxname, color=GL.ColorSkipArrowIn) # pae -> skipomuxの接続を作成

        # #####################
        # label LANE loop edge
        # #####################

        for po in self.POs:
            poname = po.name
            for src in po.srcs:
                paename = src.paecell.name
                cellgraph.edge(paename, poname)

        cellgraph.render(filename)



    def saveGraph(self, trueVars, filename:str="cell_graph"):

        # のちの探索性のために、solverの回答からリストを作成
        if trueVars is not None:
            for cstart, Var in enumerate(trueVars):
                if isinstance(Var, ConnectVar):
                    break

            for wstart, Var in enumerate(trueVars):
                if isinstance(Var, WireVar):
                    break

            for ustart, Var in enumerate(trueVars):
                if isinstance(Var, OMUXUseVar):
                    break

            bindVars = trueVars[:cstart]
            connectVars = trueVars[cstart:wstart]
            wireVars = trueVars[wstart:ustart] # not used
            useomuxVars = trueVars[ustart:]

            # ターゲット名リストを作成
            l_b_target = []
            for bindVar in bindVars:
                l_b_target.append(bindVar.target.name)

            # 接続されているimux名リストを作成
            l_c_imux = []
            # 接続されているomux名リストを作成
            l_c_omux = []

            for connectVar in connectVars:
                if isinstance(connectVar.dst, IMUX):
                    l_c_imux.append(connectVar.dst.name)

                if isinstance(connectVar.omux, OMUX):
                    l_c_omux.append(connectVar.omux.name)

            # 使用されているomux名リストを作成
            l_u_omux = []
            for useomuxVar in useomuxVars:
                # .omuxは必ずOMUXのインスタンスなので、if不要
                l_u_omux.append(useomuxVar.omux.name)

        else:
            print("if set AllConnection False, trueVars shall be input")
            exit(1)

        cellgraph = graphviz.Digraph('cell graph', format='png', filename='cell_graph')

        cellgraph.graph_attr['ranksep'] = "3"

        # nodeを作成(成形・配置のため)

        # label subgraph r with
        with cellgraph.subgraph(name="root") as r:
            #r.graph_attr['rankdir'] = 'TB'

            # in
            with r.subgraph(name="cluster_in") as cluster_in:
                cluster_in.graph_attr['rankdir'] = 'LR'
                for pi in self.PIs:
                    if pi.name in l_b_target:

                        fill = GL.ColorBind

                    else:
                        fill = GL.ColorPI

                    cluster_in.node(pi.name,shape=GL.ShapePI,
                                    fillcolor=fill,style="filled")

            # out
            with r.subgraph(name="cluster_out") as cluster_out:
                cluster_out.graph_attr['rankdir'] = 'LR'
                for po in self.POs:
                    if po.name in l_b_target:
                        fill = GL.ColorBind
                    else:
                        fill = GL.ColorPO

                    cluster_out.node(po.name,shape=GL.ShapePI,
                                     fillcolor=fill,style="filled")
            # lane
            
            for i, lane in enumerate(self.lanes): # label LANE loop node
                ## laneごとにサブグラフを作成
                # label subgraph l with
                with r.subgraph(name="cluster_lane{}".format(i)) as l:
                    #l.graph_attr['rankdir'] = 'TB'
                    # 最終レーンならsink属性をつける
                    if i == len(self.lanes) - 1 :
                        l.graph_attr['rank'] = "sink"

                    freq = len(GL.LaneBGColorList)
                    l.graph_attr['bgcolor'] = GL.LaneBGColorList[i%freq]

                    # PAECell, それに属するIMUXを用意
                    with l.subgraph(name="cluster_imux_lane{}".format(i)) as ig:
                        
                        ig.graph_attr['rankdir'] = 'LR'
                        ig.graph_attr['rank'] = 'source'
                        for PAECell in lane.PAECells:
                            # IMUX
                            for imux in PAECell.IMUXes:
                                imuxname = imux.name

                                #connectに登場するIMUXなら色を変える
                                if imuxname in l_c_imux:
                                    fill=GL.ColorBind
                                else:
                                    fill=GL.ColorIMUX
                                    
                                ig.node(imuxname, shape=GL.ShapeIMUX,
                                        fillcolor=fill, style="filled")
                            
                    # PAE
                    # IMUXより下に置く
                    with l.subgraph(name="cluster_pae_lane{}".format(i)) as pg:
                        pg.graph_attr['rankdir'] = 'LR'
                        pg.graph_attr['rank'] = 'same'

                        for PAECell in lane.PAECells:
                            paename = PAECell.name

                            if paename in l_b_target:
                                fill = GL.ColorBind
                            else:
                                fill = GL.ColorPAECell

                            pg.node(paename, shape=GL.ShapePAECell,
                                    fillcolor=fill, style="filled")

                    # OMUX, skipOMUXを用意
                    with l.subgraph(name="cluster_omuxes_lane{}".format(i)) as osg:
                        osg.graph_attr['rankdir'] = 'LR'
                        osg.graph_attr['rank'] = 'sink'

                        with osg.subgraph(name="cluster_omux_lane{}".format(i)) as og:
                            og.graph_attr['rank'] = "min"
                            for omux in lane.OMUXes:
                                omuxname = omux.name

                                if omuxname in l_u_omux:
                                    fill = GL.ColorBind
                                else:
                                    fill = GL.ColorOMUX
                                    print(GL.ColorOMUX)

                                og.node(omuxname, shape=GL.ShapeOMUX,
                                        fillcolor=fill, style="filled")
                                
                        with osg.subgraph(name="cluster_somux_lane{}".format(i)) as sog:
                            sog.graph_attr['rank'] = "max"
                            for skipOMUX in lane.skipOMUXes:
                                omuxname = skipOMUX.name

                                if omuxname in l_u_omux:
                                    fill = GL.ColorBind
                                else:
                                    fill = GL.ColorSkipOMUX

                                sog.node(omuxname,shape=GL.ShapeSkipOMUX,
                                         fillcolor=fill, style="filled")

                # #####################
                # label subgraph l with
                # #####################

            # #####################
            # label LANE loop node
            # #####################

        # #####################
        # label subgraph r with
        # #####################

        for connectVar in connectVars:
            if connectVar.omux is not None:
                # .nameすると--で表示される接続
                src = connectVar.omux.name
                dst = connectVar.dst.name
                cellgraph.edge(src, dst, color=GL.ColorConnect)

                src = connectVar.src.paecell.name
                dst = connectVar.omux.name
                cellgraph.edge(src, dst, color=GL.ColorConnect)

            else:
                if isinstance(connectVar.src, PI):
                    src = connectVar.src.name
                if isinstance(connectVar.src, PAEOutput):
                    src = connectVar.src.paecell.name
                dst = connectVar.dst.name
                cellgraph.edge(src, dst, color=GL.ColorConnect)

            #別のif omuxの有無にかかわらず、imuxがdstであるパターンはある。
            #imuxからPAEへの接続(IMUXの要素から推定できる)
            if isinstance(connectVar.dst, IMUX):
                src = connectVar.dst.name
                dst = connectVar.dst.paecell.name
                cellgraph.edge(src, dst, color=GL.ColorConnect)

        # レイアウトのために、pae->omuxへの接続を1本ずつ作成(不可視にする)
        for i, lane in enumerate(self.lanes): # label LANE loop node
            for omux in lane.OMUXes:
                # OMUXとPAEが同一レーン内でのみ接続される前提の論理。
                # レーン外のPAEからOMUXに接続する可能性がある場合、拡張が必要
                # また、omuxのインプットの0番を決め打ちしている。
                src = omux.inputs[0].paecell.name
                dst = omux.name
                cellgraph.edge(src, dst, style="invis")

            for skipomux in lane.skipOMUXes:
                # OMUXとPAEが同一レーン内でのみ接続される前提の論理。
                # レーン外のPAEからOMUXに接続する可能性がある場合、拡張が必要
                # また、omuxのインプットの0番を決め打ちしている。
                src = skipomux.inputs[0].paecell.name
                dst = skipomux.name
                cellgraph.edge(src, dst, style="invis")
 
        cellgraph.render(filename)
'''
    
if __name__ == '__main__':
    main()
