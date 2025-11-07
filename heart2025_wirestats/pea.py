import itertools
import argparse
import subprocess
import math

import graphviz

import GraphLegends as GL

import re


# wire_statsの要素
class WireStat:
    def __init__(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum, count):
        self.src_x = src_x
        self.src_y = src_y
        self.src_outnum = src_outnum
        self.dst_x = dst_x
        self.dst_y = dst_y
        self.dst_innum = dst_innum
        self.count = count
        

class WireStats: # wire_stats.txtの入力ファイルから読み込んだデータを格納 (接続情報)
    def __init__(self, filename, count=1):
        self.stats = []
        self.readFromFile(filename, count)
    

    '''
    def readFromFile(self, filename, count): # ファイルから配線接続データの読み込み
        numTargetWires = 0
        with open(filename) as f:
            for line in f:
                l = line.split()
                for i, e in enumerate(l): # コメント削除
                    if '#' in e:
                        del l[i:]
                        break
                if len(l) == 0:
                    continue

                if int(l[6]) >= count:
                    numTargetWires+=1
                    il = [int(x) for x in l]
                    ws = WireStat(il[0], il[1], il[2], il[3], il[4], il[5], il[6])
                    self.stats.append(ws)

        print(f"numTargetWires={numTargetWires}")
        for s in self.stats:
            print(">>> src_x:{},src_y:{},src_outnum:{},dst_x:{},dst_y:{},dst_innum:{},count:{}".
                  format(s.src_x, s.src_y, s.src_outnum, s.dst_x, s.dst_y, s.dst_innum, s.count))
      '''

    def readFromFile(self, filename, count): # ファイルから配線接続データの読み込み
        numTargetWires = 0
        try:
            with open(filename) as f:
                for line in f:
                    try:
                        parts = [int(s) for s in line.split()]
                        # 行が7つの数字で構成されていることを確認
                        if len(parts) != 7:
                            continue

                        wire_count = parts[6]
                        if wire_count >= count:
                            numTargetWires += 1
                            # partsの最初の6つと最後の1つを引数として渡す
                            ws = WireStat(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], wire_count)
                            self.stats.append(ws)

                    except (ValueError, IndexError):
                        # 数字に変換できない行などは無視
                        continue
        except FileNotFoundError:
            print(f"Error: Statistics file '{filename}' not found.")

        print(f"numTargetWires={numTargetWires}")  


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
# eFPGA関係のクラス
# ------------------------------------------------------------------
        
class Interconnect:      # PEA Logic内の一本の配線
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
    def __init__(self, numPIs=8, numPOs=-1):
        self.lanes = []
        self.numPIs = numPIs
        self.numPOs = numPOs # 後でconnectPOs()で作成する場合、-1となっている
        self.PAEOutputs = []
        self.PAECells = []
        self.OMUXes = []
        self.skipOMUXes = []        
        self.IMUXes = []
        self.PIs = []
        self.POs = []
        self.Interconnects = []       # 配線のリスト
        self.buildPIs()
        if self.numPOs != -1:
            self.buildPOs()

    def connectPIs(self):
        #print("\nIn connectPIs")
        for pi in self.PIs:
            #print("\nIn connectPIs")
            #print(self.IMUXes)
            for imux in self.IMUXes:
                imux.inputs.append(pi)
                pi.dsts.append(imux)

                #print("\nconnectPIs: PI, IMUX show")
                #pi.show()
                #imux.show()


    def connectPItoMUX(self, pl,laneid, paeid, imuxid, pi_set):
        print("AAA")
        pl.lanes[laneid].PAECells[paeid].IMUXes[imuxid].inputs.extend(pi_set)
        [pi.dsts.append(pl.lanes[laneid].PAECells[paeid].IMUXes[imuxid]) for pi in pi_set]



                
    def connectPIsHEART(self, pl):
        print("\nIn connectPIsHEART")


        '''        
        half = len(self.PIs) // 2
        firstHalfPIs = self.PIs[:half+1]
        secondHalfPIs = self.PIs[half-1:]

        for pi in firstHalfPIs:        
            for pc in pl.lanes[0].PAECells:
                for imux in pc.IMUXes:
                    imux.inputs.append(pi)
                    pi.dsts.append(imux)

                    print("\nconnectPIsHEART (firstHalf): PI, IMUX show")
                    pi.show()
                    imux.show()
                    

        for pi in secondHalfPIs:                
            for pc in pl.lanes[1].PAECells:            
                for imux in pc.IMUXes:
                    imux.inputs.append(pi)
                    pi.dsts.append(imux)

                    print("\nconnectPIsHEART (secondHalf): PI, IMUX show")
                    pi.show()
                    imux.show()
        
        '''

        '''
        # 間引き接続A (13ビット入力版)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:13])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:15])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:16])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[4:17])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[5:18])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[6:19])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[7:20])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[8:21])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[9:22])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[11:24]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[12:25]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[13:26]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[14:27]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[15:28]) # 16 -> 13

        # laneid=1
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[16:29]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[17:30]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[18:31]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[19:32]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[20:33]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[21:34]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[22:35]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[23:36]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[24:36] + self.PIs[0:1])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[25:36] + self.PIs[0:2])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[26:36] + self.PIs[0:3])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[27:36] + self.PIs[0:4])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[28:36] + self.PIs[0:5])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[29:36] + self.PIs[0:6])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[0:7])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[0:8])  # 16 -> 13

        # laneid=2
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[0:9])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[0:10]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[0:11]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[0:12]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[0:13])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[2:15])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[3:16])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[4:17])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[5:18])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[6:19])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[7:20])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[8:21])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[9:22])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[11:24]) # 16 -> 13

        # laneid=3
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[12:25]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[13:26]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[14:27]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[15:28]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[16:29]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[17:30]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[18:31]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[19:32]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[20:33]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[21:34]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[22:35]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[23:36]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[24:36] + self.PIs[0:1])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[25:36] + self.PIs[0:2])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[26:36] + self.PIs[0:3])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[27:36] + self.PIs[0:4])  # 16 -> 13      
        '''


        '''
        # 間引き接続B (13ビット入力版)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:13])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:15])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:16])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[8:21])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[9:22])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[11:24]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[16:29]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[17:30]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[18:31]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[19:32]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[24:36] + self.PIs[0:1]) # Orig: 24:28 (4) -> New: 13 -> 24:36 + 0:1
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[13:26]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[14:27]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[15:28]) # 16 -> 13

        # laneid=1
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[16:29]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[17:30]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[18:31]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[19:32]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[20:33]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[21:34]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[22:35]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[23:36]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[24:36] + self.PIs[0:1])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[25:36] + self.PIs[0:2])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[26:36] + self.PIs[0:3])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[27:36] + self.PIs[0:4])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[28:36] + self.PIs[0:5])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[29:36] + self.PIs[0:6])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[0:7])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[0:8])  # 16 -> 13

        # laneid=2
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[0:9])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[0:10]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[0:11]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[0:12]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[0:13])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[2:15])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[3:16])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[4:17])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[5:18])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[6:19])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[7:20])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[8:21])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[9:22])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[11:24]) # 16 -> 13

        # laneid=3
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[12:25]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[13:26]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[14:27]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[15:28]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[16:29]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[17:30]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[18:31]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[19:32]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[20:33]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[21:34]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[22:35]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[23:36]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[24:36] + self.PIs[0:1])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[25:36] + self.PIs[0:2])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[26:36] + self.PIs[0:3])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[27:36] + self.PIs[0:4])  # 16 -> 13   
        '''        

        '''
        # 間引き接続C (13ビット入力版)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:13])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:15])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:16])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[4:17])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[5:18])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[6:19])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[7:20])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[8:21])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[9:22])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[11:24]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[12:25]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[13:26]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[14:27]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[15:28]) # 16 -> 13

        # laneid=1
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[23:36])               # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[24:36] + self.PIs[0:1])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[25:36] + self.PIs[0:2])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[26:36] + self.PIs[0:3])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[27:36] + self.PIs[0:4])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[28:36] + self.PIs[0:5])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[29:36] + self.PIs[0:6])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[30:36] + self.PIs[0:7])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[31:36] + self.PIs[0:8])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[32:36] + self.PIs[0:9])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[33:36] + self.PIs[0:10]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[34:36] + self.PIs[0:11]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[35:36] + self.PIs[0:12]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[0:13])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[2:15])  # 16 -> 13

        # laneid=2
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[11:24]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[12:25]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[13:26]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[14:27]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[15:28]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[16:29]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[17:30]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[18:31]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[19:32]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[20:33]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[21:34]) # 16 -> 13

        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[22:35]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[23:36]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[24:36] + self.PIs[0:1])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[25:36] + self.PIs[0:2])  # 16 -> 13

        # laneid=3
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[33:36] + self.PIs[0:10]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[34:36] + self.PIs[0:11]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[35:36] + self.PIs[0:12]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[0:13])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[1:14])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[2:15])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[3:16])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[4:17])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[5:18])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[6:19])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[7:20])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[8:21])  # 16 -> 13

        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[9:22])  # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[10:23]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[11:24]) # 16 -> 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[12:25]) # 16 -> 13
        '''
        '''
        #間引きD
        # 閾値2 & 合計32入力 を優先する接続パターン (元の形式、PIは0から順に割り当て)
        # --- laneid=0 ---
        # PAE0 (Int: 12, 13, 11, 13 -> Ext: 20, 19, 21, 19)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:20])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[20:36] + self.PIs[0:3]) # Ext: 19 (16+3)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[3:24])                 # Ext: 21
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[24:36] + self.PIs[0:7]) # Ext: 19 (12+7)
        # PAE1 (Int: 16, 14, 16, 22 -> Ext: 16, 18, 16, 10)
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[7:23])                 # Ext: 16
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[23:36] + self.PIs[0:5]) # Ext: 18 (13+5)
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[5:21])                 # Ext: 16
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[21:31])                # Ext: 10
        # PAE2 (Int: 15, 15, 14, 20 -> Ext: 17, 17, 18, 12)
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[31:36] + self.PIs[0:12])# Ext: 17 (5+12)
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[12:29])                # Ext: 17
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[29:36] + self.PIs[0:11])# Ext: 18 (7+11)
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[11:23])                # Ext: 12
        # PAE3 (Int: 13, 11, 12, 16 -> Ext: 19, 21, 20, 16)
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[23:36] + self.PIs[0:6]) # Ext: 19 (13+6)
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[6:27])                 # Ext: 21
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[27:36] + self.PIs[0:11])# Ext: 20 (9+11)
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[11:27])                # Ext: 16

        # --- laneid=1 ---
        # PAE4 (Int: 21, 22, 11, 14 -> Ext: 11, 10, 21, 18)
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[27:36] + self.PIs[0:2]) # Ext: 11 (9+2)
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[2:12])                 # Ext: 10
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[12:33])                # Ext: 21
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[33:36] + self.PIs[0:15])# Ext: 18 (3+15)
        # PAE5 (Int: 21, 25, 19, 19 -> Ext: 11, 7, 13, 13)
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[15:26])                # Ext: 11
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[26:33])                # Ext: 7
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[33:36] + self.PIs[0:10])# Ext: 13 (3+10)
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[10:23])                # Ext: 13
        # PAE6 (Int: 18, 21, 17, 20 -> Ext: 14, 11, 15, 12)
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[23:36] + self.PIs[0:1]) # Ext: 14 (13+1)
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[1:12])                 # Ext: 11
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[12:27])                # Ext: 15
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[27:36] + self.PIs[0:3]) # Ext: 12 (9+3)
        # PAE7 (Int: 18, 16, 10, 12 -> Ext: 14, 16, 22, 20)
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[3:17])                 # Ext: 14
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[17:33])                # Ext: 16
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[33:36] + self.PIs[0:19])# Ext: 22 (3+19)
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[19:36] + self.PIs[0:3]) # Ext: 20 (17+3)

        # --- laneid=2 ---
        # PAE8 (Int: 24, 26, 12, 14 -> Ext: 8, 6, 20, 18)
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[3:11])                 # Ext: 8
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[11:17])                # Ext: 6
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[17:36] + self.PIs[0:1]) # Ext: 20 (19+1)
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[1:19])                 # Ext: 18
        # PAE9 (Int: 25, 22, 21, 21 -> Ext: 7, 10, 11, 11)
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[19:26])                # Ext: 7
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[26:36])                # Ext: 10
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[0:11])                 # Ext: 11
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[11:22])                # Ext: 11
        # PAE10 (Int: 22, 22, 19, 21 -> Ext: 10, 10, 13, 11)
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[22:32])                # Ext: 10
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[32:36] + self.PIs[0:6]) # Ext: 10 (4+6)
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[6:19])                 # Ext: 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[19:30])                # Ext: 11
        # PAE11 (Int: 24, 21, 12, 15 -> Ext: 8, 11, 20, 17)
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[30:36] + self.PIs[0:2]) # Ext: 8 (6+2)
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[2:13])                 # Ext: 11
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[13:33])                # Ext: 20
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[33:36] + self.PIs[0:14])# Ext: 17 (3+14)

        # --- laneid=3 ---
        # PAE12 (Int: 28, 30, 19, 16 -> Ext: 4, 2, 13, 16)
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[14:18])                # Ext: 4
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[18:20])                # Ext: 2
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[20:33])                # Ext: 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[33:36] + self.PIs[0:13])# Ext: 16 (3+13)
        # PAE13 (Int: 22, 31, 24, 25 -> Ext: 10, 1, 8, 7)
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[13:23])                # Ext: 10
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[23:24])                # Ext: 1
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[24:32])                # Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[32:36] + self.PIs[0:3]) # Ext: 7 (4+3)
        # PAE14 (Int: 25, 27, 25, 24 -> Ext: 7, 5, 7, 8)
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[3:10])                 # Ext: 7
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[10:15])                # Ext: 5
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[15:22])                # Ext: 7
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[22:30])                # Ext: 8
        # PAE15 (Int: 19, 28, 22, 13 -> Ext: 13, 4, 10, 19)
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[30:36] + self.PIs[0:7]) # Ext: 13 (6+7)
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[7:11])                 # Ext: 4
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[11:21])                # Ext: 10
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[21:36] + self.PIs[0:4]) # Ext: 19 (15+4)
        '''
        '''
        #間引きE
        # 閾値2 & 合計32目標 (最低外部8) パターン (間引き接続Bの構造維持版)
        num_pis = 36
        target_total_inputs = 32
        min_external_inputs = 8

        # --- ヘルパー関数: 指定した開始位置から必要な数だけPIを取得 ---
        def get_pi_set_from_start(start_index, needed):
            if needed <= 0: return []
            start = start_index % num_pis # 開始位置をラップアラウンド対応
            end = start + needed
            if end <= num_pis:
                return self.PIs[start:end]
            else:
                # ラップアラウンドする場合
                return self.PIs[start:num_pis] + self.PIs[0:end % num_pis]

        # --- laneid=0 ---
        # PAE0 (Int: 12, 13, 11, 13 -> Ext needed: 20, 19, 21, 19)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(0, max(min_external_inputs, target_total_inputs - 12))) # Start: 0, Ext: 20
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(1, max(min_external_inputs, target_total_inputs - 13))) # Start: 1, Ext: 19
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(2, max(min_external_inputs, target_total_inputs - 11))) # Start: 2, Ext: 21
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(3, max(min_external_inputs, target_total_inputs - 13))) # Start: 3, Ext: 19
        # PAE1 (Int: 16, 14, 16, 22 -> Ext needed: 16, 18, 16, 10)
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(8, max(min_external_inputs, target_total_inputs - 16))) # Start: 8, Ext: 16
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(9, max(min_external_inputs, target_total_inputs - 14))) # Start: 9, Ext: 18
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(10, max(min_external_inputs, target_total_inputs - 16)))# Start: 10, Ext: 16
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(11, max(min_external_inputs, target_total_inputs - 22)))# Start: 11, Ext: 10
        # PAE2 (Int: 15, 15, 14, 20 -> Ext needed: 17, 17, 18, 12)
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 15)))# Start: 16, Ext: 17
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(17, max(min_external_inputs, target_total_inputs - 15)))# Start: 17, Ext: 17
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(18, max(min_external_inputs, target_total_inputs - 14)))# Start: 18, Ext: 18
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(19, max(min_external_inputs, target_total_inputs - 20)))# Start: 19, Ext: 12
        # PAE3 (Int: 13, 11, 12, 16 -> Ext needed: 19, 21, 20, 16)
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 13)))# Start: 24, Ext: 19
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(13, max(min_external_inputs, target_total_inputs - 11)))# Start: 13, Ext: 21
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(14, max(min_external_inputs, target_total_inputs - 12)))# Start: 14, Ext: 20
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(15, max(min_external_inputs, target_total_inputs - 16)))# Start: 15, Ext: 16

        # --- laneid=1 --- (Starts follow lane0 PAE2/3 pattern)
        # PAE4 (Int: 21, 22, 11, 14 -> Ext needed: 11, 10, 21, 18)
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 21)))# Start: 16, Ext: 11
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(17, max(min_external_inputs, target_total_inputs - 22)))# Start: 17, Ext: 10
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(18, max(min_external_inputs, target_total_inputs - 11)))# Start: 18, Ext: 21
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(19, max(min_external_inputs, target_total_inputs - 14)))# Start: 19, Ext: 18
        # PAE5 (Int: 21, 25, 19, 19 -> Ext needed: 11, 8, 13, 13)
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 21)))# Start: 24, Ext: 11
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(13, max(min_external_inputs, target_total_inputs - 25)))# Start: 13, Ext: 8
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(14, max(min_external_inputs, target_total_inputs - 19)))# Start: 14, Ext: 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(15, max(min_external_inputs, target_total_inputs - 19)))# Start: 15, Ext: 13
        # PAE6 (Int: 18, 21, 17, 20 -> Ext needed: 14, 11, 15, 12)
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 18)))# Start: 24, Ext: 14
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(25, max(min_external_inputs, target_total_inputs - 21)))# Start: 25, Ext: 11
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(26, max(min_external_inputs, target_total_inputs - 17)))# Start: 26, Ext: 15
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(27, max(min_external_inputs, target_total_inputs - 20)))# Start: 27, Ext: 12
        # PAE7 (Int: 18, 16, 10, 12 -> Ext needed: 14, 16, 22, 20)
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(28, max(min_external_inputs, target_total_inputs - 18)))# Start: 28, Ext: 14
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(29, max(min_external_inputs, target_total_inputs - 16)))# Start: 29, Ext: 16
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(30, max(min_external_inputs, target_total_inputs - 10)))# Start: 30, Ext: 22
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(31, max(min_external_inputs, target_total_inputs - 12)))# Start: 31, Ext: 20

        # --- laneid=2 --- (Starts shift by +16 compared to lane0 PAE0/1)
        # PAE8 (Int: 24, 26, 12, 14 -> Ext needed: 8, 8, 20, 18)
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 24)))# Start: 16, Ext: 8
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(17, max(min_external_inputs, target_total_inputs - 26)))# Start: 17, Ext: 8
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(18, max(min_external_inputs, target_total_inputs - 12)))# Start: 18, Ext: 20
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(19, max(min_external_inputs, target_total_inputs - 14)))# Start: 19, Ext: 18
        # PAE9 (Int: 25, 22, 21, 21 -> Ext needed: 8, 10, 11, 11)
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 25)))# Start: 24, Ext: 8
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(25, max(min_external_inputs, target_total_inputs - 22)))# Start: 25, Ext: 10
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(26, max(min_external_inputs, target_total_inputs - 21)))# Start: 26, Ext: 11
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(27, max(min_external_inputs, target_total_inputs - 21)))# Start: 27, Ext: 11
        # PAE10 (Int: 22, 22, 19, 21 -> Ext needed: 10, 10, 13, 11)
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(32, max(min_external_inputs, target_total_inputs - 22)))# Start: 32, Ext: 10
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(33, max(min_external_inputs, target_total_inputs - 22)))# Start: 33, Ext: 10
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(34, max(min_external_inputs, target_total_inputs - 19)))# Start: 34, Ext: 13
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(35, max(min_external_inputs, target_total_inputs - 21)))# Start: 35, Ext: 11
        # PAE11 (Int: 24, 21, 12, 15 -> Ext needed: 8, 11, 20, 17)
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(8, max(min_external_inputs, target_total_inputs - 24))) # Start: 8, Ext: 8
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(29, max(min_external_inputs, target_total_inputs - 21)))# Start: 29 (B Pattern), Ext: 11
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(30, max(min_external_inputs, target_total_inputs - 12)))# Start: 30 (B Pattern), Ext: 20
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(31, max(min_external_inputs, target_total_inputs - 15)))# Start: 31 (B Pattern), Ext: 17

        # --- laneid=3 --- (Starts follow lane2 PAE2/3 pattern)
        # PAE12 (Int: 28, 30, 19, 16 -> Ext needed: 8, 8, 13, 16)
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(8, max(min_external_inputs, target_total_inputs - 28))) # Start: 8, Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(9, max(min_external_inputs, target_total_inputs - 30))) # Start: 9, Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(10, max(min_external_inputs, target_total_inputs - 19)))# Start: 10, Ext: 13
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(11, max(min_external_inputs, target_total_inputs - 16)))# Start: 11, Ext: 16
        # PAE13 (Int: 22, 31, 24, 25 -> Ext needed: 10, 8, 8, 8)
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 22)))# Start: 16, Ext: 10
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(29, max(min_external_inputs, target_total_inputs - 31)))# Start: 29 (B Pattern), Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(30, max(min_external_inputs, target_total_inputs - 24)))# Start: 30 (B Pattern), Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(31, max(min_external_inputs, target_total_inputs - 25)))# Start: 31 (B Pattern), Ext: 8
        # PAE14 (Int: 25, 27, 25, 24 -> Ext needed: 8, 8, 8, 8)
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(20, max(min_external_inputs, target_total_inputs - 25)))# Start: 20, Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(21, max(min_external_inputs, target_total_inputs - 27)))# Start: 21, Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(22, max(min_external_inputs, target_total_inputs - 25)))# Start: 22, Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(23, max(min_external_inputs, target_total_inputs - 24)))# Start: 23, Ext: 8
        # PAE15 (Int: 19, 28, 22, 13 -> Ext needed: 13, 8, 10, 19)
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 19)))# Start: 24, Ext: 13
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(25, max(min_external_inputs, target_total_inputs - 28)))# Start: 25, Ext: 8
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(26, max(min_external_inputs, target_total_inputs - 22)))# Start: 26, Ext: 10
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(27, max(min_external_inputs, target_total_inputs - 13)))# Start: 27, Ext: 19
        '''

        
        #間引きF
        num_pis = 36 # self.PIs の総数
        target_total_inputs = 32 # MUXの目標合計サイズ
        min_external_inputs = 8  # どんなに混んでいても最低これだけはPIを接続する

        # --- ヘルパー関数: 指定した開始位置から必要な数だけPIを取得 ---
        def get_pi_set_from_start(start_index, needed):
            if needed <= 0: return []
            start = start_index % num_pis # 開始位置をラップアラウンド対応
            end = start + needed
            if end <= num_pis:
                return self.PIs[start:end]
            else:
                # ラップアラウンドする場合
                return self.PIs[start:num_pis] + self.PIs[0:end % num_pis]

        # --- 内部配線数データ (imux_usage_map) に基づいてコメントと計算式を更新 ---
        
        # --- laneid=0 ---
        # PAE0 (Int: 19, 20, 10, 11 -> Ext needed: 13, 12, 22, 21)
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(0, max(min_external_inputs, target_total_inputs - 19))) # Start: 0
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(1, max(min_external_inputs, target_total_inputs - 20))) # Start: 1
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(2, max(min_external_inputs, target_total_inputs - 10))) # Start: 2
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(3, max(min_external_inputs, target_total_inputs - 11))) # Start: 3
        # PAE1 (Int: 20, 16, 13, 18 -> Ext needed: 12, 16, 19, 14)
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(8, max(min_external_inputs, target_total_inputs - 20))) # Start: 8
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(9, max(min_external_inputs, target_total_inputs - 16))) # Start: 9
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(10, max(min_external_inputs, target_total_inputs - 13)))# Start: 10
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(11, max(min_external_inputs, target_total_inputs - 18)))# Start: 11
        # PAE2 (Int: 20, 15, 16, 16 -> Ext needed: 12, 17, 16, 16)
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 20)))# Start: 16
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(17, max(min_external_inputs, target_total_inputs - 15)))# Start: 17
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(18, max(min_external_inputs, target_total_inputs - 16)))# Start: 18
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(19, max(min_external_inputs, target_total_inputs - 16)))# Start: 19
        # PAE3 (Int: 22, 15, 6, 10 -> Ext needed: 10, 17, 26, 22)
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 22)))# Start: 24
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(13, max(min_external_inputs, target_total_inputs - 15)))# Start: 13
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(14, max(min_external_inputs, target_total_inputs - 6))) # Start: 14
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(15, max(min_external_inputs, target_total_inputs - 10)))# Start: 15

        # --- laneid=1 ---
        # PAE4 (Int: 21, 22, 13, 15 -> Ext needed: 11, 10, 19, 17)
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 21)))# Start: 16
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(17, max(min_external_inputs, target_total_inputs - 22)))# Start: 17
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(18, max(min_external_inputs, target_total_inputs - 13)))# Start: 18
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(19, max(min_external_inputs, target_total_inputs - 15)))# Start: 19
        # PAE5 (Int: 20, 25, 18, 17 -> Ext needed: 12, 8, 14, 15)
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 20)))# Start: 24
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(13, max(min_external_inputs, target_total_inputs - 25)))# Start: 13
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(14, max(min_external_inputs, target_total_inputs - 18)))# Start: 14
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(15, max(min_external_inputs, target_total_inputs - 17)))# Start: 15
        # PAE6 (Int: 17, 20, 17, 23 -> Ext needed: 15, 12, 15, 9)
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 17)))# Start: 24
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(25, max(min_external_inputs, target_total_inputs - 20)))# Start: 25
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(26, max(min_external_inputs, target_total_inputs - 17)))# Start: 26
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(27, max(min_external_inputs, target_total_inputs - 23)))# Start: 27
        # PAE7 (Int: 14, 22, 20, 19 -> Ext needed: 18, 10, 12, 13)
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(28, max(min_external_inputs, target_total_inputs - 14)))# Start: 28
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(29, max(min_external_inputs, target_total_inputs - 22)))# Start: 29
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(30, max(min_external_inputs, target_total_inputs - 20)))# Start: 30
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(31, max(min_external_inputs, target_total_inputs - 19)))# Start: 31

        # --- laneid=2 ---
        # PAE8 (Int: 21, 24, 16, 17 -> Ext needed: 11, 8, 16, 15)
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 21)))# Start: 16
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(17, max(min_external_inputs, target_total_inputs - 24)))# Start: 17
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(18, max(min_external_inputs, target_total_inputs - 16)))# Start: 18
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(19, max(min_external_inputs, target_total_inputs - 17)))# Start: 19
        # PAE9 (Int: 22, 24, 19, 20 -> Ext needed: 10, 8, 13, 12)
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 22)))# Start: 24
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(25, max(min_external_inputs, target_total_inputs - 24)))# Start: 25
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(26, max(min_external_inputs, target_total_inputs - 19)))# Start: 26
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(27, max(min_external_inputs, target_total_inputs - 20)))# Start: 27
        # PAE10 (Int: 25, 19, 21, 19 -> Ext needed: 8, 13, 11, 13)
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(32, max(min_external_inputs, target_total_inputs - 25)))# Start: 32
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(33, max(min_external_inputs, target_total_inputs - 19)))# Start: 33
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(34, max(min_external_inputs, target_total_inputs - 21)))# Start: 34
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(35, max(min_external_inputs, target_total_inputs - 19)))# Start: 35
        # PAE11 (Int: 22, 23, 18, 18 -> Ext needed: 10, 9, 14, 14)
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(8, max(min_external_inputs, target_total_inputs - 22))) # Start: 8
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(29, max(min_external_inputs, target_total_inputs - 23)))# Start: 29
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(30, max(min_external_inputs, target_total_inputs - 18)))# Start: 30
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(31, max(min_external_inputs, target_total_inputs - 18)))# Start: 31

        # --- laneid=3 ---
        # PAE12 (Int: 24, 29, 15, 20 -> Ext needed: 8, 8, 17, 12)
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=get_pi_set_from_start(8, max(min_external_inputs, target_total_inputs - 24))) # Start: 8
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=get_pi_set_from_start(9, max(min_external_inputs, target_total_inputs - 29))) # Start: 9
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=get_pi_set_from_start(10, max(min_external_inputs, target_total_inputs - 15)))# Start: 10
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=get_pi_set_from_start(11, max(min_external_inputs, target_total_inputs - 20)))# Start: 11
        # PAE13 (Int: 25, 34, 27, 22 -> Ext needed: 8, 8, 8, 10)
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=get_pi_set_from_start(16, max(min_external_inputs, target_total_inputs - 25)))# Start: 16
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=get_pi_set_from_start(29, max(min_external_inputs, target_total_inputs - 34)))# Start: 29
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=get_pi_set_from_start(30, max(min_external_inputs, target_total_inputs - 27)))# Start: 30
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=get_pi_set_from_start(31, max(min_external_inputs, target_total_inputs - 22)))# Start: 31
        # PAE14 (Int: 21, 24, 20, 17 -> Ext needed: 11, 8, 12, 15)
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=get_pi_set_from_start(20, max(min_external_inputs, target_total_inputs - 21)))# Start: 20
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=get_pi_set_from_start(21, max(min_external_inputs, target_total_inputs - 24)))# Start: 21
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=get_pi_set_from_start(22, max(min_external_inputs, target_total_inputs - 20)))# Start: 22
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=get_pi_set_from_start(23, max(min_external_inputs, target_total_inputs - 17)))# Start: 23
        # PAE15 (Int: 19, 27, 22, 16 -> Ext needed: 13, 8, 10, 16)
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=get_pi_set_from_start(24, max(min_external_inputs, target_total_inputs - 19)))# Start: 24
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=get_pi_set_from_start(25, max(min_external_inputs, target_total_inputs - 27)))# Start: 25
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=get_pi_set_from_start(26, max(min_external_inputs, target_total_inputs - 22)))# Start: 26
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=get_pi_set_from_start(27, max(min_external_inputs, target_total_inputs - 16)))# Start: 27
        

        '''
        # 間引き接続A'
        # laneid=0
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:8])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:9])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:10])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:11])
        
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[4:12])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[5:13])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[6:14])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[7:15])
        
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[9:17])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[10:18])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[11:19])

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[12:20])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[13:21])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[14:22])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[15:23])

        # laneid=1
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[17:25])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[18:26])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[19:27])
        
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[20:28])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[21:29])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[22:30])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[23:31])
        
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[24:32])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[25:33])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[26:34])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[27:35])
        
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[28:36])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[29:36] + self.PIs[:1])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[:2])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[:3])

        # laneid=2
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[:4])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[:5])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[:6])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[:7])
        
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[0:8])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[1:9])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[2:10])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[3:11])
        
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[4:12])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[5:13])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[6:14])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[7:15])
        
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[9:17])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[10:18])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[11:19])

        # laneid=3
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[12:20])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[13:21])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[14:22])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[15:23])
        
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[17:25])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[18:26])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[19:27])
        
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[20:28])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[21:29])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[22:30])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[23:31])
        
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[24:32])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[25:33])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[26:34])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[27:35])
        '''

        '''
        # 間引き接続B'
        # laneid=0
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:8])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:9])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:10])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:11])
        
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[9:17])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[10:18])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[11:19])
        
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[17:25])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[18:26])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[19:27])

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[24:32])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[25:33])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[26:34])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[27:35])

        # laneid=1
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[:4])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[:5])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[:6])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[:7])
        
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[4:12])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[5:13])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[6:14])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[7:15])
        
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[12:20])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[13:21])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[14:22])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[15:23])
        
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[20:28])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[21:29])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[22:30])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[23:31])

        # laneid=2
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[28:36])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[29:36] + self.PIs[:1])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[:2])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[:3])
        
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[0:8])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[1:9])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[2:10])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[3:11])
        
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[9:17])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[10:18])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[11:19])
        
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[17:25])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[18:26])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[19:27])

        # laneid=3
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[24:32])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[25:33])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[26:34])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[27:35])
        
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[:4])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[:5])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[:6])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[:7])
        
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[4:12])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[5:13])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[6:14])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[7:15])
        
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[12:20])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[13:21])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[14:22])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[15:23])
        '''

        '''
        # 間引き接続C’
        # laneid=0
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:8])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:9])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:10])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:11])
        
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[4:12])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[5:13])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[6:14])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[7:15])
        
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[9:17])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[10:18])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[11:19])

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[12:20])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[13:21])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[14:22])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[15:23])

        # laneid=1 (全体が8ビットずれる)
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[9:17])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[10:18])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[11:19])
        
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[12:20])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[13:21])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[14:22])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[15:23])
        
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[17:25])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[18:26])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[19:27])
        
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[20:28])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[21:29])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[22:30])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[23:31])

        # laneid=2 (さらに8ビットずれる)
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[17:25])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[18:26])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[19:27])
        
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[20:28])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[21:29])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[22:30])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[23:31])
        
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[24:32])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[25:33])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[26:34])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[27:35])
        
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[28:36])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[29:36] + self.PIs[:1])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[:2])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[:3])

        # laneid=3 (さらに8ビットずれる)
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[24:32])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[25:33])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[26:34])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[27:35])
        
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[28:36])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[29:36] + self.PIs[:1])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[:2])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[:3])
        
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[:4])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[:5])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[:6])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[:7])
        
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[0:8])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[1:9])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[2:10])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[3:11])
        '''
        '''
        # 間引き接続D'
        # laneid=0
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=0, pi_set=self.PIs[0:12])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=1, pi_set=self.PIs[1:12])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=2, pi_set=self.PIs[2:15])
        self.connectPItoMUX(pl, laneid=0, paeid=0, imuxid=3, pi_set=self.PIs[3:14])
        
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=0, pi_set=self.PIs[8:20])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=1, pi_set=self.PIs[9:23])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=2, pi_set=self.PIs[10:24])
        self.connectPItoMUX(pl, laneid=0, paeid=1, imuxid=3, pi_set=self.PIs[11:20])
        
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=0, pi_set=self.PIs[16:28])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=1, pi_set=self.PIs[17:29])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=2, pi_set=self.PIs[18:30])
        self.connectPItoMUX(pl, laneid=0, paeid=2, imuxid=3, pi_set=self.PIs[19:28])

        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=0, pi_set=self.PIs[24:36])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=1, pi_set=self.PIs[25:36]+ self.PIs[:1])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=2, pi_set=self.PIs[26:36]+ self.PIs[:1])
        self.connectPItoMUX(pl, laneid=0, paeid=3, imuxid=3, pi_set=self.PIs[27:36]+ self.PIs[:2])

        # laneid=1
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=0, pi_set=self.PIs[32:36] + self.PIs[:4])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=1, pi_set=self.PIs[33:36] + self.PIs[:3])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[:9])
        self.connectPItoMUX(pl, laneid=1, paeid=0, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[:12])
        
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=0, pi_set=self.PIs[4:7])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=1, pi_set=self.PIs[5:9])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=2, pi_set=self.PIs[6:16])
        self.connectPItoMUX(pl, laneid=1, paeid=1, imuxid=3, pi_set=self.PIs[7:16])
        
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=0, pi_set=self.PIs[12:19])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=1, pi_set=self.PIs[13:16])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=2, pi_set=self.PIs[14:23])
        self.connectPItoMUX(pl, laneid=1, paeid=2, imuxid=3, pi_set=self.PIs[15:25])
        
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=0, pi_set=self.PIs[20:28])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=1, pi_set=self.PIs[21:28])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=2, pi_set=self.PIs[22:34])
        self.connectPItoMUX(pl, laneid=1, paeid=3, imuxid=3, pi_set=self.PIs[23:34])

        # laneid=2
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=0, pi_set=self.PIs[28:30])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=1, pi_set=self.PIs[29:35])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=2, pi_set=self.PIs[30:36] + self.PIs[:4])
        self.connectPItoMUX(pl, laneid=2, paeid=0, imuxid=3, pi_set=self.PIs[31:36] + self.PIs[:6])
        
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=0, pi_set=self.PIs[0:5])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=1, pi_set=self.PIs[1:5])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=2, pi_set=self.PIs[2:9])
        self.connectPItoMUX(pl, laneid=2, paeid=1, imuxid=3, pi_set=self.PIs[3:13])
        
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=0, pi_set=self.PIs[8:16])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=1, pi_set=self.PIs[9:14])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=2, pi_set=self.PIs[10:16])
        self.connectPItoMUX(pl, laneid=2, paeid=2, imuxid=3, pi_set=self.PIs[11:19])
        
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=0, pi_set=self.PIs[16:24])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=1, pi_set=self.PIs[17:23])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=2, pi_set=self.PIs[18:29])
        self.connectPItoMUX(pl, laneid=2, paeid=3, imuxid=3, pi_set=self.PIs[19:29])

        # laneid=3
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=0, pi_set=self.PIs[24:26])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=1, pi_set=self.PIs[25:29])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=2, pi_set=self.PIs[26:36]+ self.PIs[:1])
        self.connectPItoMUX(pl, laneid=3, paeid=0, imuxid=3, pi_set=self.PIs[27:36]+ self.PIs[:1])
        
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=0, pi_set=self.PIs[32:35])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=1, pi_set=self.PIs[33:33])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=2, pi_set=self.PIs[34:36] + self.PIs[:5])
        self.connectPItoMUX(pl, laneid=3, paeid=1, imuxid=3, pi_set=self.PIs[35:36] + self.PIs[:6])
        
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=0, pi_set=self.PIs[4:10])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=1, pi_set=self.PIs[5:6])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=2, pi_set=self.PIs[6:10])
        self.connectPItoMUX(pl, laneid=3, paeid=2, imuxid=3, pi_set=self.PIs[7:12])
        
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=0, pi_set=self.PIs[12:17])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=1, pi_set=self.PIs[13:16])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=2, pi_set=self.PIs[14:26])
        self.connectPItoMUX(pl, laneid=3, paeid=3, imuxid=3, pi_set=self.PIs[15:27])
        '''
         
    def connectPAEs(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum):

        if src_y > len(self.lanes) or dst_y > len(self.lanes):
            print("connectPAEs: src_y, dst_y larger than len(lanes)")
            exit()
        if src_x > len(self.lanes[src_y].PAECells) or dst_x > len(self.lanes[dst_y].PAECells):
            print("connectPAEs: src_x, dst_x larger than len(PAECells)")
            exit()
        srcPAE = self.lanes[src_y].PAECells[src_x];
        dstPAE = self.lanes[dst_y].PAECells[dst_x];

        #print(f"srcPAE:{srcPAE}")
        #srcPAE.show()
        #print(f"dstPAE:{dstPAE}")
        #dstPAE.show()


        for output in srcPAE.outputs:
            output.show()
        
        
        omux = None
        for dst in srcPAE.outputs[src_outnum].dsts:
            if type(dst) is OMUX and dst.skipLengths is None:
                omux = dst
        if omux is None:
            print("1-input OMUX not attached to PAE output")
            exit()

        #print("OMUX show")
        #omux.show()

        imux = dstPAE.IMUXes[dst_innum]

        #print("\nIMUX show")
        #imux.show()
        
        imux.inputs.append(omux)
        omux.dsts.append(imux)

            
    def buildPIs(self): # 外部出力を作成
        print(f"building PIs {self.numPIs}")
        for i in range(self.numPIs):
            print("appending PI")
            pi = PI()
            pi.show()
            self.PIs.append(pi)

    def buildPOs(self): # 外部出力を作成
        for i in range(self.numPOs):
            self.POs.append(PO())

    # 以下のコピーは重複していた (generateAndconnectPOsに同じことをしていた)
    #def copyPAECellsFromLanes(self): # レーンのPAECell情報コピー(参照のため)
    #    for l in self.lanes:
    #        for paecell in l.PAECells:
    #            self.PAECells.append(paecell)
                
        #for p in self.PAECells:
        #    p.show()
        
    def addLane(self, lane):
        self.lanes.append(lane)


    # PEAの出力を、引数指定の外部出力POに接続
    def generateAndconnectPOs(self, directOutput=True, outputLastLane=False):

        # 重複して各種リストに追加しないように、チェックを追加した
        
        # 前準備(PAEOutputs, OMUXes, IMUXesを準備) (TODO: 別の場所に移動し、呼び出し順依存を減らす)
        for l in self.lanes:
            l.show()
            for omux in l.OMUXes:
                omux.show()
                if omux not in self.OMUXes:
                    self.OMUXes.append(omux)
                
            for skipomux in l.skipOMUXes: # 忘れていた
                skipomux.show()
                if skipomux not in self.skipOMUXes:
                    self.skipOMUXes.append(skipomux)
            
            for pc in l.PAECells:
                if pc not in self.PAECells:
                    self.PAECells.append(pc)
                print("show PAECell")
                pc.show()
                for o in pc.outputs:
                    if o not in self.PAEOutputs:
                        self.PAEOutputs.append(o)
                for i in pc.IMUXes:
                    if i not in self.IMUXes:                    
                        self.IMUXes.append(i)                    

        # directOutput=True: laneのPAEの出力を、出力MUXを通さずそのまま外部出力に出す
        # outputLastLane=True: 最後のレーンの出力のみPOに接続
        #                False:すべてのレーンの出力をPOに接続
        if directOutput == True:
            PAEOutputs = []
            if outputLastLane == True:
                # 最後のレーンの出力のみを、POに接続
                lastLane = self.lanes[-1]
                for p in lastLane.PAECells:
                    for o in p.outputs:
                        PAEOutputs.append(o)

            elif outputLastLane == False:
                # すべてのレーンの出力を、POに接続

                for p in self.PAECells:
                    p.show()
                    for o in p.outputs:
                        PAEOutputs.append(o)

            #print("PAEOutputs in generateAndconnectPOs begin")
            #for o in PAEOutputs:
            #    o.show()
            #print("PAEOutputs in generateAndconnectPOs end")
                        
            for o in PAEOutputs:
                po = PO()
                self.POs.append(po)
                o.dsts.append(po)
                po.srcs.append(o)
                
        else:
            # TODO: directOutput=Falseの場合の実装
            # もともと事前にPOが生成されているので、それらに、PEAの出力を接続する
            pass

        
    
    def enumerateInterconnects(self):  # PEA Logic中の接続をすべて列挙

        #list = self.PAEOutputs + self.OMUXes + self.IMUXes
        #for i in list:
        #    i.show()
                    
        # OMUXを通す場合の配線を列挙  (src -> omux -> dst)

        for omux in self.OMUXes:
            for s in omux.inputs:
                for d in omux.dsts:
                    self.Interconnects.append(Interconnect(s, omux, d))


        # 忘れていた! SkipMUXを通す場合の配線を列挙 (src -> skipMux -> dst)

        for skipomux in self.skipOMUXes:
            for s in skipomux.inputs:
                for d in skipomux.dsts:
                    self.Interconnects.append(Interconnect(s, skipomux, d))
                    

        # OMUXを通さない場合の配線を列挙  (src -> dst)
        # PI -> IMUX 
        for pi in self.PIs:
            for d in pi.dsts:
                if type(d) is IMUX or type(d) is PO:
                    self.Interconnects.append(Interconnect(pi, None, d))

        for o in self.PAEOutputs:
            for d in o.dsts:
                if type(d) is PO:
                    self.Interconnects.append(Interconnect(o, None, d))

        #self.copyPAECellsFromLanes() # ついでにLaneのPAECell情報を集めておく => 別の場所で済み
                    
        for ic in self.Interconnects:
            ic.show()
            
'''
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
                    

class Lane:
    count = 0
    def __init__(self, nPAECells=4, nIMUXins=4, nOMUXes=6, nOMUXins=2, nPAEin=4, nPAEout=3, noOMUX=False, nSkipOMUXes=4, skips = None):
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
        self.skips = skips         # フィードバック/フィードフォワードの設定(skipするリスト)
        self.nSkipOMUXes = nSkipOMUXes # フィードバック/フィードフォワード用の出力MUX数
        self.skipOMUXes = []       # フィードバック/フィードフォワード用の出力MUXのリスト
        #self.nOMUXes = nPAEout * nPAECells # PAE Cellの出力数3×PAE Cell数に設定（OMUX無しにするため）
        self.buildPAECells(nPAECells, nPAEin, nPAEout)
        if noOMUX == False:
            self.buildOMUXes(nOMUXes)
            self.connectPAEOutputToOMUX()
        if skips != None:
            self.buildSkipOMUXes(skips)
            self.connectPAEOutputToSkipOMUX()
#        OMUX.count = 0         # カウンタをリセット

    def buildPAECells(self, nPAECells, nPAEin, nPAEout):   # レーン内にPAEセルを作る
        for i in range(nPAECells):
            print(f"nPAEout = {nPAEout}")
            self.PAECells.append(PAECell(self, nPAEin, nPAEout))
        #PAECell.count = 0      # カウンタをリセット
    

    def buildOMUXes(self,nOMUXes):     # レーン内に出力MUXを作る
        for i in range(nOMUXes):
            self.OMUXes.append(OMUX(self))

    # 出力MUXの入力にPAEセルの出力を接続する
    # fullConnection = True: 完全接続, False: 部分接続
    #def connectPAEOutputToOMUX(self, fullConnection = True, noOMUX = True):
    def connectPAEOutputToOMUX(self, fullConnection = False, noOMUX = True):         
        print("##### connectPAEOutputToOMUX() ####")
        outputs = []
        for p in self.PAECells:
            for o in p.outputs:
                outputs.append(o)

        if fullConnection is True:
            for i, omux in enumerate(self.OMUXes):
                for o in outputs:
                    omux.inputs.append(o)
                    o.dsts.append(omux)
                    
        elif noOMUX is True: # OMUXを付けない場合、1入力のOMUXを用意する                    

            for i, omux in enumerate(self.OMUXes):
                omux.inputs.append(outputs[i])
                outputs[i].dsts.append(omux)
            
        else :
            # OMUXがM個(nOMUXes)で、PAE出力がN個(nPAEout*nPAECells)とする。
            # M個のOMUXで、N個の出力を分けるので、
            # OMUX 1個あたりに接続されるPAE出力は、N/M個。割り切れない場合は、
            # 整数に切り上げ(ceil[N/M])、数は等しくならない(ceil[N/M]-1)が発生、それでOK。
            # オリジナル例題: OMUX6個、PAE出力が12個で、12/6=2個
            # 例： OMUXが4個、PAE出力が12個なら、12/4=3個
            # 例： OMUXが2個、PAE出力が6個なら、6/2=3個
            # 例： OMUXが3個、PAE出力が6個なら、6/3=2個
            # 連続するsize = ceil[N/M]個の出力を、尽きるまで、OMUXにつなげる。

            N = self.nPAEout * self.nPAECells

            size = math.ceil(N/self.nOMUXes)
            
            count = 0
            finish = False
            for i, omux in enumerate(self.OMUXes):
                for j in range(size):
                    if count == len(outputs):
                        finish = True
                        break
                    
                    omux.inputs.append(outputs[size*i+j])
                    outputs[size*i+j].dsts.append(omux)
                    count += 1
                    if finish == True:
                        break
            
    def buildSkipOMUXes(self,skips): # フィードバック/フィードフォワード用の出力MUXを作る
        for i in range(self.nSkipOMUXes):        
            self.skipOMUXes.append(OMUX(self, skipLengths=skips))
        #OMUX.count = 0         # カウンタをリセット            

    def connectPAEOutputToSkipOMUX(self): # skip出力MUXの入力にPAEセルの出力を接続する
        print("##### connectPAEOutputToSkipOMUX() ####")
        outputs = []
        for p in self.PAECells:
            for o in p.outputs:
                outputs.append(o)

        # ここでは、PAE出力をすべて、一つのSkipOMUXに接続する形とした
        # TODO: 他の接続形式のSkipOMUXの検討・実装
        for i, omux in enumerate(self.skipOMUXes):
            for o in outputs:
                omux.inputs.append(o)
                o.dsts.append(omux)

    # 引数に指定したlaneの出力/外部入力(src)を、このlaneの入力に接続
    # fullConnection : True 完全接続, False 部分入力(ex. ずらしながら接続する方式)
    #def connect(self, srcs, fullConnection = True):
    def connect(self, srcs, fullConnection = False):         

        if fullConnection is True:
            # すべての入力/出力MUXを、このlaneの各PAEセルの入力に接続
            # 入力MUXの入力数制約は、無視する
            for i, p in enumerate(self.PAECells):
                for j, m in enumerate(p.IMUXes):
                    for s in srcs:
                        m.inputs.append(s)
                        s.dsts.append(m)
        else :
            # srcsに対して、一つずつずらしながら接続する方式
            # 必要なパラメータ： 1. 入力MUXの入力数nIMUXins, 
            #                    2. srcsの要素数N(前のレーンの出力数、または外部入力数)
            # パラメータ1,2に応じて、処理を行う
            nIMUXins = self.nIMUXins
            N = len(srcs)                                           #srcs:セルからの出力、あるいは外部入力

            for i, p in enumerate(self.PAECells):                   #i:レーン   p:paeセル
                for j, m in enumerate(p.IMUXes):                    #j:m:マルチプレクサ
                    for k in range(nIMUXins):                       #k：マルチプレクサへの４つの入力
                        m.inputs.append(srcs[(nIMUXins*i+j+k)%N])                    
                        srcs[(nIMUXins*i+j+k)%N].dsts.append(m)


                    
    # フィードバック/フィードフォワード接続をつなげる。lanesはレーンのリスト
    # lanes[0]: 初段、lanes[1]:次段, ....
    def connectSkips(self, lanes):

        # TODO?: 任意のskipOMUXを、外部出力に出力できるよう、修正
        for m in self.skipOMUXes: # ループを回しているが、現時点では1個のみ
            for l in m.skipLengths:
                # 現在のレーン番号(self.count)を基準にして、どのレーンに接続するか決定
                dstLane = lanes[self.count+l] # 接続先のレーン
                # skipOMUXを、接続先レーンのすべてのIMUXに接続する
                for p in dstLane.PAECells:
                    for im in p.IMUXes:
                        im.inputs.append(m)
                        m.dsts.append(im)

    # 引数指定の外部出力POを、このlaneの出力に接続
    # 廃止 (PEALogicに移動）
    """
    def connectPOs(self, POs, directOutput=True, outputLastLane=False): 
        # directOutput=True: laneのPAEの出力を、出力MUXを通さずそのまま外部出力に出す
        # outputLastLane=True: 最後のレーンの出力のみPOに接続する。
        #                False:すべてのレーンの出力をPOに接続する
        if directOutput == True and outputLastLane == True:
            # 最後のレーンの出力を、POに接続
            assert self.nPAECells * self.nPAEout == len(POs), PAEの総出力数とPO数が異なります
:
            PAEOutputs = []
            for p in self.PAECells:
                for o in p.outputs:
                    PAEOutputs.append(o)

            for i, o in enumerate(PAEOutputs):
                o.dsts.append(POs[i])
                POs[i].srcs.append(o)
                
            #for o in PAEOutputs:
            #    o.show()

        elif directOutput == True and outputLastLane == False:
            # すべてのレーンの出力を、POに接続
            pass
        else:
            # TODO: directOutput=Falseの場合の実装
            pass
    """

                    
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
        
    def showSkips(self): #フィードバック/フィードフォワードの設定を表示
        print("Showing skips for lane{}".format(self.count))
        for i, s in enumerate(self.skips):
            print("skip length[{}]:{}".format(i,s))

    def showSkipOMUXes(self): #フィードバック/フィードフォワード用OMUXを表示
        print("Showing skipOMUXes for lane{}".format(self.count))
        print("Show begin")
        for i, s in enumerate(self.skipOMUXes):
            s.show()
        print("Show end")



        

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
        self.src.show()
        print(" -> ",end="")
        self.dst.show()
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

    def writeDot(self): # graphviz向けに、グラフを出力
        with open('sample.dot', 'w') as f:
            str = "digraph netlist {\n"
            f.write(str)
            for e in self.edges:
                if type(e.src) == PAEInstanceOutput:
                    srcname = e.src.PAEInstance.name
                else:
                    print(type(e.src))
                    assert(type(e.src) == NetlistPI)
                    srcname = e.src.name

                if type(e.dst) == PAEInstanceInput:
                    dstname = e.dst.PAEInstance.name
                else:
                    print(type(e.dst))
                    assert(type(e.dst) == NetlistPO)
                    dstname = e.dst.name
                    
                
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
                

        for e in self.edges:
            e.show()

        for p in self.PAEInstances.values():
            p.showFanouts()
                

        
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
        assert("Invalid input argumet at PAEInstanceOrPIPO()")
        

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
        assert("Invalid input argumet at bindingPort()")
    

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

        command = ['kissat', '--time=3', '--no-binary', 'sample.cnf']        
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

        #return # コメントアウト　2024/12/23 配線評価のため        
        for e in self.Netlist.edges:
            src = e.src
            dst = e.dst

            srcInst = PAEInstanceOrPIPO(src)
            dstInst = PAEInstanceOrPIPO(dst)

            #print("--- src of edge")
            #src.show()
            #print("")
            #srcInst.show()
            #print(srcInst.name)

            #print("--- dst of edge")
            #dst.show()
            #print("")            
            #dstInst.show()
            #print("")            
            #print(dstInst.name)
            #print("")

            #srcInst, dstInstのバインド候補を列挙できるはず。
            #bind変数のキーをチェックする。
            #srcInst, dstInstを第一のキーとして、bind変数の辞書をチェックし、
            #第二のキーが、バインド結果の候補となる。
            #Bind変数を作るときのように、PAECells, PIs, POsを列挙する。
            
            #srcInstのバインド候補の列挙
            #print("srcBindings & BindingPorts")
            srcBindings = [] # srcInstのバインド候補のPAECell, PI/PO
            srcBindingPorts = [] # バインド候補のPAECellのポート, PI/PO
            for k, v in self.BindVars.items():
                if k[0] == srcInst:
                    srcBindings.append(k[1])
                    srcBindingPort = bindingPort(src, k[1])
                    srcBindingPorts.append(srcBindingPort)
                    #k[1].show()
                    #srcBindingPort.show()

            #print("dstBindings & BindingPorts")                    
            #srcInstのバインド候補の列挙
            dstBindings = [] # dstInstのバインド候補のPAECell, PI/PO
            dstBindingPorts = [] # バインド候補のPAECellのポート, PI/PO
            for k, v in self.BindVars.items():
                if k[0] == dstInst:
                    dstBindings.append(k[1])
                    dstBindingPort = bindingPort(dst, k[1])
                    dstBindingPorts.append(dstBindingPort)
                    #dstBindingPort.show()

            for j1, srcBinding in enumerate(srcBindings):
                for j2, dstBinding in enumerate(dstBindings):

                    #print("in j1&j2 loop")

                    srcBindingPort = srcBindingPorts[j1]
                    dstBindingPort = dstBindingPorts[j2]

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

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='ネットリストのファイル名(独自形式)')
    parser.add_argument('--ws_count', type=int, default=1, help='配線ヒストグラムファイルでの配線数の下限値')
    args = parser.parse_args()
    print('file='+args.file)
    print('ws_count=' + str(args.ws_count))    
    
    # build PAE logic
    pl = PEALogic(numPIs=36)
    #pl = PEALogic(numPIs=24)    

    # レーンを作る

    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[3, 2 , 1 ,0], nOMUXes=12, nSkipOMUXes=0, nPAEout=3)) #デフォルトでnoOMUX=True,nPAEin=4は入ってるので設定していない
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[2, 1, 0, -1], nOMUXes=12, nSkipOMUXes=0, nPAEout=3))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[1, 0,-1, -2], nOMUXes=12, nSkipOMUXes=0, nPAEout=3))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0, -1, -2, -3], nOMUXes=12, nSkipOMUXes=0, nPAEout=3))

    '''
    # フィードバック/フィードフォワード接続をつなげる
    pl.lanes[0].connectSkips(pl.lanes)
    pl.lanes[1].connectSkips(pl.lanes)
    pl.lanes[2].connectSkips(pl.lanes)
    pl.lanes[3].connectSkips(pl.lanes)
    '''

    '''
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0], nOMUXes=6, nSkipOMUXes=2))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0,-1], nOMUXes=6, nSkipOMUXes=3))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0,-1], nOMUXes=6, nSkipOMUXes=3))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, nOMUXes=0, skips=[-2,-1], nSkipOMUXes=3, noOMUX=True))        
    '''

    # 接続を記述したファイルを読み込む
    # ただし、countが特定の値以上のもののみ、読み込む
    # 配線接続情報を外部ファイルから読み込む (countが5以上) 2024/12/9
    
    print(f"ws_count: {args.ws_count}")
    wirestats = WireStats("wire_stats.txt", args.ws_count)                      

    # 読み込んだwireStatsを元に、PAEを接続する。
    # wirestatsにかかれている接続を１本ずつつなぐ
    # PAELogicクラスに対して、操作する

    for ws in wirestats.stats:
        print("\nws: >>> src_x:{},src_y:{},src_outnum:{},dst_x:{},dst_y:{},dst_innum:{},count:{}".
              format(ws.src_x, ws.src_y, ws.src_outnum, ws.dst_x, ws.dst_y, ws.dst_innum, ws.count))
        pl.connectPAEs(ws.src_x, ws.src_y, ws.src_outnum, ws.dst_x, ws.dst_y, ws.dst_innum)
        
    
    '''
    pl.lanes[1].connect(pl.lanes[0].OMUXes)
    pl.lanes[2].connect(pl.lanes[1].OMUXes)
    pl.lanes[3].connect(pl.lanes[2].OMUXes)
    '''

    '''
    # 外部入力をレーンに接続
    pl.lanes[0].connect(pl.PIs)
    pl.lanes[1].connect(pl.PIs)
    pl.lanes[2].connect(pl.PIs)
    pl.lanes[3].connect(pl.PIs)
    '''

    # 以下のコメントアウトを外すと、SAT解が得られる。
    '''
    # レーンを作る
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0], nOMUXes=6, nSkipOMUXes=2))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0,-1], nOMUXes=6, nSkipOMUXes=3))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, skips=[0,-1], nOMUXes=6, nSkipOMUXes=3))
    pl.addLane(Lane(nIMUXins=4, nPAECells=4, nOMUXes=0, skips=[-2,-1], nSkipOMUXes=3, noOMUX=True))        

    
    # 隣接するレーン間を接続する
    pl.lanes[1].connect(pl.lanes[0].OMUXes)
    pl.lanes[2].connect(pl.lanes[1].OMUXes)
    pl.lanes[3].connect(pl.lanes[2].OMUXes)    

    # フィードバック/フィードフォワード接続をつなげる
    pl.lanes[0].connectSkips(pl.lanes)
    pl.lanes[1].connectSkips(pl.lanes)
    pl.lanes[2].connectSkips(pl.lanes)
    pl.lanes[3].connectSkips(pl.lanes)    

    # 外部入力をレーンに接続
    pl.lanes[0].connect(pl.PIs)
    pl.lanes[1].connect(pl.PIs)
    pl.lanes[2].connect(pl.PIs)
    pl.lanes[3].connect(pl.PIs)
    '''

    pl.generateAndconnectPOs(directOutput=True, outputLastLane=False)
    #pl.connectPIs()

    pl.connectPIsHEART(pl)
    
    # フィードバック/フィードフォワード接続後(すべて接続後)の接続を表示
    #pl.lanes[0].showConnections()
    #pl.lanes[1].showConnections()


    #pl.lanes[0].show()
    #pl.lanes[1].show()

    #pl.saveGraph_AC(filename="cell_graph_all_connection") # 接続が全表示されるグラフ


    # -------------------------------------------------------------------
    # 入力ネットリストを読み込み
    
    netlistFile = args.file
    netlist = Netlist(netlistFile)

    # SAT式を作る準備をする

    # まずは、PAE logicにネットリストがマッピングできるか、簡単なチェック
    # PI/POが足りているか。PAEの数が足りているか。
    print(f"In netlist, numPIs={netlist.numPIs}, numPOs={netlist.numPOs}")
    #if pl.numPIs < netlist.numPIs or pl.numPOs < netlist.numPOs:

    #print(f"DEBUG: Checking PI counts -> Model PIs (pl.numPIs) = {pl.numPIs}, Netlist PIs (netlist.numPIs) = {netlist.numPIs}")
    if pl.numPIs < netlist.numPIs:
        print("not enough numPI")
        exit()
    totalNumPAECells = 0
    for l in pl.lanes:
        totalNumPAECells += l.nPAECells
    print(f"totalNumPAECells = {totalNumPAECells}")
    print(f"totalNumPAEInstances = {len(netlist.PAEInstances)}")
    if totalNumPAECells < len(netlist.PAEInstances):
        print("not enough PAECells")
        exit()

    # SAT式を作るために、PEA Logicの配線を列挙する
    pl.enumerateInterconnects()

    # ネットリストをgraphvizに出力

    # SAT式を作って解く
    satmgr = SATmgr(pl, netlist)

    #trueVars = satmgr.readSATResult()
    trueVars = satmgr.readSATResultKissat()    

    if len(trueVars) == 0:
        print("P&R solution not found")
        exit()


        
    # satの結果が強調されるグラフ
    #pl.saveGraph(filename="cell_graph_p_and_r", 
    #             trueVars=trueVars)
    #
    #print(len(pl.POs))

    # コンフィギュレーションビットの総数を計算
    
    numConfBits = 0
    
    for m in pl.IMUXes:
        m.show()
        print("numMUXinputs: {}, numConfBits: {}".format(len(m.inputs), m.numConfBits()))
        numConfBits += m.numConfBits()

    print("IMUX: numConfBits={}".format(numConfBits))        

    '''
    for m in pl.OMUXes:
        m.show()
        print("numMUXinputs: {}, numConfBits: {}".format(len(m.inputs), m.numConfBits()))
        numConfBits += m.numConfBits()

    print("IMUX+OMUX: numConfBits={}".format(numConfBits))                
    '''

    for m in pl.skipOMUXes:
        m.show()
        print("skipOMUX: numMUXinputs: {}, numConfBits: {}".format(len(m.inputs), m.numConfBits()))
        numConfBits += m.numConfBits()

    #print("IMUX+OMUX+skipMUX: numConfBits={}".format(numConfBits))                        

    #print("#PAEs: {}, PAE Conf bits: {}".format(len(pl.PAECells), len(pl.PAECells)*8))
    #numConfBits += len(pl.PAECells)*8
        
        
    print("numConfBits={}".format(numConfBits))
    
    
    
    
if __name__ == '__main__':
    main()
