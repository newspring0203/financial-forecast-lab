"""Source integrity and forecast information-set guards."""
import hashlib
import json
from pathlib import Path

def verify_source(path,manifest_path):
    manifest=json.loads(Path(manifest_path).read_text())
    digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest!=manifest['sha256']:raise ValueError('Raw source SHA-256 does not match manifest')
    return digest

def guard_origin(train,sources,origin_date,origin_end,target_end):
    if origin_date>=target_end:raise ValueError('Origin must precede target quarter end')
    if not train or not sources:raise ValueError('Empty origin data')
    if any(x['end']>origin_end for x in train):raise ValueError('Future period in training data')
    if any(s['filed']>origin_date for x in sources for s in x['sources']):raise ValueError('Future filing in training data')
