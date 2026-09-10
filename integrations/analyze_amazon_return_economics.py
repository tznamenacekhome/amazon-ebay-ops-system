"""Offline, read-only FBA return analysis from cached MBOP/Amazon evidence.

No database writes, accounting recalculation, or estimated Amazon fees.
See docs/AMAZON_RETURN_ECONOMICS.md for collection and limitations.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import median

from amazon_sync_sales_finances import transaction_order_id
from sourcing_match_rules import detect_all_systems, platform_display

ZERO = Decimal('0')
RELEASED = {'RELEASED', 'DEFERRED_RELEASED'}
RETURNS = 'GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA'
REIMBURSEMENTS = 'GET_FBA_REIMBURSEMENTS_DATA'


def number(v):
    return Decimal(str(v)) if v not in (None, '') else None


def amount(row):
    return number((row.get('breakdownAmount') or {}).get('currencyAmount')) or ZERO


def unique_transactions(stored, fresh):
    result = {t['raw_transaction_json']['transactionId']: t['raw_transaction_json'] for t in stored}
    result.update({t['transactionId']: t for t in fresh})
    # A released transaction can have a NEW ID and point to its deferred record.
    # Counting both charges a shipment/refund twice despite distinct IDs.
    superseded = set()
    for t in result.values():
        refs={r['relatedIdentifierName']:r['relatedIdentifierValue'] for r in t.get('relatedIdentifiers') or []}
        release=refs.get('RELEASE_TRANSACTION_ID')
        if release in result and result[release].get('transactionStatus')=='RELEASED':
            superseded.add(t['transactionId'])
        deferred=refs.get('DEFERRED_TRANSACTION_ID')
        if deferred and t.get('transactionStatus')=='RELEASED':superseded.add(deferred)
    return [t for key,t in result.items() if key not in superseded]


def item_sku(item):
    contexts = [c for c in item.get('contexts') or [] if c.get('contextType') == 'ProductContext']
    return contexts[0].get('sku') if len(contexts) == 1 else None


def item_components(item):
    """Use named fee level once, never add parent and child totals together."""
    fees = []
    principal = ZERO
    for group in item.get('breakdowns') or []:
        kind = group.get('breakdownType', '')
        if kind in ('AmazonFees', 'FBAFees'):
            for child in group.get('breakdowns') or [group]:
                fees.append((child.get('breakdownType'), amount(child)))
        elif kind == 'ProductCharges':
            for child in group.get('breakdowns') or []:
                if child.get('breakdownType') in ('OurPricePrincipal', 'Principal'):
                    principal += amount(child)
    return fees, principal


def classify_game(asin, title, identities):
    identity = identities.get(asin, {})
    product_type = identity.get('product_type') or ''
    if product_type in ('PHYSICAL_VIDEO_GAME_SOFTWARE', 'CONSOLE_VIDEO_GAMES'):
        platforms=detect_all_systems(identity.get('normalized_platform') or '')
        return True, '/'.join(platform_display(s) or s for s in platforms) or 'Unknown', 'Amazon product type'
    systems = detect_all_systems(title)
    # Deliberately do not classify platform-compatible hardware as game software.
    excluded = re.search(r'\b(controller|headset|console|charging|charger|cable|skin|case only|accessory|accessories|steering wheel)\b', title, re.I)
    if systems and not excluded:
        return True, '/'.join(platform_display(s) or s for s in systems), 'Title/platform heuristic'
    return False, 'Unclassified', 'No reliable game match'


def csv_write(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8'); return
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Treat externally supplied titles as text when opened in Excel.
            writer.writerow({k: "'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k,v in row.items()})


def json_default(value):
    if isinstance(value, Decimal): return float(value)
    raise TypeError(type(value).__name__)


def loss_bounds(transaction_cost, basis, impairment, reimbursement, inventory_reimb=0):
    """Unknown recovery is not a zero-valued asset. Return separate scenarios."""
    if transaction_cost is None or inventory_reimb:
        return None, None
    known = transaction_cost + (impairment or ZERO) - reimbursement
    upper = None
    if impairment is not None or basis is not None:
        upper = transaction_cost + (basis if impairment is None else impairment) - reimbursement
    return known, upper


def run(cache, output, start='2025-09-01', end='2026-09-01'):
    def read(name, optional=False):
        path = cache / (name+'.json')
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else ([] if optional else (_ for _ in ()).throw(FileNotFoundError(path)))
    sales = read('sales')
    returns = read(RETURNS)
    reimbursements = read(REIMBURSEMENTS)
    identities = {r['asin']: r for r in read('identities')}
    skus = {r['seller_sku']: r for r in read('skus')}
    # One ASIN classification serves BOTH numerator and denominator. Report titles
    # may contain platform suffixes absent from the original sale title.
    class_candidates=defaultdict(list)
    for asin,title in [(s['asin'],s['title']) for s in sales]+[(r['asin'],r['product-name']) for r in returns]:
        value=classify_game(asin,title or '',identities)
        if value[0]:class_candidates[asin].append(value)
    asin_classes={asin:Counter(values).most_common(1)[0][0] for asin,values in class_candidates.items()}
    cases = {r['row']['lpn']: r['row'] for r in read('cases') if r['row'].get('lpn')}
    cost_sources = {}
    for name, field in [('backfill_costs', 'active_cost_per_unit'), ('legacy_costs', 'cost_per_unit')]:
        groups = defaultdict(list)
        for r in read(name): groups[r['seller_sku']].append(r)
        for sku, rows in groups.items():
            costs = {number(r[field]) for r in rows if number(r[field]) is not None}
            if len(costs) == 1: cost_sources[sku] = (costs.pop(), 'inventorylab_existing_sku_method')
    sm = defaultdict(list)
    for s in sales:
        s['is_game'], s['system'], s['classification'] = asin_classes.get(s['asin'],(False,'Unclassified','No reliable game match'))
        s['sold_units'] = int(s.get('quantity_shipped') or 0)
        sm[(s['amazon_order_id'], s['seller_sku'])].append(s)
    fresh = [t for f in sorted(cache.glob('finance_live_*.json')) for t in json.loads(f.read_text())]
    tx = unique_transactions(read('transactions'), fresh)
    tm = defaultdict(list)
    for t in tx:
        if t.get('transactionStatus') in RELEASED:
            for item in t.get('items') or []:
                tm[(transaction_order_id(t), item_sku(item))].append((t,item))
    # Keep distinct LPNs, even when one order has two units returned.
    unique = {}
    for r in returns:
        key = (r['order-id'],r['sku'],r.get('license-plate-number') or r['return-date'])
        if key in unique and unique[key] != r: raise ValueError('Conflicting return evidence')
        unique[key] = r
    returns = list(unique.values())
    return_groups = defaultdict(list)
    for r in returns: return_groups[(r['order-id'],r['sku'])].append(r)
    reimbursement_groups = defaultdict(list)
    seen = set()
    for r in reimbursements:
        key = tuple(sorted(r.items()))
        if key in seen: continue
        seen.add(key)
        reimbursement_groups[(r.get('amazon-order-id'),r.get('sku'))].append(r)
    fee_audit=[]; detail=[]
    for key, group in return_groups.items():
        candidates=sm[key]; sale=candidates[0] if len(candidates)==1 else None
        return_qty=sum(int(r['quantity']) for r in group)
        sold_qty=(sale or {}).get('sold_units',0)
        basis=None; basis_source='missing'
        if sale and sale.get('cogs') is not None and sale.get('cogs_quantity'):
            basis=number(sale['cogs'])/number(sale['cogs_quantity']);basis_source=sale['cogs_source']
        elif key[1] in cost_sources: basis,basis_source=cost_sources[key[1]]
        ledger=tm[key]
        flags=[]
        if not sale: flags.append('ambiguous_or_missing_sale')
        if not any(t['transactionType']=='Shipment' for t,i in ledger):flags.append('missing_posted_shipment')
        if not any(t['transactionType']=='Refund' for t,i in ledger):flags.append('missing_posted_refund')
        if return_qty!=sold_qty:flags.append('partial_quantity_no_original_fee_allocation')
        currencies={((i.get('totalAmount') or {}).get('currencyCode')) for t,i in ledger}
        if currencies-{'USD'}:flags.append('non_USD_or_unknown_currency')
        gross=ZERO;credits=ZERO; orig_fba=ZERO; orig_referral=ZERO; fba_credit=ZERO;referral_credit=ZERO;admin=ZERO;processing=ZERO;removal=ZERO; revenue=ZERO;refund=ZERO
        for t,i in ledger:
            typ=t['transactionType'];fees,principal=item_components(i)
            if typ=='Shipment':revenue+=principal
            elif typ=='Refund':refund-=principal
            elif typ=='FBAInventoryReimbursement':continue  # report is the only offset source
            elif typ.startswith('ServiceFee'):
                if t.get('description') not in ('FBACustomerReturn','FBADisposal','FBARemoval'):
                    flags.append('unclassified_service_fee')
            else:
                flags.append('unclassified_adjustment');continue
            for kind,value in fees:
                fee_audit.append({'order_id':key[0],'sku':key[1],'transaction_id':t['transactionId'],'posted_date':t['postedDate'],'transaction_status':t['transactionStatus'],'transaction_type':typ,'description':t.get('description'),'fee_type':kind,'signed_amount_usd':value})
                gross+=max(-value,ZERO);credits+=max(value,ZERO)
                if typ=='Shipment' and kind=='Commission':orig_referral-=value
                if typ=='Shipment' and ('Fulfillment' in kind or 'FBA' in kind):orig_fba-=value
                if typ=='Refund' and kind=='Commission':referral_credit+=value
                if typ=='Refund' and ('Fulfillment' in kind or 'FBA' in kind):fba_credit+=value
                if kind=='RefundCommission':admin-=value
                if 'CustomerReturn' in kind:processing-=value
                if 'Disposal' in kind or 'Removal' in kind:removal-=value
        if abs(revenue-refund)>Decimal('0.05') and revenue and refund:
            flags.append('principal_difference_review')
        fees_complete=not flags
        # All line-level values can be shared only across returned units of that exact line.
        # Partial quantity lines remain explicitly excluded from economic totals.
        tx_cost=(gross-credits)/return_qty if fees_complete else None
        reimb_rows=reimbursement_groups[key]
        reimb=sum((number(r.get('amount-total')) or ZERO for r in reimb_rows if r.get('currency-unit')=='USD'),ZERO)
        if any(r.get('currency-unit')!='USD' for r in reimb_rows): flags.append('unknown_reimbursement_currency');tx_cost=None
        inventory_reimb=sum(int(r.get('quantity-reimbursed-inventory') or 0) for r in reimb_rows)
        if inventory_reimb:flags.append('inventory_reimbursement_requires_unit_reconciliation')
        for r in group:
            case=cases.get(r.get('license-plate-number'),{})
            disp=r['detailed-disposition'];outcome='unknown';impairment=None
            if disp=='SELLABLE': outcome='sellable';impairment=ZERO
            elif disp in ('CUSTOMER_DAMAGED','DEFECTIVE'):outcome='unsellable_recovery_unknown'
            if case.get('inspected_at') and case.get('decision')=='send_back_to_amazon' and re.search(r'condition=New(?:\b|\.)',case.get('evidence_summary') or ''):outcome='inspected_sellable';impairment=ZERO
            if case.get('workflow_state')=='disposed_donated':outcome='disposed_donated';impairment=basis
            if reimb or inventory_reimb:outcome='amazon_reimbursed'
            reimbursement=reimb/return_qty
            known,upper=loss_bounds(tx_cost,basis,impairment,reimbursement,inventory_reimb)
            is_game,system,classification=asin_classes.get(r['asin'],(False,'Unclassified','No reliable game match'))
            sale_date=(sale or {}).get('purchase_date','')[:10]
            detail.append({'order_id':key[0],'sku':key[1],'asin':r['asin'],'fnsku':r['fnsku'],'title':r['product-name'],'is_video_game':is_game,'system':system,'classification_source':classification,'original_condition':(sale or {}).get('condition_id'),'current_sku_condition':skus.get(key[1],{}).get('condition'),'sale_date':sale_date,'return_date':r['return-date'][:10],'quantity':int(r['quantity']),'sold_line_quantity':sold_qty,'lpn':r.get('license-plate-number'),'fulfillment_center':r['fulfillment-center-id'],'raw_disposition':disp,'raw_reason':r['reason'],'raw_status':r['status'],'economic_outcome':outcome,'case_id':case.get('amazon_return_recovery_case_id'),'unit_cost':basis,'cost_source':basis_source,'sale_price_per_unit':number(sale['item_price_amount'])/sold_qty if sale and sold_qty and sale.get('item_price_amount') is not None else None,'original_revenue_line':revenue,'customer_refund_line':refund,'gross_fees_per_returned_unit':gross/return_qty if fees_complete else None,'fee_credits_per_returned_unit':credits/return_qty if fees_complete else None,'original_fba_fee_per_returned_unit':orig_fba/return_qty if fees_complete else None,'original_referral_fee_per_returned_unit':orig_referral/return_qty if fees_complete else None,'fba_fee_credit_per_returned_unit':fba_credit/return_qty if fees_complete else None,'referral_fee_credit_per_returned_unit':referral_credit/return_qty if fees_complete else None,'refund_admin_fee_per_returned_unit':admin/return_qty if fees_complete else None,'return_processing_fee_per_returned_unit':processing/return_qty if fees_complete else None,'removal_fee_per_returned_unit':removal/return_qty if fees_complete else None,'net_transaction_cost':tx_cost,'reimbursement':reimbursement,'reimbursement_ids':';'.join(sorted({x['reimbursement-id'] for x in reimb_rows})),'reimbursement_inventory_units':inventory_reimb,'known_recovery_value':None,'known_impairment':impairment,'known_loss_excluding_unknown_impairment':known,'zero_recovery_loss_known_basis':upper,'reconciliation_status':';'.join(sorted(set(flags))) or 'posted_fees_reconciled','cohort_in_period':bool(sale_date and start<=sale_date<end),'return_in_period':start<=r['return-date'][:10]<end})
    eligible=[s for s in sales if s['fulfillment_channel'] in ('Amazon','AFN') and s['order_status'].startswith('Shipped') and start<=s['purchase_date'][:10]<end and not s.get('is_replacement_order') and (s.get('marketplace_id')=='ATVPDKIKX0DER' or s.get('item_price_currency')=='USD')]
    eligible_keys={(s['amazon_order_id'],s['seller_sku']) for s in eligible}
    for r in detail:r['cohort_in_period']=(r['order_id'],r['sku']) in eligible_keys
    def summarize(ss,rr):
        units=sum(s['sold_units'] for s in ss);returned=sum(r['quantity'] for r in rr)
        complete=[r for r in rr if r['net_transaction_cost'] is not None]
        def total(field):return sum((r[field]*r['quantity'] for r in rr if r[field] is not None),ZERO)
        costs=[r['net_transaction_cost'] for r in complete for _ in range(r['quantity'])]
        known_components=total('net_transaction_cost')+total('known_impairment')-total('reimbursement')
        unknown_basis=sum((r['unit_cost']*r['quantity'] for r in rr if r['known_impairment'] is None and r['unit_cost'] is not None),ZERO)
        return {'units_sold':units,'returned_units_observed':returned,'return_rate':returned/units if units else None,'fee_reconciled_units':sum(r['quantity'] for r in complete),'basis_known_units':sum(r['quantity'] for r in rr if r['unit_cost'] is not None),'gross_fees_reconciled':total('gross_fees_per_returned_unit'),'fee_credits_reconciled':total('fee_credits_per_returned_unit'),'net_transaction_cost_reconciled':total('net_transaction_cost'),'reimbursements_linked':total('reimbursement'),'known_impairment':total('known_impairment'),'known_economic_components_partial_coverage':known_components,'known_loss_fee_reconciled_subset':total('known_loss_excluding_unknown_impairment'),'zero_recovery_known_components_plus_known_basis':known_components+unknown_basis,'unknown_impairment_known_basis':unknown_basis,'unknown_impairment_missing_basis_units':sum(r['quantity'] for r in rr if r['known_impairment'] is None and r['unit_cost'] is None),'mean_transaction_cost_reconciled':sum(costs,ZERO)/len(costs) if costs else None,'median_transaction_cost_reconciled':median(costs) if costs else None,'mean_known_loss_fee_reconciled':total('known_loss_excluding_unknown_impairment')/sum(r['quantity'] for r in complete) if complete else None,'known_cost_per_unit_sold_partial_coverage':known_components/units if units else None,'zero_recovery_cost_per_unit_sold_partial_coverage':(known_components+unknown_basis)/units if units else None,'full_maximum_loss':None,'dispositions':dict(Counter(r['raw_disposition'] for r in rr)),'outcomes':dict(Counter(r['economic_outcome'] for r in rr)),'original_fba_fees':total('original_fba_fee_per_returned_unit'),'original_referral_fees':total('original_referral_fee_per_returned_unit'),'referral_credits':total('referral_fee_credit_per_returned_unit'),'fba_credits':total('fba_fee_credit_per_returned_unit'),'refund_admin_fees':total('refund_admin_fee_per_returned_unit'),'return_processing_fees':total('return_processing_fee_per_returned_unit'),'removal_fees':total('removal_fee_per_returned_unit')}
    cohort=[r for r in detail if r['cohort_in_period']]
    summary={'start':start,'end_exclusive':end,'returns_observed_through':'2026-09-08','all_report_return_units':sum(r['quantity'] for r in detail),'overall':summarize(eligible,cohort),'video_games':summarize([s for s in eligible if s['is_game']],[r for r in cohort if r['is_video_game']]),'calendar_return_units':sum(r['quantity'] for r in detail if r['return_in_period']),'reconciliation_flags':dict(Counter(r['reconciliation_status'] for r in detail)),'fresh_finance_transactions':len(fresh),'reimbursement_report_rows':len(reimbursements),'unique_return_rows':len(detail)}
    refund_only=[]
    for key in sorted(eligible_keys-set(return_groups)):
        for transaction,item in tm[key]:
            if transaction['transactionType']!='Refund':continue
            fees,principal=item_components(item)
            refund_only.append({'order_id':key[0],'sku':key[1],'transaction_id':transaction['transactionId'],'posted_date':transaction['postedDate'],'customer_principal_refund':-principal,'net_refund_fee_credit':sum((value for kind,value in fees),ZERO),'status':'Posted refund without physical-return report match; not counted as a returned unit'})
    summary['refund_only_sale_lines']=len({(r['order_id'],r['sku']) for r in refund_only})
    summary['refund_only_transactions']=len(refund_only)
    segments=[]
    for dim in ('asin','system','month','reason','disposition','sale_price_band','cost_band'):
        def band(v):return 'Unknown' if v is None else ('Under $20' if v<20 else '$20–39.99' if v<40 else '$40–59.99' if v<60 else '$60+')
        def sk(s):
            return s['asin'] if dim=='asin' else s['system'] if dim=='system' else s['purchase_date'][:7] if dim=='month' else band(number(s['item_price_amount'])/s['sold_units'] if s['item_price_amount'] is not None and s['sold_units'] else None) if dim=='sale_price_band' else band(number(s['cogs'])/number(s['cogs_quantity']) if s['cogs'] is not None and s['cogs_quantity'] else None) if dim=='cost_band' else None
        def rk(r):return r['asin'] if dim=='asin' else r['system'] if dim=='system' else r['sale_date'][:7] if dim=='month' else r['raw_reason'] if dim=='reason' else r['raw_disposition'] if dim=='disposition' else band(r['sale_price_per_unit']) if dim=='sale_price_band' else band(r['unit_cost'])
        for key in sorted({rk(r) for r in cohort}|{sk(s) for s in eligible if sk(s) is not None}):
            rs=[r for r in cohort if rk(r)==key];ss=[s for s in eligible if sk(s)==key]
            a=summarize(ss,rs)
            segments.append({'dimension':dim,'value':key,'title':next((s['title'] for s in ss),'') if dim=='asin' else '',**{k:v for k,v in a.items() if not isinstance(v,dict)}})
    output.mkdir(parents=True,exist_ok=True)
    csv_write(output/'return_detail.csv',detail)
    csv_write(output/'fee_events.csv',fee_audit)
    csv_write(output/'segments.csv',segments)
    csv_write(output/'sales_denominator.csv',[{k:s.get(k) for k in ('amazon_order_id','amazon_order_item_id','asin','seller_sku','title','purchase_date','sold_units','is_game','system','classification','cogs','cogs_source')} for s in eligible])
    csv_write(output/'refunds_without_physical_return.csv',refund_only)
    (output/'summary.json').write_text(json.dumps(summary,indent=2,default=json_default),encoding='utf-8')
    print(json.dumps(summary,indent=2,default=json_default))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',default='2025-09-01')
    parser.add_argument('--end',default='2026-09-01')
    args=parser.parse_args()
    run(args.cache,args.output,args.start,args.end)
