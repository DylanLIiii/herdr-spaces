// Runs entirely on the selected machine. The registry contains that machine's
// Python/entry/data paths, so client paths and PATH setup never leak across hosts.
export const discoverRuntime = `import json,os,pathlib,re,sys
try:
 name=sys.argv[1]
 if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}',name): raise ValueError('Invalid runtime name')
 root=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',str(pathlib.Path.home()/'.config')))
 path=root/'herdr-spaces'/'runtimes'/(name+'.json')
 if not path.is_file():
  print(json.dumps({'code':'runtime_missing','message':'Project setup is not ready on this machine'}),file=sys.stderr)
  sys.exit(2)
 data=json.loads(path.read_text())
 argv=data.get('command')
 if data.get('protocolVersion')!=1 or not isinstance(argv,list) or not argv or any(not isinstance(s,str) or '\\0' in s for s in argv) or not os.path.isabs(argv[0]): raise ValueError('Invalid runtime registration; reinstall this machine runtime')
 os.execv(argv[0],argv+sys.argv[2:])
except (OSError,ValueError) as e:
 print(json.dumps({'error':str(e)}),file=sys.stderr)
 sys.exit(1)
`;

export function endpoint(config, machine) {
  if (machine) {
    const remote=config.remotes?.[machine]??{};
    const argv=remote.command??[remote.python||'python3','-c',discoverRuntime,remote.name||config.remoteName||'projects'];
    if(!Array.isArray(argv)||!argv.length||argv.some(s=>typeof s!=='string'||s.includes('\0')))throw new Error('远端运行入口配置无效。');
    return {command:argv[0],args:argv.slice(1),on:machine};
  }
  if(!config.entry)throw new Error('尚未安装运行入口。请运行项目安装器。');
  return {command:config.python||'python3',args:[config.entry,...(config.dataHome?['--home',config.dataHome]:[])],on:null};
}

export function failure(result) {
  const raw=String(result.stderr||result.stdout||'连接未返回结果').slice(0,1500);
  let data;try{data=JSON.parse(raw);}catch{}
  const code=data?.code||(raw.includes('Install herdr-spaces runtime')?'runtime_missing':'unavailable');
  const error=new Error(code==='runtime_missing'?'此机器尚未准备项目功能。':data?.message||data?.error||'暂时无法连接项目机器，请重试。');
  error.code=code;error.detail=raw;return error;
}

export async function callRuntime(config,args,loc,exec) {
  const target=endpoint(config,loc.machine);
  const r=await exec(target.command,[...target.args,...args],{on:target.on,timeout:args[0]==='introduce'?40000:15000});
  if(r.code!==0)throw failure(r);
  return JSON.parse(r.stdout);
}

export function supportsLeaderSetup(probe) {
  return ['leader-bind','core-command-discovery','pm-configuration','guided-setup','artifact-bundles'].every(feature=>probe?.capabilities?.includes(feature));
}

export async function prepareRuntime(config,loc,exec,readTextFile) {
  const custom=config.remotes?.[loc.machine];
  if(custom?.command)throw new Error('请先在项目机器更新自定义运行入口，然后重试。');
  if(!config.bootstrap||!config.bundle)throw new Error('请更新本机的 Herdr Spaces 安装，以启用自动设置。');
  const [source,bundle]=await Promise.all([readTextFile(config.bootstrap),readTextFile(config.bundle)]);
  if(!source||!bundle)throw new Error('本机安装文件不完整，请重新安装 Herdr Spaces。');
  const r=await exec(loc.machine?(custom?.python||'python3'):config.python||'python3',
    ['-c',source,custom?.name||config.remoteName||'projects',bundle],{on:loc.machine,timeout:30000});
  if(r.code!==0)throw failure(r);
  return JSON.parse(r.stdout);
}

export function validateSnapshot(data) {
  if(data?.protocolVersion!==1||![1,2].includes(data.schemaVersion)||!Array.isArray(data.coreScopes)||
    typeof data.coreScopes[0]!=='string'||!data.coreScopes[0].startsWith('core:')||typeof data.ledgerHome!=='string')
    throw new Error('项目运行程序版本不兼容，请更新本机与项目机器上的 Herdr Spaces。');
  return data;
}
