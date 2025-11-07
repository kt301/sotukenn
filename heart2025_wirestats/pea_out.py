import itertools
import argparse
import subprocess
import math
import graphviz
import GraphLegends as GL # (GraphLegends.pyが同じディレクトリにある前提)
import re
import os # ★ os をインポート
from collections import defaultdict # ★ defaultdict をインポート

# ==================================================================
# ★ ブロック1: 従来の pea.py のクラス定義群 ★
# (WireStatsクラスは不要になったので削除)
# ==================================================================

# --- WireStatクラスは不要 ---

class PI: # PEA論理(レーンの集合)への外部入力
    count = 0    
    def __init__(self):
        self.count = PI.count  # PIのID番号
        PI.count += 1      
        self.name = self.name()
        self.dsts = [] # PIの接続先(IMUX)
    def name(self):
        return f"I{self.count}"
    def show(self):
        print(f"Primary Input {self.name}")

class PO: # PEA論理(レーンの集合)からの外部出力
    count = 0
    def __init__(self):
        self.count = PO.count  # POのID番号
        PO.count += 1
        self.name = self.name()
        self.srcs = [] # POの接続元(PEAOutput/OMUX)
    def name(self):
        return f"O{self.count}"
    def show(self):
        print(f"Primary Output {self.name}")

class IMUX: # PAEセルの入力に付加される入力MUX
    def __init__(self, paecell, inputNum, maxIn=4):
        self.inputs = []       
        self.maxIn = maxIn       
        self.paecell = paecell   
        self.inputNum = inputNum 
        self.name = self.name()
    def numConfBits(self): 
        if len(self.inputs) <= 1: return 0 # 1入力は配線とみなす
        return math.ceil(math.log2(len(self.inputs)))
    def name(self):
        return f"IMUX{self.inputNum}_PAE{self.paecell.count}_lane{self.paecell.lane.count}"
    def show(self):
        print(self.name)

class OMUX: # レーンの出力に付加される出力MUX
    count = 0
    def __init__(self, lane, withFF=False, skipLengths=None):
        self.count = OMUX.count
        OMUX.count += 1
        self.lane = lane      
        self.inputs = []      
        self.dsts = []      
        self.withFF = withFF  
        self.skipLengths = skipLengths 
        self.name = self.name()
    def numConfBits(self):
        if len(self.inputs) <= 1: return 0
        return math.ceil(math.log2(len(self.inputs)))
    def name(self):
        return f"OMUX{self.count}_lane{self.lane.count}"
    def show(self):
        print(self.name)

class PAEOutput: # PAEセルの出力
    def __init__(self, paecell, outputNum):
        self.paecell = paecell
        self.outputNum = outputNum 
        self.dsts = []           
        self.name = self.name()
    def name(self):
        return f"OutPort{self.outputNum}_PAE{self.paecell.count}_lane{self.paecell.lane.count}"
    def show(self):
        print(self.name)

class PAECell: # PAEセル
    count = 0
    def __init__(self, lane, nPAEin=4, nPAEout=3): # ★ nPAEout=3 に変更
        self.count = PAECell.count 
        PAECell.count += 1
        self.lane = lane       
        self.nPAEin = nPAEin     
        self.nPAEout = nPAEout   
        self.IMUXes = []         
        self.outputs = []        
        self.buildIMUXes(nPAEin)
        self.buildOutputs(nPAEout)
        self.name = self.name()
    def buildIMUXes(self, nPAEin):  
        for i in range(nPAEin):
            self.IMUXes.append(IMUX(self, i))
    def buildOutputs(self, nPAEout): 
        for i in range(nPAEout):
            self.outputs.append(PAEOutput(self,i))
    def name(self):
        return f"PAE{self.count}_lane{self.lane.count}"
    def show(self):
        print(f"lane[{self.lane.count}]: PAECell[{self.count}]")

class Var: # SAT変数
    count = 1
    def __init__(self, mgr):
        self.count = Var.count
        Var.count += 1
        self.mgr = mgr
    @classmethod
    def numVars(cls):
       return cls.count-1 
    def cnfStr(self):
        return f"{self.count}"

class BindVar(Var):
    def __init__(self, mgr, instance, target):
        super().__init__(mgr)
        self.instance = instance 
        self.target = target   
        self.name = self.name()
        mgr.vars[self.count] = self
    def name(self):
        return f"b_{self.instance.name}_{self.target.name}"

class ConnectVar(Var):
    def __init__(self, mgr, src, omux, dst):
        super().__init__(mgr)
        self.src = src
        self.omux = omux
        self.dst = dst
        self.name = self.name()
        mgr.vars[self.count] = self
    def name(self):
        name = f"c_{self.src.name}"
        if self.omux != None:
            name += f"--{self.omux.name}"
        name += f"--{self.dst.name}"
        return name
        
class OMUXUseVar(Var):
    def __init__(self, mgr, src, omux):
        super().__init__(mgr)
        self.src = src
        self.omux = omux
        self.name = self.name()
        mgr.vars[self.count] = self
    def name(self):
        return f"u_{self.src.name}--{self.omux.name}"

class WireVar(Var):
    def __init__(self, mgr, src, dst):
        super().__init__(mgr)
        self.src = src
        self.dst = dst
        self.name = self.name()
        mgr.vars[self.count] = self
    def name(self):
        return f"w_{self.src.name}--{self.dst.name}"

class Interconnect:
    count = 0
    def __init__(self, src, omux, dst):
        self.count =Interconnect.count
        Interconnect.count += 1
        self.src = src
        self.omux = omux 
        self.dst = dst
    def show(self):
        print(f"Interconnect (id={self.count}) {self.src.name} -> ", end="")
        if self.omux != None:
            print(f"{self.omux.name} ->", end="")
        print(f"{self.dst.name} ")

class PEALogic:
    def __init__(self, numPIs=8, numPOs=-1):
        self.lanes = []
        self.numPIs = numPIs
        self.numPOs = numPOs
        self.PAEOutputs = []
        self.PAECells = []
        self.OMUXes = []
        self.skipOMUXes = []
        self.IMUXes = []
        self.PIs = []
        self.POs = []
        self.Interconnects = []
        self.buildPIs()
        if self.numPOs != -1:
            self.buildPOs()

    # ( ... 従来の connectPIs, connectPItoMUX などは削除しても良い ... )
    
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    # ★★★ pea_out.py のための新しいメソッド ★★★
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    
    def connectPI_wire(self, pi_object, dst_x, dst_y, dst_pin):
        """
        指定されたPIオブジェクトを、指定された宛先IMUXに接続する
        """
        try:
            # 座標から対象のPAEセルとIMUXを特定
            dstPAE = self.lanes[dst_y].PAECells[dst_x]
            imux = dstPAE.IMUXes[dst_pin]
            
            # 接続を実行
            imux.inputs.append(pi_object)
            pi_object.dsts.append(imux)
            
        except IndexError:
            # 座標やピン番号がグリッド範囲外の場合
            print(f"Warning: Failed to connect PI. Invalid destination: ({dst_x},{dst_y}), pin {dst_pin}")
        except Exception as e:
            print(f"Warning: Error connecting PI wire: {e}")

    # ★ 内部配線接続用の connectPAEs (従来通り) ★
    def connectPAEs(self, src_x, src_y, src_outnum, dst_x, dst_y, dst_innum):
        try:
            srcPAE = self.lanes[src_y].PAECells[src_x]
            dstPAE = self.lanes[dst_y].PAECells[dst_x]
            imux = dstPAE.IMUXes[dst_innum]
            
            # OMUXを自動で見つける (sa_out.pyのロジックに合わせる)
            omux = None
            for dst in srcPAE.outputs[src_outnum].dsts:
                if isinstance(dst, OMUX) and dst.skipLengths is None:
                    omux = dst
                    break
            
            if omux is None:
                # print(f"Warning: No 1-input OMUX found for {srcPAE.name} output {src_outnum}")
                # (Note: Lane()コンストラクタでOMUXが自動接続される前提)
                # 暫定的に、LaneのOMUXリストから該当するものを探す
                # (sa_out.pyの Lane コンストラクタは nPAEout * nPAECells = 12 個のOMUXを作り、
                #  PAEの出力と1対1で接続する前提のため)
                
                # PAEの出力ピン総数 (0..11) に基づいてOMUXを特定する
                pae_index_in_lane = self.lanes[src_y].PAECells.index(srcPAE)
                omux_index = pae_index_in_lane * srcPAE.nPAEout + src_outnum
                if omux_index < len(self.lanes[src_y].OMUXes):
                    omux = self.lanes[src_y].OMUXes[omux_index]
                
            if omux:
                imux.inputs.append(omux)
                omux.dsts.append(imux)
            else:
                print(f"Error: Could not find matching OMUX for wire.")
        
        except Exception as e:
            print(f"Error connecting PAE wire: {e}")

    # ( ... buildPIs, buildPOs, addLane, generateAndconnectPOs, enumerateInterconnects ... )
    # ( ... saveGraph, saveGraph_AC は pea.py と同じ ... )
    # ( ... (省略) ... )
    
    def buildPIs(self): 
        print(f"building PIs {self.numPIs}")
        for i in range(self.numPIs):
            self.PIs.append(PI())

    def buildPOs(self): 
        for i in range(self.numPOs):
            self.POs.append(PO())
            
    def addLane(self, lane):
        self.lanes.append(lane)

    def generateAndconnectPOs(self, directOutput=True, outputLastLane=False):
        for l in self.lanes:
            for omux in l.OMUXes:
                if omux not in self.OMUXes: self.OMUXes.append(omux)
            for skipomux in l.skipOMUXes: 
                if skipomux not in self.skipOMUXes: self.skipOMUXes.append(skipomux)
            for pc in l.PAECells:
                if pc not in self.PAECells: self.PAECells.append(pc)
                for o in pc.outputs:
                    if o not in self.PAEOutputs: self.PAEOutputs.append(o)
                for i in pc.IMUXes:
                    if i not in self.IMUXes: self.IMUXes.append(i)
        
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
        else:
            pass # (POが事前に作られている場合のロジック)

    def enumerateInterconnects(self):
        # (OMUXを通す)
        for omux in self.OMUXes:
            for s in omux.inputs:
                for d in omux.dsts:
                    self.Interconnects.append(Interconnect(s, omux, d))
        # (SkipOMUXを通す)
        for skipomux in self.skipOMUXes:
            for s in skipomux.inputs:
                for d in skipomux.dsts:
                    self.Interconnects.append(Interconnect(s, skipomux, d))
        # (PI -> IMUX/PO)
        for pi in self.PIs:
            for d in pi.dsts:
                if type(d) is IMUX or type(d) is PO:
                    self.Interconnects.append(Interconnect(pi, None, d))
        # (PAEOutput -> PO)
        for o in self.PAEOutputs:
            for d in o.dsts:
                if type(d) is PO:
                    self.Interconnects.append(Interconnect(o, None, d))

# --- Lane クラス (変更なし) ---
class Lane:
    count = 0
    def __init__(self, nPAECells=4, nIMUXins=4, nOMUXes=6, nOMUXins=2, nPAEin=4, nPAEout=3, noOMUX=False, nSkipOMUXes=0, skips = None):
        self.count =Lane.count
        Lane.count += 1
        self.nPAECells = nPAECells 
        self.nOMUXes = nOMUXes
        self.PAECells = []
        self.OMUXes = []
        self.nPAEin = nPAEin
        self.nPAEout = nPAEout
        self.skips = skips
        self.skipOMUXes = []
        
        # ★ sa_out.py のロジックに合わせ、OMUXは (nPAEout * nPAECells) 個作る
        if noOMUX == False:
            self.nOMUXes = nPAEout * nPAECells
        
        self.buildPAECells(nPAECells, nPAEin, nPAEout)
        if noOMUX == False:
            self.buildOMUXes(self.nOMUXes)
            # ★ sa_out.py のロジックに合わせ、1対1で接続する
            self.connectPAEOutputToOMUX(noOMUX=True)
        if skips != None:
             pass # (今回はskipOMUXesは使わない)

    def buildPAECells(self, nPAECells, nPAEin, nPAEout):
        for i in range(nPAECells):
            self.PAECells.append(PAECell(self, nPAEin, nPAEout))
    
    def buildOMUXes(self,nOMUXes):
        for i in range(nOMUXes):
            self.OMUXes.append(OMUX(self))

    def connectPAEOutputToOMUX(self, fullConnection = True, noOMUX = True):
        outputs = [o for p in self.PAECells for o in p.outputs]
        if noOMUX is True: 
            # 1入力OMUXをPAE出力と1対1で接続
            for i, omux in enumerate(self.OMUXes):
                if i < len(outputs):
                    omux.inputs.append(outputs[i])
                    outputs[i].dsts.append(omux)
        else:
             # (従来のフル接続や部分接続ロジック)
             pass
    
    def show(self):
        print(f"--- start printing lane {self.count} ---")
        for p in self.PAECells: p.show()
        for m in self.OMUXes: m.show()

# --- Netlist, SATmgr, etc. クラス群 (変更なし) ---
# ( ... 従来のpea.pyからそのままコピー ... )
# ( ... (長いので省略) ... )

# (Netlistクラスの定義)
class NetlistPI:
    count = 0
    def __init__(self, netlist, name): self.count=NetlistPI.count; NetlistPI.count+=1; self.netlist=netlist; self.name=name; self.fanouts=[]
    def show(self): print(f"PI[{self.name}]",end="")
class NetlistPO:
    count = 0
    def __init__(self, netlist, name): self.count=NetlistPO.count; NetlistPO.count+=1; self.netlist=netlist; self.name=name; self.input=None
    def show(self): print(f"PO[{self.name}]",end="")
class PAEInstanceInput:
    def __init__(self, pae, inputNum): self.PAEInstance=pae; self.inputNum=inputNum
    def show(self): print(f"PAE[{self.PAEInstance.name}].in[{self.inputNum}]",end="")
class PAEInstanceOutput:
    def __init__(self, name, pae, outputNum): self.name=name; self.PAEInstance=pae; self.outputNum=outputNum
    def show(self): print(f"PAE[{self.PAEInstance.name}].out[{self.outputNum}]",end="")
class PAEInstance:
    count = 0
    def __init__(self, netlist, name): self.count=PAEInstance.count; PAEInstance.count+=1; self.netlist=netlist; self.name=name; self.inputNames=[]; self.outputNames=[]; self.inputs=[]; self.outputs=[]; self.fanouts=[]; self.initFanouts()
    def initFanouts(self):
        for i in range(self.netlist.numPAEoutputs): self.fanouts.append([])
    def show(self): print(f"PAEInstance [{self.name}]")
class Wire:
    count = 0
    def __init__(self, netlist, srcname, dstname): self.count=Wire.count; Wire.count+=1; self.srcname=srcname; self.dstname=dstname
class Edge:
    count = 0
    def __init__(self, netlist, src, dst): self.count=Edge.count; Edge.count+=1; self.src=src; self.dst=dst
    def show(self): print(f"edge[{self.count}]: ", end=""); self.src.show(); print(" -> ",end=""); self.dst.show(); print("\n")
class Netlist:
    def __init__(self, filename, numPAEinputs = 4, numPAEoutputs = 3): # ★ nPAEout=3 に変更
        self.numPIs=-1; self.numPOs=-1; self.numPAEinputs=numPAEinputs; self.numPAEoutputs=numPAEoutputs; self.netlistPIs={}; self.netlistPOs={}; self.PAEInstances={}; self.PAEGeneratedOutputs={}; self.edges=[]
        self.readFromFile(filename); self.connect(); self.buildEdges()
    def buildEdges(self):
        for paeInst in self.PAEInstances.values():
            for i, src in enumerate(paeInst.inputs):
                if src is None: continue
                paeInput = PAEInstanceInput(paeInst, i)
                self.edges.append(Edge(self, src, paeInput))
                if type(src) is PAEInstanceOutput: src.PAEInstance.fanouts[src.outputNum].append(paeInput)
                elif type(src) is NetlistPI: src.fanouts.append(paeInput)
        for po in self.netlistPOs.values():
            self.edges.append(Edge(self, po.input, po))
            if type(po.input) is PAEInstanceOutput: po.input.PAEInstance.fanouts[po.input.outputNum].append(po)
            elif type(po.input) is NetlistPI: po.input.fanouts.append(po)
    def connect(self):
        for paeInst in self.PAEInstances.values():
            for i, name in enumerate(paeInst.outputNames):
                if name == "nc": paeInst.outputs.append(None)
                else:
                    paeOutput = PAEInstanceOutput(name, paeInst, i)
                    if name in self.netlistPOs: self.netlistPOs[name].input = paeOutput
                    paeInst.outputs.append(paeOutput)
                    self.PAEGeneratedOutputs[name] = paeOutput
        for paeInst in self.PAEInstances.values():
            for i, name in enumerate(paeInst.inputNames):
                if name in self.netlistPIs: paeInst.inputs.append(self.netlistPIs[name])
                elif name == "nc": paeInst.inputs.append(None)
                else:
                    paeOutput = self.PAEGeneratedOutputs.get(name)
                    paeInst.inputs.append(paeOutput)
    def readFromFile(self, filename):
        with open(filename) as f:
            for line in f:
                l = line.split(); del_index = -1
                for i, e in enumerate(l):
                    if '#' in e: del_index = i; break
                if del_index != -1: del l[del_index:]
                if len(l) == 0: continue
                if l[0] == "inputs":
                    self.numPIs = 0
                    for e in l[1:]: self.netlistPIs[e] = NetlistPI(self,e); self.numPIs+=1
                elif l[0] == "outputs":
                    self.numPOs = 0
                    for e in l[1:]: self.netlistPOs[e] = NetlistPO(self,e); self.numPOs+=1
                elif l[0] == "pae":
                    pae = PAEInstance(self,l[1]); self.PAEInstances[l[1]] = pae
                    pae.inputNames.extend(l[2:2+self.numPAEinputs])
                    pae.outputNames.extend(l[2+self.numPAEinputs:])

# (SAT クラス群の定義)
class Literal:
    count = 0
    def __init__(self, var, polarity=True): self.count=Literal.count; Literal.count+=1; self.var=var; self.polarity=polarity; self.str=self.str(); self.cnfStr=self.cnfStr()
    def str(self): return self.var.name if self.polarity else "!" + self.var.name
    def cnfStr(self): return self.var.cnfStr() if self.polarity else "-" + self.var.cnfStr()
class Clause:
    count = 0
    def __init__(self): self.count=Clause.count; Clause.count+=1; self.literals=[]
    @classmethod
    def numClauses(cls): return cls.count
    def addLiteral(self, literal): self.literals.append(literal)
    def str(self): return " + ".join([l.str for l in self.literals])
    def cnfStr(self): return " ".join([l.cnfStr for l in self.literals]) + " 0"
class Constraint:
    def __init__(self): self.clauses=[]
    def addClause(self, clause): self.clauses.append(clause)
    def Str(self): return "".join(["("+cl.str()+")" for cl in self.clauses])
    def cnfStr(self): return "\n".join([cl.cnfStr() for cl in self.clauses]) + "\n"
def PAEInstanceOrPIPO(src):
    if type(src) is NetlistPI or type(src) is NetlistPO: return src
    elif type(src) is PAEInstanceInput or type(src) is PAEInstanceOutput: return src.PAEInstance
    else: assert("Invalid input argumet at PAEInstanceOrPIPO()")
def bindingPort(src, binding):
    if type(src) is PAEInstanceOutput: return binding.outputs[src.outputNum]
    elif type(src) is PAEInstanceInput: return binding.IMUXes[src.inputNum]
    elif type(src) is NetlistPI or type(src) is NetlistPO: return binding
    else: assert("Invalid input argumet at bindingPort()")
class SATmgr:
    def __init__(self, PEALogic, Netlist):
        self.PEALogic = PEALogic; self.Netlist = Netlist; self.vars = {}; self.BindVars = {}; self.ConnectVars = {}; self.OMUXUseVars = {}; self.WireVars = {}
        self.makeBindVars(); self.makeConnectVars()
        self.MappingConstraints = []; self.buildMappingConstraints()
        self.MaxMappingConstraints = []; self.buildMaxMappingConstraints()
        self.OMUXUsageConstraints = []; self.buildOMUXUsageConstraints()
        self.OMUXUsageVarConstraints = []; self.buildOMUXUsageVarConstraints()
        self.IMUXUsageConstraints = []; self.buildIMUXUsageConstraints()
        self.WireVarConstraints = []; self.buildWireVarConstraints()
        self.BindConnectConstraints = []; self.buildBindConnectConstraints()
        self.writeCNF(); self.writeReadableCNF()
    def readSATResultKissat(self):
        print("using Kissat"); trueVars = []; isSAT = False
        try:
            with open('sample.output', 'r') as f: lines = f.readlines()
            for line in lines:
                tokens = line.split()
                if not tokens: continue
                if tokens[0] == "s":
                    if tokens[1] == "SATISFIABLE": isSAT = True
                    else: break
                if tokens[0] == "v":
                    for t in tokens[1:]:
                        if t == "0": break
                        if not t.startswith('-'):
                            var = self.vars.get(int(t))
                            if var: trueVars.append(var)
            if not isSAT: print("########### SAT could not find solution")
        except FileNotFoundError: print("Error: sample.output not found.")
        except Exception as e: print(f"Error reading SAT result: {e}")
        return trueVars
    def solveSAT(self):
        command = ['kissat', '--time=3', '--no-binary', 'sample.cnf']
        try:
            with open('sample.output', 'w') as output_file, open('sample.cnf', 'r') as input_file:
                subprocess.run(command, stdin=input_file, stdout=output_file, shell=False, timeout=5) # 5秒タイムアウト
        except subprocess.TimeoutExpired:
            print("SAT solver timed out.")
        except FileNotFoundError:
            print("Error: 'kissat' solver not found. Make sure it is installed and in your PATH.")
        except Exception as e:
            print(f"Error running SAT solver: {e}")
    def writeCNF(self):
        with open('sample.cnf', 'w') as f:
            f.write(f"p cnf {Var.numVars()} {Clause.numClauses()}\n")
            f.write(self.MappingConstraints.cnfStr())
            f.write(self.MaxMappingConstraints.cnfStr())
            f.write(self.OMUXUsageConstraints.cnfStr())
            f.write(self.OMUXUsageVarConstraints.cnfStr())
            f.write(self.IMUXUsageConstraints.cnfStr())
            f.write(self.WireVarConstraints.cnfStr())
            f.write(self.BindConnectConstraints.cnfStr())
    def writeReadableCNF(self):
        with open('sample.rcnf', 'w') as f:
            f.write("MappingConstraints\n" + self.MappingConstraints.Str() + "\n")
            f.write("\nMaxMappingConstraints\n" + self.MaxMappingConstraints.Str() + "\n")
            f.write("\nOMUXUsageConstraints\n" + self.OMUXUsageConstraints.Str() + "\n")
            f.write("\nOMUXUsageVarConstraints\n" + self.OMUXUsageVarConstraints.Str() + "\n")
            f.write("\nIMUXUsageConstraints\n" + self.IMUXUsageConstraints.Str() + "\n")
            f.write("\nWireVarConstraints\n" + self.WireVarConstraints.Str() + "\n")
            f.write("\nBindConnectConstraints\n" + self.BindConnectConstraints.Str() + "\n")
    def buildBindConnectConstraints(self):
        for e in self.Netlist.edges:
            src, dst = e.src, e.dst
            srcInst, dstInst = PAEInstanceOrPIPO(src), PAEInstanceOrPIPO(dst)
            srcBindings = []; srcBindingPorts = []
            for k, v in self.BindVars.items():
                if k[0] == srcInst: srcBindings.append(k[1]); srcBindingPorts.append(bindingPort(src, k[1]))
            dstBindings = []; dstBindingPorts = []
            for k, v in self.BindVars.items():
                if k[0] == dstInst: dstBindings.append(k[1]); dstBindingPorts.append(bindingPort(dst, k[1]))
            for j1, srcBinding in enumerate(srcBindings):
                for j2, dstBinding in enumerate(dstBindings):
                    srcBindingPort, dstBindingPort = srcBindingPorts[j1], dstBindingPorts[j2]
                    bindConnectConstraint = Constraint()
                    wv = self.WireVars.get((srcBindingPort, dstBindingPort))
                    cl = Clause()
                    sbv = self.BindVars.get((srcInst, srcBinding)); cl.addLiteral(Literal(sbv, False))
                    dbv = self.BindVars.get((dstInst, dstBinding)); cl.addLiteral(Literal(dbv, False))
                    if wv is None: # 接続がない場合
                        pass # 制約 (!sbv + !dbv) を追加
                    else: # 接続がある場合
                        cl.addLiteral(Literal(wv, True)) # 制約 (!sbv + !dbv + wv) を追加
                    bindConnectConstraint.addClause(cl)
                    self.BindConnectConstraints.append(bindConnectConstraint)
    def buildWireVarConstraints(self):
        for wk, wv in self.WireVars.items():
            connectvars = [cv for ck, cv in self.ConnectVars.items() if wk[0] == ck[0] and wk[1] == ck[2]]
            wireVarConstraint = Constraint()
            cl = Clause(); cl.addLiteral(Literal(wv, False))
            for cv in connectvars: cl.addLiteral(Literal(cv, True))
            wireVarConstraint.addClause(cl)
            self.WireVarConstraints.append(wireVarConstraint)
    def buildOMUXUsageVarConstraints(self):
        OMUXes = self.PEALogic.OMUXes + self.PEALogic.skipOMUXes
        for OMUX in OMUXes:
            for PAEOutput in self.PEALogic.PAEOutputs:
                omuxusevar = self.OMUXUseVars.get((PAEOutput,OMUX))
                if omuxusevar is None: continue
                connectvars = [v for k, v in self.ConnectVars.items() if k[0] == PAEOutput and k[1] == OMUX]
                OMUXUsageVarConstraint = Constraint()
                for u in connectvars:
                    cl = Clause(); cl.addLiteral(Literal(u, False)); cl.addLiteral(Literal(omuxusevar, True))
                    OMUXUsageVarConstraint.addClause(cl)
                self.OMUXUsageVarConstraints.append(OMUXUsageVarConstraint)
    def buildMappingConstraints(self):
        instances = list(self.Netlist.PAEInstances.values()) + list(self.Netlist.netlistPIs.values()) + list(self.Netlist.netlistPOs.values())
        for instance in instances:
            bindvars = [v for k, v in self.BindVars.items() if k[0] == instance]
            if not bindvars: continue
            mappingConstraint = Constraint(); cl = Clause()
            for v in bindvars: cl.addLiteral(Literal(v, True))
            mappingConstraint.addClause(cl); self.MappingConstraints.append(mappingConstraint)
    def buildMaxMappingConstraints(self):
        cells = self.PEALogic.PAECells + self.PEALogic.PIs + self.PEALogic.POs
        for cell in cells:
            bindvars = [v for k, v in self.BindVars.items() if k[1] == cell]
            pairs = list(itertools.combinations(bindvars, 2))
            if not pairs: continue
            maxMappingConstraint = Constraint()
            for p in pairs:
                u, v = p[0], p[1]
                if u == v: continue
                cl = Clause(); cl.addLiteral(Literal(u, False)); cl.addLiteral(Literal(v, False))
                maxMappingConstraint.addClause(cl)
            self.MaxMappingConstraints.append(maxMappingConstraint)
    def buildOMUXUsageConstraints(self):
        OMUXes = self.PEALogic.OMUXes + self.PEALogic.skipOMUXes
        for OMUX in OMUXes:
            omuxusevars = [v for k, v in self.OMUXUseVars.items() if k[1] == OMUX]
            pairs = list(itertools.combinations(omuxusevars, 2))
            if not pairs: continue
            OMUXUsageConstraint = Constraint()
            for p in pairs:
                u, v = p[0], p[1]
                if u == v: continue
                cl = Clause(); cl.addLiteral(Literal(u, False)); cl.addLiteral(Literal(v, False))
                OMUXUsageConstraint.addClause(cl)
            self.OMUXUsageConstraints.append(OMUXUsageConstraint)
    def buildIMUXUsageConstraints(self):
        for IMUX in self.PEALogic.IMUXes:
            imuxusevars = [v for k, v in self.ConnectVars.items() if k[2] == IMUX]
            pairs = list(itertools.combinations(imuxusevars, 2))
            if not pairs: continue
            IMUXUsageConstraint = Constraint()
            for p in pairs:
                u, v = p[0], p[1]
                if u == v: continue
                cl = Clause(); cl.addLiteral(Literal(u, False)); cl.addLiteral(Literal(v, False))
                IMUXUsageConstraint.addClause(cl)
            self.IMUXUsageConstraints.append(IMUXUsageConstraint)
    def makeBindVars(self):
        for PAEInstance in self.Netlist.PAEInstances.values():
            for PAECell in self.PEALogic.PAECells:
                bindvar = BindVar(self, PAEInstance, PAECell); self.BindVars[(PAEInstance, PAECell)] = bindvar
        for netlistPI in self.Netlist.netlistPIs.values():
            for PI in self.PEALogic.PIs:
                bindvar = BindVar(self, netlistPI, PI); self.BindVars[(netlistPI, PI)] = bindvar
        for netlistPO in self.Netlist.netlistPOs.values():
            for PO in self.PEALogic.POs:
                bindvar = BindVar(self, netlistPO, PO); self.BindVars[(netlistPO, PO)] = bindvar
    def makeConnectVars(self):
        for ic in self.PEALogic.Interconnects:
            connectvar = ConnectVar(self, ic.src, ic.omux, ic.dst); self.ConnectVars[(ic.src, ic.omux, ic.dst)] = connectvar
            wirevar = WireVar(self, ic.src, ic.dst); self.WireVars[(ic.src, ic.dst)] = wirevar
            if ic.omux == None: continue
            omuxuse = (ic.src, ic.omux)
            if omuxuse in self.OMUXUseVars: continue
            omuxusevar = OMUXUseVar(self, ic.src, ic.omux); self.OMUXUseVars[omuxuse] = omuxusevar


# ==================================================================
# ★ ブロック3: 新しい main() 関数 ★
# (pea.pyのmainを改造し、wirestat_final.txtを読み込む)
# ==================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('netlist_file', help='検証したいネットリストのファイル名(独自形式)')
    args = parser.parse_args()
    print(f"Verifying netlist: {args.netlist_file}")

    # --- 1. アーキテクチャの基本設定 ---
    FINAL_ARCH_FILE = "wirestat_final.txt" # ★ build_wire.py が出力したファイル
    NUM_PIS = 36
    GRID_X = 4
    GRID_Y = 4
    INPUT_SPACING = 0.18 # ★ PI座標の計算ロジック (整数版)
    
    # --- 2. PEALogicの器を作成 ---
    pl = PEALogic(numPIs=NUM_PIS)
    for _ in range(GRID_Y): # 4レーン
        # ★ Laneコンストラクタを、sa_out.pyと一致させる (nPAEout=3)
        pl.addLane(Lane(nPAECells=GRID_X, nOMUXes=12, nSkipOMUXes=0, nPAEout=3))

    # --- 3. PIの物理座標 -> PIオブジェクト の対応マップを作成 ---
    # (build_wire.py と「全く同じ」ロジックで座標を生成)
    pi_coord_to_object_map = {}
    
    # ★ 整数座標ロジック ★
    for i in range(NUM_PIS):
        x_coord = i % GRID_X
        coord = (float(x_coord), -1.0) # (x, y) タプル
        pi_coord_to_object_map[coord] = pl.PIs[i]
    
    print(f"Mapped {len(pi_coord_to_object_map)} PI objects to physical coordinates.")

    # --- 4. 最終アーキテクチャファイル(wirestat_final.txt)を読み込み、配線を構築 ---
    print(f"Loading final architecture from '{FINAL_ARCH_FILE}'...")
    if not os.path.exists(FINAL_ARCH_FILE):
        print(f"Error: Final architecture file '{FINAL_ARCH_FILE}' not found.")
        print("Please run build_wire.py first.")
        return

    internal_wires_loaded = 0
    pi_wires_loaded = 0
    
    with open(FINAL_ARCH_FILE, 'r') as f:
        for line in f:
            if line.startswith("#"): continue
            try:
                parts = line.strip().split()
                if len(parts) != 6: continue
                
                # (src_x, src_y, src_pin, dst_x, dst_y, dst_pin)
                # ★ 座標は整数として読み込む ★
                src_x = float(parts[0]) # PIのX座標は小数/整数の可能性があるためfloat
                src_y = float(parts[1]) # PIのY座標
                src_pin = int(parts[2])
                dst_x, dst_y, dst_pin = int(parts[3]), int(parts[4]), int(parts[5])

                if src_y < 0 or src_pin == -1:
                    # --- 4a. 外部入力(PI)配線の接続 ---
                    pi_coord = (src_x, src_y)
                    pi_obj = pi_coord_to_object_map.get(pi_coord)
                    
                    if pi_obj:
                        pl.connectPI_wire(pi_obj, dst_x, dst_y, dst_pin)
                        pi_wires_loaded += 1
                    else:
                        print(f"Warning: PI coordinate {pi_coord} not found in map.")
                else:
                    # --- 4b. 内部配線(Cell->Cell)の接続 ---
                    pl.connectPAEs(int(src_x), int(src_y), src_pin, dst_x, dst_y, dst_pin)
                    internal_wires_loaded += 1
                    
            except (ValueError, IndexError, TypeError):
                print(f"Skipping malformed line in {FINAL_ARCH_FILE}: {line.strip()}")
                continue
    
    print(f"Architecture built: {internal_wires_loaded} internal wires, {pi_wires_loaded} PI wires.")

    # --- 5. PO（外部出力）の接続 (従来通り) ---
    pl.generateAndconnectPOs(directOutput=True, outputLastLane=False)

    # --- 6. 検証対象のネットリストを読み込み ---
    netlistFile = args.netlist_file
    if not os.path.exists(netlistFile):
        print(f"Error: Netlist file '{netlistFile}' not found.")
        return
        
    netlist = Netlist(netlistFile)

    # --- 7. リソースチェック (従来通り) ---
    print(f"In netlist, numPIs={netlist.numPIs}, numPOs={netlist.numPOs}")
    if pl.numPIs < netlist.numPIs:
        print("Error: Not enough physical PIs in architecture for this netlist.")
        exit(1) # 失敗
    totalNumPAECells = len(pl.PAECells)
    if totalNumPAECells < len(netlist.PAEInstances):
        print("Error: Not enough physical PAE Cells in architecture for this netlist.")
        exit(1) # 失敗

    # --- 8. SAT求解 (従来通り) ---
    print("Enumerating interconnects and building SAT problem...")
    pl.enumerateInterconnects()
    satmgr = SATmgr(pl, netlist)
    
    print("Running SAT solver (kissat)...")
    satmgr.solveSAT()
    
    trueVars = satmgr.readSATResultKissat() 

    if len(trueVars) == 0:
        print("\n--- RESULT: P&R solution not found (UNSAT) ---")
        exit(1) # 失敗をシェルに通知
    else:
        print("\n--- RESULT: P&R solution FOUND (SAT) ---")

    # --- 9. 構成メモリ計算 (オプション) ---
    numConfBits = 0
    for m in pl.IMUXes:
        numConfBits += m.numConfBits()
    for m in pl.OMUXes:
        numConfBits += m.numConfBits()
    
    print(f"Total Configuration Bits (IMUXes + OMUXes): {numConfBits}")

# ==================================================================
# ★ ブロック4: 実行の起点 ★
# ==================================================================
if __name__ == '__main__':
    # クラスのカウンタをリセット
    PI.count = 0; PO.count = 0; OMUX.count = 0; PAECell.count = 0; Lane.count = 0
    Var.count = 1; Interconnect.count = 0; Clause.count = 0
    NetlistPI.count = 0; NetlistPO.count = 0; PAEInstance.count = 0
    Wire.count = 0; Edge.count = 0
    
    main()