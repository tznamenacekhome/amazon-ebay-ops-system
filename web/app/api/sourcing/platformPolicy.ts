import aliases from '../../../lib/canonicalSystems.json';
import policy from '../../../lib/sourcingPlatformPolicy.json';
export const sourcingPlatformPolicyVersion = policy.version;

type Row = Record<string, unknown>;
const obj = (v: unknown): Row => v && typeof v === 'object' && !Array.isArray(v) ? v as Row : {};
const norm = (v: unknown) => String(v ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' ');
export function canonicalSystems(value: unknown): string[] {
  const exact=Object.keys(aliases).filter(key=>norm(key)===norm(value));
  if(exact.length)return exact;
  const text = ` ${norm(value)} `, found: Array<{start: number; end: number; system: string}> = [];
  for (const [system, values] of Object.entries(aliases)) for (const alias of values) {
    const needle = ` ${norm(alias)} `;
    let index = text.indexOf(needle);
    while (index >= 0) { found.push({start:index, end:index+needle.length-1, system}); index=text.indexOf(needle,index+1); }
  }
  const kept: typeof found = [];
  for (const row of found.sort((a,b)=>(b.end-b.start)-(a.end-a.start))) {
    if (!kept.some(other=>row.start<other.end&&row.end>other.start)) kept.push(row);
  }
  return [...new Set(kept.map(row=>row.system))];
}

export function sourcingPlatformEligibility(seedValue: unknown, candidateValue: unknown = {}) {
  const seed=obj(seedValue), candidate=obj(candidateValue), context=obj(seed.raw_context_json);
  let catalog=obj(context.amazon_catalog_identity);
  if (catalog.asin && String(catalog.asin).toUpperCase()!==String(seed.asin??'').toUpperCase()) catalog={};
  const attrs=obj(catalog.relevant_attributes_json);
  let systems=[...new Set([catalog.normalized_platform,attrs.platform,seed.system,context.inferred_system].flatMap(canonicalSystems))];
  if (!systems.length) systems=canonicalSystems(seed.amazon_title);
  const raw=obj(candidate.raw_ebay_json), aspects=Array.isArray(raw.localizedAspects)?raw.localizedAspects.map(obj):[];
  const candidateSystems=aspects.filter(a=>String(a.name).toLowerCase()==='platform').flatMap(a=>canonicalSystems(a.value));
  const known=[...new Set([...systems,...candidateSystems])];
  const result=(status:string,reason:string)=>({version:policy.version,result:status,reason,platforms:known});
  if(known.some(s=>policy.excludedCartridgePlatforms.includes(s))) return result('blocked',policy.cartridgeReason);
  if(systems.length!==1) return result('unresolved',policy.unresolvedReason);
  const system=systems[0];
  if(policy.mixedFormatPlatforms.includes(system)) {
    const format=[attrs.format,catalog.normalized_format,attrs.platform,catalog.normalized_platform,attrs.media_type,attrs.physical_format,
      ...(String(seed.amazon_title??'').match(/\b(?:CD-ROM|DVD-ROM|cartridge|HuCard|disc)\b/gi)??[])].join(' ');
    if(/\bcartridge\b|\bhu[ -]?card\b|\bcard\b/i.test(format+' '+String(candidate.ebay_title??'')))return result('blocked',policy.cartridgeReason);
    const explicitFormat=[attrs.physical_format,attrs.media_type,attrs.platform,catalog.normalized_platform,
      ...(String(seed.amazon_title??'').match(/\b(?:CD-ROM|DVD-ROM|disc)\b/gi)??[])].join(' ');
    const disc=/\b(?:cd(?:[ _-]?rom)?|dvd(?:[ _-]?rom)?|blu[ -]?ray|disc)\b/i;
    if(!disc.test(format)||!disc.test(explicitFormat))return result('unresolved',policy.unresolvedReason);
    return result('pass','Product-specific disc format; normal sourcing safeguards still apply.');
  }
  if([...policy.exceptionPlatforms,...policy.discOrComputerPlatforms].includes(system))return result('pass','Platform permitted; normal sourcing safeguards still apply.');
  return result('unresolved',policy.unresolvedReason);
}

export function platformOpportunityAllowed(row: unknown) {
  const value=obj(row);
  return sourcingPlatformEligibility(value.sourcing_seed_asins,value.sourcing_ebay_candidates).result==='pass';
}
