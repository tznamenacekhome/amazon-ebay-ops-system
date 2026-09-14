// Real packaged Next.js UI/API -> isolated PostgreSQL. Never uses production credentials.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {execFileSync,spawn} from 'node:child_process';
import {mkdirSync,readFileSync,existsSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const image=process.env.ADJUDICATION_TEST_IMAGE;
assert(image?.startsWith('mbop-web:web-'),'An exact local web release image is required');
const container='mbop-phase2-review-test',webContainer='mbop-adjudication-browser-test';
const out=resolve(process.env.ADJUDICATION_TEST_OUTPUT??'tmp/variation-scope/browser');mkdirSync(out,{recursive:true});
const sql=q=>execFileSync('docker',['exec','-i',container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'],{input:q,encoding:'utf8',windowsHide:true,maxBuffer:32*1024*1024}).trim();
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

  const queue=JSON.parse(readFileSync('web/app/api/sourcing/adjudication/queue.json','utf8'));
  const row=queue.find(r=>r.asin==='B08SZ1F5FB');
  const api=async(query='')=>(await fetch('http://localhost:3108/api/sourcing/adjudication'+query)).json();
  let current=(await api()).rows.find(r=>r.queueId===row.queueId);
  const seed={queueId:row.queueId,requestId:crypto.randomUUID(),expectedAsin:row.asin,expectedEbayItemId:row.ebayItemId,expectedSnapshotHash:row.snapshotHash,expectedRevision:current.revision,
    identityAttested:true,variationResolution:'unknown',notes:'Preserve these saved operator notes',feedback:{pairVerdict:'correct',flaggedFields:['coreGame'],corrections:[{side:'ebay',scope:'pair',field:'coreGame',state:'value',value:'Preserved scoped correction'}],fieldRelationships:[{field:'platform',operatorRelationship:'compatible'}]}};
  const seeded=await fetch('http://localhost:3108/api/sourcing/adjudication',{method:'POST',headers:{'content-type':'application/json','x-mbop-csrf':'1','origin':'http://localhost:3108'},body:JSON.stringify(seed)});assert.equal(seeded.status,200,await seeded.text());
  current=(await api()).rows.find(r=>r.queueId===row.queueId);const original=structuredClone(current.latestReview);
  await cdp('Page.reload');await until(`document.querySelectorAll('tbody tr').length===16`);
  await js(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Review confirmation variation scope').click()`);
  const open=async()=>{await js(`[...document.querySelectorAll('tbody tr')].find(r=>r.textContent.includes('${row.asin}')).querySelector('button').click()`);await until(`!!document.querySelector('[role=dialog]')`);};
  for(const scope of ['unknown','verified','not_applicable']) {
    await open();assert.equal(await js(`document.querySelector('[aria-label="Adjudication notes"]').value`),original.notes);
    await js(`{const e=document.querySelector('[aria-label="Variation scope"]');e.value='${scope}';e.dispatchEvent(new Event('change',{bubbles:true}));}`);
    if(scope==='verified') {
      assert(await js(`document.querySelector('[role=dialog]').textContent.includes('No exact variation identifier')`));
      await js(`window.realFetch=window.fetch;window.fetch=(url,opts)=>{if(opts?.method==='POST'){const b=JSON.parse(opts.body);b.expectedRevision='stale';opts={...opts,body:JSON.stringify(b)};}return window.realFetch(url,opts);}`);
      await js(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Save variation scope').click()`);await until(`!!document.querySelector('[role=alert]')`);
      assert.equal(await js(`document.querySelector('[aria-label="Variation scope"]').value`),'verified');
      assert(await js(`document.querySelector('[role=alert]').textContent.includes('newer review')`));
      const shot=await cdp('Page.captureScreenshot',{captureBeyondViewport:false});writeFileSync(resolve(out,'variation-stale.png'),Buffer.from(shot.data,'base64'));
      await js(`window.fetch=window.realFetch`);
    }
    const shot=await cdp('Page.captureScreenshot',{captureBeyondViewport:false});writeFileSync(resolve(out,'variation-'+scope+'.png'),Buffer.from(shot.data,'base64'));
    await js(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Save variation scope').click()`);await until(`!document.querySelector('[role=dialog]')`);
    current=(await api()).rows.find(r=>r.queueId===row.queueId);
    assert.equal(current.latestReview.variationResolution,scope);assert.equal(current.latestReview.tierA,scope==='not_applicable');
    for(const key of ['actionId','feedback','corrections','notes','platformRelationship'])assert.deepEqual(current.latestReview[key],original[key],key);
  }
  assert(!(await js(`[...document.querySelectorAll('tbody tr')].some(r=>r.textContent.includes('${row.asin}'))`)));
  await cdp('Page.reload');await until(`document.querySelectorAll('tbody tr').length===16`);
  assert(await js(`[...document.querySelectorAll('tbody tr')].find(r=>r.textContent.includes('${row.asin}')).textContent.includes('Tier A')`));
  assert.equal(errors.length,0);
  writeFileSync(resolve(out,'contracts.json'),JSON.stringify({image,variationStatesPersisted:3,originalEvidencePreserved:true,staleSelectionPreserved:true,qualifiedRowLeavesFollowup:true,reloadTierA:true,errors},null,2));
  console.log('Packaged browser/API/RPC variation contracts passed: all states, preserved evidence, inline stale error, filtered queue and reload.');
} finally {ws?.close();chrome?.kill();proxy.close();try{execFileSync('docker',['stop',webContainer],{windowsHide:true,stdio:'ignore'});}catch{}}
