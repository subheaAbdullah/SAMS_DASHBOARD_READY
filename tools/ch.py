import os
import io, warnings
warnings.filterwarnings("ignore")
p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
t=io.open(p,encoding="utf-8").read()
compile(t,p,"exec")
print("SYNTAX OK | lines:", t.count(chr(10))+1)
print("mojibake:", [i for i,l in enumerate(t.split(chr(10)),1) if "\ufffd" in l] or "NONE")
