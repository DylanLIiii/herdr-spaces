import sys,subprocess,json
from pathlib import Path
root=Path(__file__).parent
args=sys.argv[1:]
commands=('probe','setup','bind','introduce','show','context','skill')
command=next((c for c in commands if c in args),'other')
with (root/'calls.jsonl').open('a') as f:f.write(json.dumps({'command':command})+'\n')
if command=='introduce' and not (root/'fault-used').exists():
 (root/'fault-used').write_text('failed before delivery')
 print(json.dumps({'error':'隔离验证：介绍发送前的传输故障，请重试'}),file=sys.stderr)
 sys.exit(73)
sys.exit(subprocess.call([sys.executable,'/Users/dylan/repo/herdr-spaces/project.py']+args))
