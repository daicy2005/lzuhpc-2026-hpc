#!/usr/bin/env python3
import argparse,json,pathlib,statistics,sys
def main():
 ap=argparse.ArgumentParser();ap.add_argument('records');a=ap.parse_args();r=json.loads(pathlib.Path(a.records).read_text());groups={}
 for x in r:
  if x.get('status')!='completed' or x.get('correct') is not True:continue
  groups.setdefault(x['condition'],[]).append(x['epoch_seconds'])
 out=[]
 for k,v in groups.items():out.append({'condition':k,'n':len(v),'median':statistics.median(v),'min':min(v),'max':max(v),'values':v})
 print(json.dumps(sorted(out,key=lambda x:x['condition']),indent=2));return 0
if __name__=='__main__':sys.exit(main())
