import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const out={};new Function('exports',ts.transpileModule(readFileSync(new URL('./deliveryStats.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(out);
const data={notDelivered:{units:7,purchaseDollars:123.45,unpricedUnits:0},deliveredNotReceived:{units:3,purchaseDollars:99,unpricedUnits:1}};
assert.deepEqual((await out.fetchDeliveryStats({rpc:async name=>{assert.equal(name,'purchase_delivery_stats');return {data,error:null};}})).delivery,data);
assert.deepEqual(await out.fetchDeliveryStats({rpc:async()=>({data:null,error:{message:'Actual DB failure'}})}),{delivery:null,deliveryError:'Actual DB failure'});
assert.equal((await out.fetchDeliveryStats({rpc:async()=>({data:{},error:null})})).delivery,null);
console.log('Purchase delivery API: authoritative totals preserved; actual errors and invalid results visible, never zero-filled');
