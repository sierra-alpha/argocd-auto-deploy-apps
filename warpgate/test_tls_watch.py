import os,pathlib,subprocess,tempfile,time,yaml
patch=yaml.safe_load(pathlib.Path(__file__).resolve().parent.joinpath('manifests/deployment-patch.yaml').read_text())
script=patch['spec']['template']['spec']['containers'][0]['command'][-1]
subprocess.run(['sh','-n'],input=script,text=True,check=True)
for change in (True,False):
 with tempfile.TemporaryDirectory() as tmp:
  p=pathlib.Path(tmp)
  (p/'tls.crt').write_text('test cert');(p/'tls.key').write_text('test key')
  (p/'warpgate').write_text('#!/bin/sh\ntrap \'exit 0\' TERM INT\ntouch "$STARTED"\nwhile :; do sleep 0.05; done\n')
  (p/'warpgate').chmod(0o755)
  testscript=script.replace('/tls-cert/',tmp+'/').replace('sleep 30','sleep 0.05')
  env={'PATH':tmp+':/usr/bin:/bin','STARTED':str(p/'started'),'WARPGATE_ENCRYPTION_KEY':'test-placeholder'}
  proc=subprocess.Popen(['sh','-ec',testscript],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  try:
   deadline=time.monotonic()+3
   while not (p/'started').exists():
    assert proc.poll() is None
    assert time.monotonic()<deadline
    time.sleep(.02)
   if change: (p/'tls.crt').write_text('renewed test cert')
   else: proc.terminate()
   assert proc.wait(timeout=3)==0
   print('TLS renewal restart' if change else 'TERM shutdown', 'passed')
  finally:
   if proc.poll() is None: proc.kill();proc.wait()
