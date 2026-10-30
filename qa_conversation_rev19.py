"""20 real consecutive generations with recovery, Qt and synthetic broker."""
import argparse,json
from qa_conversation_rev11 import run
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--model',required=True);p.add_argument('--report',required=True);a=p.parse_args()
 r=run(a.exe,a.model,a.report,dell_7280=True,rebuilt=True,owner_requests=True,twenty_turns=True)
 print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['status']=='PASSED' else 1)
