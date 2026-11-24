import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const out = {};
new Function('exports', ts.transpileModule(readFileSync(new URL('./presentation.ts', import.meta.url),'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(out);
const calls=[];
const counts=await out.presentationCounts('tab-fixture',async url=>{
  const q=new URL(url,'https://test.local').searchParams;calls.push(q);
  return Response.json({summary:{total:q.get('scope')==='all_open'?12:9},opportunities:[]});
});
assert.deepEqual(counts,{buyList:12,closestExcluded:9});
assert(calls.every(q=>q.get('flipmineTabId')==='tab-fixture'&&q.get('format')==='list'&&q.get('fresh')==='1'));
assert.equal(calls[0].get('status'),'open');assert.equal(calls[1].get('status'),'all');
await assert.rejects(()=>out.presentationCounts('t',async()=>Response.json({error:'offline'},{status:503})),/retained/);
await assert.rejects(()=>out.presentationCounts('t',async()=>Response.json({summary:{}})),/retained/);
assert.deepEqual(await out.presentationCounts('t',async()=>Response.json({summary:{total:0}})),{buyList:0,closestExcluded:0});
console.log('Flipmine presentation: shared list counts, valid empty, failure and incomplete counts retained');
