import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const out={};new Function('exports',ts.transpileModule(readFileSync(new URL('./reviewRequestIds.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(out);
const requests=new out.ReviewRequestIds();
const first=requests.get('pair:positive');
assert.equal(requests.get('pair:positive'),first,'Failed/uncertain network attempt must retain its ID for retry');
requests.complete('pair:positive');
const negative=requests.get('pair:negative');requests.complete('pair:negative');
const positiveAgain=requests.get('pair:positive');
assert.notEqual(positiveAgain,first,'A later positive after intervening negative must append a new action');
assert.notEqual(positiveAgain,negative);
requests.cancel();assert.notEqual(requests.get('pair:positive'),positiveAgain,'Closing a review ends that attempt');
assert.notEqual(requests.get('otherPair:positive'),requests.get('pair:positive'),'Bulk rows have independent IDs');
const uncertain=requests.get('edited-dialog:positive');
requests.get('edited-dialog:negative');requests.complete('edited-dialog:negative');
requests.cancel(); // Successful dialog close also discards abandoned payload attempts.
assert.notEqual(requests.get('edited-dialog:positive'),uncertain);
console.log('Review request IDs passed: retry stability, completed-attempt renewal, intervening verdict, cancel, independent bulk rows.');
