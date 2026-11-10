// Runs entirely on the selected machine. The registry contains that machine's
// Python/entry/data paths, so client paths and PATH setup never leak across hosts.
export const discoverRuntime = `import json,os,pathlib,re,sys
try:
 name=sys.argv[1]
 if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}',name): raise ValueError('Invalid runtime name')
 root=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',str(pathlib.Path.home()/'.config')))
 path=root/'herdr-spaces'/'runtimes'/(name+'.json')
 if not path.is_file(): raise ValueError('Install herdr-spaces runtime on this machine: python3 scripts/install.py --runtime-only --name '+name)
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

export function validateSnapshot(data) {
  if(data?.protocolVersion!==1||data.schemaVersion!==1||!Array.isArray(data.coreScopes)||
    typeof data.coreScopes[0]!=='string'||!data.coreScopes[0].startsWith('core:')||typeof data.ledgerHome!=='string')
    throw new Error('项目运行程序版本不兼容，请在项目所在机器安装 herdr-spaces 0.2 或兼容版本。');
  return data;
}
