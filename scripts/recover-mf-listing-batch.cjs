/** Bounded MF recovery. Plan first; apply only the saved, reviewed manifest.
 * node scripts/recover-mf-listing-batch.cjs plan <sheet-source.json> <output-dir>
 * node scripts/recover-mf-listing-batch.cjs apply <output-dir>/manifest.json
 * Reads the local service credential without printing it. No Amazon writes.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const webRequire = createRequire(path.join(root, 'web/package.json'));
const ts = webRequire('typescript');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText, filename);
const { inventoryLabExportRows } = require('../web/app/api/fba-shipments/inventoryLabExport.ts');
const { fetchListingSkuMappings, resolveListingSku } = require('../web/app/api/amazonSkuIdentity.ts');
const { listingCsv, businessLocalNow } = require('../web/app/fba/listingBatch.ts');
process.loadEnvFile(path.join(root, 'web/.env.local'));
const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
if (new URL(url).hostname !== 'froeucjkcepuhgwisped.supabase.co') throw Error('Unexpected recovery environment');
const db = webRequire('@supabase/supabase-js').createClient(url, process.env.SUPABASE_SERVICE_ROLE_KEY);
async function query(builder) { const { data, error } = await builder; if (error) throw Error(error.message); return data; }
const read = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
const save = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const summary = lots => ({ ids: lots.map(l => l.id).sort(), units: lots.reduce((n,l) => n+l.quantity,0),
  cost_cents: lots.reduce((n,l) => n+Math.round(Number(l.unit_cost)*l.quantity*100),0) });
async function main() {
 const [mode, input, output] = process.argv.slice(2);
 if (mode === 'plan') {
  const source = read(input);
  const rows = source.missing.values.slice(5).filter(r => r.length>=9 && r[2]);
  if (!rows.length || rows.length>100) throw Error('Expected bounded missing-item evidence');
  const batches = await query(db.from('amazon_listing_batches').select('id,external_reference,status,fulfillment_method').in('external_reference', [...new Set(rows.map(r=>'MF '+r[0]))]));
  if (batches.length!==3 || batches.some(b=>b.fulfillment_method!=='MF'||b.status!=='completed')) throw Error('Expected three completed MF source batches');
  const allocations = await query(db.from('amazon_listing_allocations').select('*').in('batch_id', batches.map(b=>b.id)));
  const chosen = [];
  const selected = new Set();
  for (const row of rows) {
   if (String(row[5]).toLowerCase().includes('found') || String(row[7]).toLowerCase().includes('found') || String(row[8]).toLowerCase()!=='new') throw Error('Row is not missing New inventory');
   const batch = batches.find(b=>b.external_reference==='MF '+row[0]);
   const matches=allocations.filter(a=>a.batch_id===batch.id&&a.snapshot.asin===row[2]);
   if (!matches.length || matches.reduce((n,a)=>n+a.quantity,0)!==Number(row[4])) throw Error('Sheet/MBOP quantity mismatch: '+row[2]);
   for (const a of matches) { if(selected.has(a.id)) throw Error('Repeated source row'); selected.add(a.id); chosen.push(a); }
  }
  const lots=await query(db.from('amazon_merchant_inventory_lots').select('*').in('allocation_id',chosen.map(a=>a.id)));
  if(lots.length!==chosen.length || lots.some(l=>l.seller_sku)) throw Error('Sources reconciled or lots are not one per allocation');
  const registered=await query(db.from('amazon_mf_lots').select('id').in('listing_lot_id',lots.map(l=>l.id)));
  if(registered.length) throw Error('Source stock already registered');
  const mappings=await fetchListingSkuMappings(db,[...new Set(chosen.map(a=>a.snapshot.asin))],'MF');
  const items=chosen.map(a=>({source_allocation_id:a.id,quantity:a.quantity,condition:'new',seller_sku:resolveListingSku(mappings,a.snapshot.asin,'MF','new')}));
  const groups=chosen.map((a,i)=>({asin:a.snapshot.asin,msku:items[i].seller_sku,title:a.snapshot.amazon_title,system:a.snapshot.system,
   sell_price:Number(a.snapshot.sell_price),fulfillment_method:'MF',details:[{...a.snapshot,item_id:a.id,quantity:a.quantity,
    unit_cost:Number(a.snapshot.unit_cost),seller_sku:items[i].seller_sku,fulfillment_method:'MF',condition:'new'}]}));
  const csv=listingCsv(inventoryLabExportRows(groups,Object.fromEntries(chosen.map(a=>[a.id,String(a.quantity)])),'MF'));
  const source_url=`https://docs.google.com/spreadsheets/d/${source.spreadsheet_id}/edit?gid=364361611`;
  const manifest={p_batch:crypto.randomUUID(),p_local:businessLocalNow(),p_items:items,p_csv:csv,
   p_evidence:{source_url,source_sha256:hash(JSON.stringify(source)),allocations:items,source_batches:batches,
    physical_before:summary(lots),csv_sha256:hash(csv),condition_basis:'New as recorded in source reconciliation'}};
  fs.mkdirSync(output,{recursive:true}); save(path.join(output,'manifest.json'),manifest);
  fs.writeFileSync(path.join(output,`mbop-mf-recovery-${manifest.p_batch}.csv`),csv);
  console.log(JSON.stringify({batch:manifest.p_batch,local:manifest.p_local,...summary(lots),csv_rows:csv.split('\n').length-1,
   mapped_rows:items.filter(i=>i.seller_sku).length,output},null,2));
 } else if(mode==='apply') {
  const manifest=read(input);
  if(hash(manifest.p_csv)!==manifest.p_evidence.csv_sha256) throw Error('CSV changed after planning');
  const before=await query(db.from('amazon_merchant_inventory_lots').select('id,quantity,unit_cost').in('id',manifest.p_evidence.physical_before.ids));
  if(JSON.stringify(summary(before))!==JSON.stringify(manifest.p_evidence.physical_before)) throw Error('Physical source changed');
  const result=await query(db.rpc('mbop_recover_mf_listing',manifest));
  const allocations=await query(db.from('amazon_listing_allocations').select('id,quantity,listed_quantity,recovery_source_allocation_id').eq('batch_id',manifest.p_batch));
  const lots=await query(db.from('amazon_merchant_inventory_lots').select('id,quantity,unit_cost,allocation_id').in('allocation_id',allocations.map(a=>a.id)));
  if(JSON.stringify(summary(lots))!==JSON.stringify(manifest.p_evidence.physical_before)) throw Error('Recovery conservation verification failed');
  save(path.join(path.dirname(input),'result.json'),{batch:result.id,reference:result.external_reference,status:result.status,
   physical_after:summary(lots),allocations:allocations.length});
  console.log(JSON.stringify({batch:result.id,reference:result.external_reference,status:result.status,units:summary(lots).units,cost:summary(lots).cost_cents/100},null,2));
 } else throw Error('Use plan <source.json> <output-dir> or apply <manifest.json>');
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
