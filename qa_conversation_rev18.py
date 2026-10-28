"""Real model recovery while reviewing, then the reported casual/humour turns."""
import argparse,json
from qa_conversation_rev11 import run

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--model',required=True);p.add_argument('--report',required=True)
    args=p.parse_args();result=run(args.exe,args.model,args.report,dell_7280=True,rebuilt=True,owner_requests=True)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['status']=='PASSED' else 1)
