const fs=require('fs'),assert=require('assert/strict'),path=require('path');
const dir=process.env.REVIEW_FIXTURES||path.resolve('tmp/sourcing-phase3');
process.env.SUPABASE_URL='https://froeucjkcepuhgwisped.supabase.co';process.env.SUPABASE_SERVICE_ROLE_KEY='offline-test-key';
const fixtures=new Map(JSON.parse(fs.readFileSync(path.join(dir,'responses.json'),'utf8')).filter(r=>r.method==='GET').map(r=>[r.url,r]));
const baseline=JSON.parse(fs.readFileSync(path.join(dir,'current.json'),'utf8'));assert.equal(baseline.reviews.length,0);
let reads=0;global.fetch=async(url,init)=>{
 const method=init?.method??'GET';if(method==='POST'&&String(url)===process.env.SUPABASE_URL+'/rest/v1/rpc/sourcing_latest_reviews')return new Response('[]',{headers:{'content-type':'application/json'}});
 assert.equal(method,'GET');const row=fixtures.get(String(url));assert(row,'Uncaptured request; forbidden network '+url);reads++;return new Response(JSON.stringify(row.body),{status:row.status,headers:{'content-type':'application/json'}});
};
const app=process.env.REVIEW_APP||path.resolve('web');
const {GET}=require(path.join(app,'.next/server/app/api/sourcing/opportunities/route.js')).routeModule.userland;
(async()=>{const counts={};for(const [name,query] of Object.entries({buy_list:'status=open&type=all&sourceMode=all&scope=all_open&limit=150',closest_excluded:'status=open&type=all&sourceMode=all&scope=closest_excluded&limit=50',business_excluded:'status=business_excluded&type=all&scope=all_open&limit=50'})){
 const response=await GET({url:'https://example.test/api/sourcing/opportunities?'+query}),body=await response.json();assert.equal(response.status,200,JSON.stringify(body));assert.deepEqual(body.opportunities.map(r=>r.opportunityId),baseline.views[name].opportunities.map(r=>r.opportunityId));assert.deepEqual(body.summary,baseline.views[name].summary);for(let i=0;i<body.opportunities.length;i++){const a={...body.opportunities[i]},b={...baseline.views[name].opportunities[i]};delete a.diagnosticComparison;delete b.diagnosticComparison;assert.deepEqual(a,b);}counts[name]=body.opportunities.length;
}console.log(JSON.stringify({compiledRuntimeRouting:counts,reads,networkCalls:0}));
for(const file of fs.readdirSync(path.join(app,'.next/server'),{recursive:true}).filter(f=>f.endsWith('.js'))){const s=fs.readFileSync(path.join(app,'.next/server',file),'utf8');assert(!s.includes('phase3_shadow')&&!s.includes('offline_identity_policy'),file);}
assert(!fs.existsSync(path.join(app,'integrations')));console.log('Packaged route output matches frozen full routing fields. No shadow policy activation or Python integrations in web runtime.');
})().catch(e=>{console.error(e);process.exitCode=1});
