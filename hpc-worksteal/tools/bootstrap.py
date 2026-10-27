#!/usr/bin/env python3
"""Copy the reviewed sources into a new Linux checkout and build with logs."""
import argparse,datetime as dt,json,pathlib,shutil,subprocess,sys
from lab import source_files,digest,write,ROOT
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--destination',required=True);ap.add_argument('--sanitize',choices=('none','asan','tsan'),default='none')
 ap.add_argument('--completion-batch',type=int,default=1);ap.add_argument('--steal-scratch',action='store_true');ap.add_argument('--ipo',action='store_true');ap.add_argument('--compute-lanes',type=int,choices=(1,4,8),default=1);a=ap.parse_args()
 target=pathlib.Path(a.destination).resolve();target.mkdir(parents=True,exist_ok=False)
 for f in source_files():
  dest=target/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
 build=target/('build-'+a.sanitize);build.mkdir();records=[]
 commands=[['cmake','-S',str(target),'-B',str(build),'-DCMAKE_BUILD_TYPE='+('Release' if a.sanitize=='none' else 'Debug')]]
 commands[0] += ['-DWS_COMPLETION_BATCH='+str(a.completion_batch),'-DWS_STEAL_SCRATCH='+('ON' if a.steal_scratch else 'OFF'),'-DWS_ENABLE_IPO='+('ON' if a.ipo else 'OFF'),'-DWS_COMPUTE_LANES='+str(a.compute_lanes)]
 if a.sanitize!='none':commands[0].append('-DWS_'+a.sanitize.upper()+'=ON')
 commands.append(['cmake','--build',str(build),'-j2'])
 for i,cmd in enumerate(commands):
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
  (build/f'build-{i}.log').write_text(p.stdout+p.stderr);records.append({'argv':cmd,'returncode':p.returncode})
  print(json.dumps(records[-1]),flush=True)
  if p.returncode:write(build/'build.json',records);return p.returncode
 write(build/'build.json',records)
 cmd=[sys.executable,str(target/'tools/lab.py'),'validate','--exe',str(build/'worksteal')]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=180);(build/'validate.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr)
 return p.returncode
if __name__=='__main__':sys.exit(main())
