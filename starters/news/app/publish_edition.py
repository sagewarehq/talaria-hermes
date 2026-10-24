#!/usr/bin/env python3
"""Validate an editorial selection against real collected records and publish atomically."""
import datetime as dt
import json
from pathlib import Path
import re
import sys
import fcntl
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import newsroom
TOPICS=set(newsroom.TOPICS)

def validate(edition,data):
 assert edition.get('version')==1,'Unsupported version'
 assert edition.get('basisUpdatedAt')==data['updatedAt'],'Edition must match current feed batch'
 assert edition.get('summary') and edition.get('editedAt'),'Edition needs editor note and date'
 assert dt.datetime.fromisoformat(edition['editedAt']).tzinfo,'Edited timestamp needs timezone'
 items=edition.get('items');assert isinstance(items,list) and len(items)<=30,'Select no more than 30'
 known={a['id'] for a in data['articles']};seen=set();keys=0
 for item in items:
  key=item.get('id');assert key in known and re.fullmatch('[a-f0-9]{16}',key),'Unknown article ID'
  assert key not in seen,'Duplicate story';seen.add(key)
  assert isinstance(item.get('priority'),int) and 0<=item['priority']<=100,'Priority out of bounds'
  assert isinstance(item.get('key'),bool),'key must be boolean';keys+=item['key']
  assert isinstance(item.get('why'),str) and 20<=len(item['why'])<=500,'Add bounded relevance reason'
  assert 2<=len(item.get('tags',[]))<=6 and all(isinstance(t,str) and 1<=len(t)<=60 for t in item['tags']),'Use 2–6 tags'
  assert all(t in TOPICS for t in item.get('topics',[])),'Unknown topic'
  evidence=item.get('evidence',{})
  assert evidence.get('status') in ('source-reviewed','feed-only'),'Label evidence status'
  assert evidence.get('url','').startswith('https://') and evidence.get('note'),'Evidence URL and limitation required'
 assert keys<=3,'Use no more than three key developments'
 return {'selected':len(items),'key':keys,'reviewed':sum(i['evidence']['status']=='source-reviewed' for i in items)}

def main():
 edition=json.loads(Path(sys.argv[1]).read_text());data=json.loads((ROOT/'data.json').read_text())
 stats=validate(edition,data)
 from refresh import cache_image
 by_id={a['id']:a for a in data['articles']}
 for item in edition['items']:
  if item['key']: cache_image(by_id[item['id']])
 data_tmp=ROOT/'data.publish.tmp';data_tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));data_tmp.replace(ROOT/'data.json')
 edition['snapshots']=[dict(by_id[item['id']]) for item in edition['items']]
 publish_archive(ROOT,edition)
 extract_articles()
 print(json.dumps(stats))

def extract_articles():
 """Bring the articles' text in for the in-app reader (extract.py, in its own venv). Never fails a publish."""
 import subprocess
 py=ROOT.parents[1]/"venvs"/"newsroom"/"bin"/"python"
 if not py.exists():return
 try:subprocess.run([str(py),str(ROOT/"extract.py"),str(ROOT)],timeout=300,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 except Exception:pass

def atomic_json(path,value):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)

def archive_record(root,edition,records):
 stamp=dt.datetime.fromisoformat(edition['editedAt']).astimezone(dt.timezone.utc)
 ident=stamp.strftime('%Y%m%dT%H%M%S%fZ')
 archived=dict(edition,editionId=ident)
 folder=root/'editions';folder.mkdir(exist_ok=True)
 path=folder/(ident+'.json')
 if path.exists():
  if json.loads(path.read_text())!=archived:raise ValueError('Archived edition is immutable; use a new editedAt for a new edition')
 else:
  with path.open('x') as stream:json.dump(archived,stream,ensure_ascii=False,indent=2)
 records[ident]=dict(id=ident,editedAt=edition['editedAt'],date=stamp.astimezone(newsroom.zone()).date().isoformat(),count=len(edition['items']),summary=edition.get('summary',''),path='editions/'+ident+'.json')
 return archived

def publish_archive(root,edition):
 """Archive before moving latest. Existing edition files are never rewritten."""
 with (root/'.editions.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  index_path=root/'editions.json'
  index=json.loads(index_path.read_text()) if index_path.exists() else {'editions':[]}
  records={item['id']:item for item in index['editions']}
  current=root/'editorial.json'
  if current.exists():archive_record(root,json.loads(current.read_text()),records)
  archived=archive_record(root,edition,records)
  atomic_json(current,archived)
  atomic_json(index_path,dict(version=1,latestId=archived['editionId'],editions=sorted(records.values(),key=lambda r:r['editedAt'],reverse=True)))

if __name__=='__main__': main()
