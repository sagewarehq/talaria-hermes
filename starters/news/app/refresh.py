#!/usr/bin/env python3
"""Collect attributed RSS headlines from the feeds in newsroom.json; atomic data replacement, preserve good data on failure."""
import concurrent.futures as cf
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
import io
from html.parser import HTMLParser
from urllib.parse import urlsplit
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))  # newsroom.py; the routine runs this through runpy
from newsroom import open_public, settings

def fetch_public(url):
 return open_public(url)

class ImageMetadata(HTMLParser):
 def __init__(self):
  super().__init__(); self.image=''
 def handle_starttag(self, tag, attrs):
  attrs=dict(attrs)
  if tag=='meta' and (attrs.get('property') or attrs.get('name')) in ('og:image','twitter:image') and not self.image:
   self.image=attrs.get('content','')

def feed_image(item):
 for el in item.iter():
  if el.tag in ('{http://search.yahoo.com/mrss/}content','{http://search.yahoo.com/mrss/}thumbnail') and el.get('url','').startswith('https://'):
   return el.get('url')
  if el.tag=='enclosure' and el.get('type','').startswith('image/'):
   return el.get('url','')
 for el in item.iter():
  if el.tag.split('}')[-1] in ('encoded','content','description'):
   match=re.search(r'<img[^>]+src=[\"\x27]([^\"\x27]+)',el.text or '',re.I)
   if match: return html.unescape(match.group(1))
 return ''

def cache_image(article):
 """Use feed media or canonical og:image, cache raster bytes for phone reliability."""
 folder=ROOT/'images'; folder.mkdir(exist_ok=True)
 existing=list(folder.glob(article['id']+'.*'))
 if existing:
  article['image']='./images/'+existing[0].name
  article.pop('imageCandidate',None)
  return
 image=article.pop('imageCandidate','')
 try:
  if not image:
   # OpenAI currently blocks metadata retrieval. Do not bypass restrictions.
   if article['publisher']=='OpenAI': return
   with fetch_public(article['url']) as response:
    parser=ImageMetadata();parser.feed(response.read(1_500_000).decode('utf-8','replace'));image=parser.image
  if not image.startswith('https://'): return
  host=urlsplit(image).hostname or ''
  if host in ('localhost','127.0.0.1','::1') or not '.' in host: return
  with fetch_public(image) as response:
   kind=response.headers.get_content_type(); ext={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif','image/avif':'.avif'}.get(kind)
   if not ext: return
   content=response.read(4_000_001)
   if len(content)>4_000_000 or len(content)<100: return
  try: from PIL import Image, ImageOps  # Hermes' Python has it; without it, key stories just have no picture
  except ImportError: return
  with Image.open(io.BytesIO(content)) as original:
   if original.width*original.height>40_000_000: return
   resized=ImageOps.exif_transpose(original).convert('RGB');resized.thumbnail((900,650))
   path=folder/(article['id']+'.jpg');resized.save(path,quality=82,optimize=True)
  article['image']='./images/'+path.name;article['imageSource']=image
 except Exception as exc:
  article['imageError']=str(exc)
 finally:
  article.pop('imageCandidate',None)

ROOT = Path(__file__).resolve().parent
SOURCES = [(f.get('topic') or 'Technology',f.get('title') or urlsplit(f['url']).hostname,f['url']) for f in settings()['feeds'] if f.get('url')]
NOW = dt.datetime.now(dt.timezone.utc)
def clean(text):
 return re.sub(r'\s+', ' ',html.unescape(re.sub('<[^>]*>', '',text or ''))).strip()
def parse_date(s):
 try:
  try: d=email.utils.parsedate_to_datetime(s)
  except Exception: d=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
  return d.replace(tzinfo=d.tzinfo or dt.timezone.utc).astimezone(dt.timezone.utc)
 except Exception: return None

def collect(src):
 topic,publisher,url=src
 with open_public(url,timeout=30) as response: root=ET.fromstring(response.read(4_000_000))
 entries=root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
 rows=[]
 for item in entries:
  def text(key):
   el=item.find(key)
   if el is None: el=item.find('{http://www.w3.org/2005/Atom}'+key)
   return ''.join(el.itertext()) if el is not None else ''
  title=clean(text('title')); link=text('link').strip()
  if not link:
   for el in item.findall('{http://www.w3.org/2005/Atom}link'):
    if el.get('rel','alternate')=='alternate': link=el.get('href',''); break
  date=parse_date(text('pubDate') or text('published') or text('updated'))
  if not title or not link.startswith('https://') or not date or date>NOW+dt.timedelta(hours=2): continue
  if NOW-date>dt.timedelta(days=10): continue
  summary=clean(text('description') or text('summary'))
  summary=re.sub(r'\s*(The post .*? appeared first on .*|Read the full story.*)$','',summary)[:320]
  article_topics=[topic]
  discussion=''
  if publisher=='Hacker News':
   discussion=text('comments')
   summary='Selected by the Hacker News community. Open the original article or join the discussion.'
   signals=title.lower()
   for label,pattern in [('Artificial Intelligence',r'\b(ai|llm|openai|anthropic|claude|deepseek|moonshot|model|inference|agent)\b'),('Cybersecurity',r'\b(security|vulnerability|ransomware|malware|exploit|breach|cve|cryptography)\b'),('Startups',r'\b(startup|founder|funding|venture)\b')]:
    if re.search(pattern,signals): article_topics.append(label)
  rows.append(dict(id=hashlib.sha256(link.encode()).hexdigest()[:16],title=title,url=link,publisher=publisher,topics=article_topics,publishedAt=date.isoformat(),summary=summary,feedUrl=url,imageCandidate=feed_image(item),discussionUrl=discussion))
 return rows

def atomic(name,value):
 path=ROOT/name; tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)); tmp.replace(path)

def main():
 rows={}; health=[]
 with cf.ThreadPoolExecutor(max_workers=6) as pool:
  futures={pool.submit(collect,s):s for s in SOURCES}
  for future in cf.as_completed(futures):
   topic,publisher,url=futures[future]
   try:
    items=future.result()
    health.append(dict(topic=topic,publisher=publisher,url=url,count=len(items),ok=bool(items)))
    for row in items:
     if row['id'] in rows: rows[row['id']]['topics']=sorted(set(rows[row['id']]['topics']+row['topics']))
     else: rows[row['id']]=row
   except Exception as exc: health.append(dict(topic=topic,publisher=publisher,url=url,ok=False,error=str(exc)))
 if not rows:
  atomic('status.json',dict(attemptedAt=NOW.isoformat(),ok=False,sources=health))
  raise SystemExit('All collection feeds unavailable; preserving the last good data and edition')
 # Keep last good coverage for a temporarily failed topic, explicitly marked.
 failed_topics=set(t for t,_,_ in SOURCES)-set(t for r in rows.values() for t in r['topics'])
 if (ROOT/'data.json').exists():
  old=json.loads((ROOT/'data.json').read_text())
  for row in old.get('articles',[]):
   if any(t in failed_topics for t in row['topics']) and row['id'] not in rows:
    row['retained']=True; rows[row['id']]=row
 if not rows:
  atomic('status.json',dict(attemptedAt=NOW.isoformat(),ok=False,sources=health))
  raise SystemExit('All sources unavailable; previous news data preserved')
 articles=sorted(rows.values(),key=lambda a:a['publishedAt'],reverse=True)
 # Drop identical normalized headlines even when feeds use different tracking URLs.
 seen=set(); unique=[]
 for row in articles:
  key=re.sub(r'\W+','',row['title']).lower()
  if key not in seen: unique.append(row); seen.add(key)
 # Reuse local photos without fetching an image for every candidate. The editor
 # prepares imagery only for selected key stories when it publishes an edition.
 for article in unique:
  matches=list((ROOT/'images').glob(article['id']+'.*'))
  if matches: article['image']='./images/'+matches[0].name
 atomic('data.json',dict(updatedAt=NOW.isoformat(),refreshHours=6,articles=unique,sources=health,coverageDays=10))
 atomic('status.json',dict(attemptedAt=NOW.isoformat(),ok=True,sources=health))
 print(json.dumps({'articles':len(unique),'images':sum(bool(a.get('image')) for a in unique),'byTopic':{t:sum(t in a['topics'] for a in unique) for t,_,_ in SOURCES},'sourceFailures':[s for s in health if not s['ok']],'updatedAt':NOW.isoformat()}))
if __name__=='__main__': main()
