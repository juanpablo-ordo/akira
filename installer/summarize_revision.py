"""Print compact, reproducible CI evidence without private account data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET


def verify_manifest(root):
    manifest=json.loads((root/'PACKAGE_SHA256.json').read_text(encoding='utf-8'))
    bad=[]
    for relative,expected in manifest.items():
        path=(root/relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            bad.append(relative+': absent or outside source');continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:bad.append(relative+': SHA256 mismatch')
    if bad:raise RuntimeError('Package integrity: '+', '.join(bad))
    return len(manifest)


def summarize(root, folder):
    count=verify_manifest(root)
    xml=ET.parse(folder/'REGRESSION_TESTS.xml').getroot()
    cases=xml.findall('.//testcase')
    if not cases or xml.findall('.//failure') or xml.findall('.//error') or xml.findall('.//skipped'):
        raise RuntimeError('Regressions incomplete or failed')
    names=('SOURCE_SELF_CHECK','NATIVE_APPLICATION','NATIVE_FIRST_RUN','SPRITE_AI_SOURCE',
        'SPRITE_AI_FROZEN','HTTPS_SOURCE_REV10','HTTPS_FROZEN_REV10','LOW_RESOURCE_FROZEN_REV10',
        'PUBLIC_SOURCES_SOURCE_REV10','PUBLIC_SOURCES_FROZEN_REV10','LOCAL_AI_SCENARIOS',
        'REAL_REVIEW_REV10','REAL_CONVERSATION_REV6_WINDOWS','REAL_CHAT_LOW_RESOURCE_REV11','INSTALLED_LOCAL_AI')
    reports={}
    for name in names:
        path=folder/(name+'.json');raw=path.read_bytes();data=json.loads(raw)
        if data.get('status')!='PASSED':raise RuntimeError('Unverified report: '+name)
        reports[name]={'status':data['status'],'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    from akira_version import BUILD_ID
    result={'status':'PASSED','build':BUILD_ID,'source_commit':os.environ.get('GITHUB_SHA'),
        'workflow_run_id':os.environ.get('GITHUB_RUN_ID'),'manifest_entries_verified':count,
        'regressions':{'xml_testcases':len(cases),'failures':0,'errors':0,'skipped':0},
        'real_conversation_and_load':json.loads((folder/'REAL_CHAT_LOW_RESOURCE_REV11.json').read_text(encoding='utf-8')),
        'frozen_without_text_inference':json.loads((folder/'LOW_RESOURCE_FROZEN_REV10.json').read_text(encoding='utf-8')),
        'reports':reports,'live_account_used':False,'user_attachments_reviewed':False,'profitability_verified':False}
    (folder/'VERIFICATION_REV11.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('AKIRA_REV11_VERIFICATION_JSON='+json.dumps(result,ensure_ascii=False,separators=(',',':')),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--diagnostics',type=Path,default=Path('diagnostics'))
    parser.add_argument('--manifest-only',action='store_true')
    args=parser.parse_args()
    if args.manifest_only:print('SHA256 verified files:',verify_manifest(args.root))
    else:summarize(args.root,args.diagnostics)
