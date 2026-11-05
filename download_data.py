"""Download once; keep the raw SEC snapshot and a reproducible source manifest."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parent
URL='https://data.sec.gov/api/xbrl/companyfacts/CIK0000097476.json'

def main():
    user_agent=os.environ.get('SEC_USER_AGENT')
    if not user_agent:raise SystemExit('Set SEC_USER_AGENT to your application name and contact email.')
    request=urllib.request.Request(URL,headers={'User-Agent':user_agent,'Accept-Encoding':'identity'})
    payload=urllib.request.urlopen(request,timeout=60).read()
    obj=json.loads(payload)
    if obj.get('cik')!=97476:raise ValueError('Unexpected CIK')
    folder=ROOT/'data/raw';folder.mkdir(parents=True,exist_ok=True)
    (folder/'ti_companyfacts.json').write_bytes(payload)
    (folder/'manifest.json').write_text(json.dumps(dict(url=URL,retrieved_at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(payload).hexdigest()),indent=2))
    print('Saved SEC companyfacts snapshot and manifest.')

if __name__=='__main__':main()
