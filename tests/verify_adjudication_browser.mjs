// Real packaged Next.js UI/API -> isolated PostgreSQL. Never uses production credentials.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {execFileSync,spawn} from 'node:child_process';
import {mkdirSync,readFileSync,existsSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const image=process.env.ADJUDICATION_TEST_IMAGE;
assert(image?.startsWith('mbop-web:web-'),'An exact local web release image is required');
const container='mbop-phase2-review-test',webContainer='mbop-adjudication-browser-test';
const out=resolve(process.env.ADJUDICATION_TEST_OUTPUT??'tmp/adjudication-negative-browser');mkdirSync(out,{recursive:true});
const sql=q=>execFileSync('docker',['exec','-i',container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'],{input:q,encoding:'utf8',windowsHide:true}).trim();
const quote=v=>v==null?'null':"'"+String(typeof v==='object'?JSON.stringify(v):v).replaceAll("'","''")+"'";
const calls=[],errors=[];
const proxy=createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;
  const name=req.url?.split('/').at(-1);
  if(req.method!=='POST'||!['sourcing_adjudication_state','sourcing_save_adjudication'].includes(name)){res.writeHead(403);res.end('{}');return;}
  const args=JSON.parse(raw);calls.push({name,args});
  try {const data=sql(`select public.${name}(${Object.entries(args).map(([k,v])=>k+'=>'+quote(v)).join(',')})`);res.setHeader('content-type','application/json');res.end(data);}
  catch(e){res.writeHead(400,{'content-type':'application/json'});res.end(JSON.stringify({message:String(e.stderr),code:String(e.stderr).includes('newer pair review')?'40001':'22023'}));}
});
await new Promise(r=>proxy.listen(3199,'0.0.0.0',r));
let chrome,ws;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
try {
  execFileSync('docker',['run','-d','--rm','--name',webContainer,'-p','127.0.0.1:3108:3000','-e','SUPABASE_URL=http://host.docker.internal:3199','-e','SUPABASE_SERVICE_ROLE_KEY=disposable-test-only','-e','CLOUD_DEPLOYMENT=false','-e','LOCAL_SYNC_ENABLED=true',image],{windowsHide:true});
  for(let i=0;i<60;i++){try{await fetch('http://localhost:3108/sourcing/adjudication');break;}catch{await wait(500);}}
  const profile=resolve(out,'chrome-'+Date.now());mkdirSync(profile);
  chrome=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
  for(let i=0;i<60&&!existsSync(resolve(profile,'DevToolsActivePort'));i++)await wait(250);
  const port=readFileSync(resolve(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const tabs=await(await fetch(`http://localhost:${port}/json`)).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise(r=>ws.addEventListener('open',r,{once:true}));let id=0;const pending=new Map();
  ws.addEventListener('message',e=>{const msg=JSON.parse(e.data);if(msg.id){const p=pending.get(msg.id);pending.delete(msg.id);msg.error?p.reject(msg.error):p.resolve(msg.result);}else if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params);});
  const cdp=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
  const js=async expression=>{const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const until=async expression=>{for(let i=0;i<100;i++){if(await js(expression))return;await wait(100);}throw new Error('Timed out: '+expression+' '+await js('JSON.stringify({url:location.href,text:document.body.innerText})')+' '+JSON.stringify(errors));};
  await cdp('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Runtime.enable');await cdp('Page.enable');await cdp('Page.navigate',{url:'http://localhost:3108/sourcing/adjudication'});
  await until(`document.querySelectorAll('tbody tr').length===16`);
  await js(`document.querySelectorAll('tbody tr')[1].querySelector('button').click()`);
  await until(`!!document.querySelector('[role=dialog]')`);
  const before=await js(`({text:document.querySelector('[role=dialog]').innerText,secure:isSecureContext,uuid:typeof crypto.randomUUID})`);
  await js(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Incorrect Match').click()`);
  for(let i=0;i<200;i++){if(await js(`!document.querySelector('[role=dialog]')||!!document.querySelector('[role=alert]')`))break;await wait(100);}
  const result=await js(`({dialog:!!document.querySelector('[role=dialog]'),text:document.body.innerText,alerts:[...document.querySelectorAll('[role=alert]')].map(e=>e.textContent)})`);
  writeFileSync(resolve(out,'result.json'),JSON.stringify({image,before,result,calls,errors},null,2));
  const screenshot=await cdp('Page.captureScreenshot',{captureBeyondViewport:false});writeFileSync(resolve(out,'result.png'),Buffer.from(screenshot.data,'base64'));
  console.log(JSON.stringify({image,dialog:result.dialog,alerts:result.alerts,saves:calls.filter(c=>c.name==='sourcing_save_adjudication').length,errors}));
  assert.equal(result.dialog,false,'Negative click must save and close the dialog');
  const saved=calls.find(c=>c.name==='sourcing_save_adjudication');assert(saved);assert.equal(saved.args.p_context.matchingFeedback.pairVerdict,'incorrect');
  assert.equal(saved.args.p_context.identityAttested,false);assert.equal(saved.args.p_context.variationVerified,false);
  assert.deepEqual(saved.args.p_context.matchingFeedback.flaggedFields,[]);assert.deepEqual(saved.args.p_context.matchingFeedback.corrections,[]);
  if(process.env.ADJUDICATION_BASELINE!=='1') {
    assert(result.text.includes('Incorrect Match saved for B07FF3F7F9'));
    assert(await js(`document.querySelectorAll('tbody tr')[1].querySelector('button').textContent==='Incorrect Match'`));
    assert.equal(calls.filter(c=>c.name==='sourcing_adjudication_state').length,18,'16 initial reads + pre-save + exact-pair readback; no full queue reload');
    const open=async()=>{await js(`document.querySelectorAll('tbody tr')[1].querySelector('button').click()`);await until(`!!document.querySelector('[role=dialog]')`);};
    const negative=async()=>{await js(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Incorrect Match').click()`);await until(`!document.querySelector('[role=dialog]')`);};
    await open();await js(`document.querySelector('[aria-label="Core Game Wrong"]').click()`);await negative();
    let last=calls.filter(c=>c.name==='sourcing_save_adjudication').at(-1);assert.deepEqual(last.args.p_context.matchingFeedback.flaggedFields,['coreGame']);assert.deepEqual(last.args.p_context.matchingFeedback.corrections,[]);
    await open();await js(`document.querySelector('[aria-label="Core Game Wrong"]').click();`);
    await until(`!!document.querySelector('[aria-label="Core Game ebay value"]')`);
    const correctedValue='Disposable corrected product '+Date.now();
    await js(`{const e=document.querySelector('[aria-label="Core Game ebay value"]');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,${JSON.stringify(correctedValue)});e.dispatchEvent(new Event('input',{bubbles:true}));}`);await negative();
    last=calls.filter(c=>c.name==='sourcing_save_adjudication').at(-1);assert.equal(last.args.p_context.matchingFeedback.corrections[0].value,correctedValue);
    await open();assert(await js(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Confirm Match').disabled`));
    await js(`{const e=document.querySelector('[aria-label="Adjudication notes"]');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,'Retain unsaved notes');e.dispatchEvent(new Event('input',{bubbles:true}));window.originalFetch=window.fetch;window.fetch=(url,opts)=>{if(opts?.method==='POST'){const body=JSON.parse(opts.body);body.expectedRevision='stale-browser-test';opts={...opts,body:JSON.stringify(body)};}return window.originalFetch(url,opts);};}`);
    await js(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Incorrect Match').click()`);await until(`!!document.querySelector('[role=alert]')`);
    assert(await js(`document.querySelector('[role=alert]').textContent.includes('A newer review or correction exists')`));assert.equal(await js(`document.querySelector('[aria-label="Adjudication notes"]').value`),'Retain unsaved notes');
    await js(`window.fetch=window.originalFetch`);
    const screen=await cdp('Page.captureScreenshot',{captureBeyondViewport:false});writeFileSync(resolve(out,'stale.png'),Buffer.from(screen.data,'base64'));
    writeFileSync(resolve(out,'contracts.json'),JSON.stringify({image,negativeWithoutAssertions:true,wrongWithoutReplacement:true,negativeWithCorrection:true,staleInlineAndStateRetained:true,positiveDisabledWithoutAttestation:true,readbackOnly:true,saves:calls.filter(c=>c.name==='sourcing_save_adjudication').length,errors},null,2));
    console.log('Actual packaged browser/API/RPC contracts passed, including negative variants, bounded update, success and stale-state retention.');
  }
} finally {ws?.close();chrome?.kill();proxy.close();try{execFileSync('docker',['stop',webContainer],{windowsHide:true,stdio:'ignore'});}catch{}}
