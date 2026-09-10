"""Offline FBA inbound/storage economics from cached, read-only evidence.

No source writes or changes to sourcing, FIFO, accounting, or scheduler behavior.
See docs/AMAZON_INBOUND_STORAGE_ECONOMICS.md for collection and coverage.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import median
from analyze_amazon_return_economics import classify_game, csv_write, json_default, RELEASED

D=Decimal
ZERO=D(0)
CATEGORIES={'FBAPostInboundTransportation':'carrier','FBAInboundConvenience':'placement',
            'FBAStorageBilling':'storage','FBALongTermStorageBilling':'aged',
            'FBAStorageFeeAdjustment':'storage_adjustment'}

def num(v):
    return D(str(v)) if v not in (None,'','--') else None

def ratio(a,b):
    return a/b if b else None

def next_month(month):
    y,m=map(int,month.split('-'))
    return f'{y+1}-01' if m==12 else f'{y}-{m+1:02d}'

def percentile(values,q):
    if not values:return None
    vals=sorted(values);pos=D(str(q))*(len(vals)-1);lo=int(pos)
    return vals[lo]+(vals[min(lo+1,len(vals)-1)]-vals[lo])*(pos-lo)

def holding_cost(monthly,days):
    return monthly*D(days)*D(12)/D(365) if monthly is not None else None

def seasonal_holding(normal,q4,days):
    """Calendar bounds: Q4 has 92 days, so a year cannot be all-Q4."""
    if normal is None or q4 is None:return None,None
    least=max(0,days-273);most=min(days,92)
    return tuple(holding_cost(normal,days-q)+holding_cost(q4,q) for q in (least,most))

def fee_rows(transactions,start,end):
    """Transactions were release-deduplicated at collection. Keep signed reversals."""
    rows=[];seen={}
    for t in transactions:
        tid=t['transactionId']
        if tid in seen:
            if seen[tid]!=t:raise ValueError('Conflicting transaction versions')
            continue
        seen[tid]=t
        if t.get('description') not in CATEGORIES or t.get('transactionStatus') not in RELEASED:continue
        if not start<=t['postedDate'][:10]<end:continue
        if t['totalAmount']['currencyCode']!='USD':raise ValueError('Non-USD transaction')
        refs={r['relatedIdentifierName']:r['relatedIdentifierValue'] for r in t.get('relatedIdentifiers') or []}
        sid=refs.get('ORDER_ID','')
        rows.append({'transaction_id':tid,'posted_date':t['postedDate'],
                     'category':CATEGORIES[t['description']],'description':t['description'],
                     'transaction_type':t['transactionType'],'shipment_id':sid if sid.startswith('FBA') else '',
                     'cost_usd':-num(t['totalAmount']['currencyAmount'])})
    return rows

def summarize_shipments(rows,field):
    eligible=[r for r in rows if r.get(field) is not None and r['units']>0]
    units=sum(r['units'] for r in eligible);cost=sum((r[field] for r in eligible),ZERO)
    game_units=sum(r['game_units'] for r in eligible)
    game_cost=sum((r[field]*D(r['game_units'])/r['units'] for r in eligible),ZERO)
    rates=[r[field]/r['units'] for r in eligible]
    boxed=[r for r in eligible if r.get('boxes')]
    weighted=[r for r in eligible if r.get('game_weight_share') is not None]
    weight_games=sum(r['game_units'] for r in weighted)
    weight_cost=sum((r[field]*r['game_weight_share'] for r in weighted),ZERO)
    return {'shipments':len(eligible),'units':units,'cost':cost,'weighted_per_unit':ratio(cost,D(units)),
            'median_shipment_per_unit':median(rates) if rates else None,
            'p25':percentile(rates,.25),'p75':percentile(rates,.75),
            'min':min(rates) if rates else None,'max':max(rates) if rates else None,
            'game_units':game_units,'allocated_game_cost':game_cost,'allocated_per_game':ratio(game_cost,D(game_units)),
            'box_sample_shipments':len(boxed),'boxes':sum(r['boxes'] for r in boxed),
            'cost_per_box':ratio(sum((r[field] for r in boxed),ZERO),D(sum(r['boxes'] for r in boxed))),
            'units_per_box':ratio(D(sum(r['units'] for r in boxed)),D(sum(r['boxes'] for r in boxed))),
            'weight_allocation_shipments':len(weighted),'weight_allocation_game_units':weight_games,
            'weight_allocated_game_cost':weight_cost,'weight_allocated_per_game':ratio(weight_cost,D(weight_games)),
            'same_weight_sample_unit_allocated_per_game':ratio(sum((r[field]*D(r['game_units'])/r['units'] for r in weighted),ZERO),D(weight_games))}

def run(cache,previous,output,start='2025-09-01',end='2026-09-01'):
    def read(name,root=cache):
        path=root/(name+'.json')
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    output.mkdir(parents=True,exist_ok=True)
    identities={r['asin']:r for r in read('identities',previous)}
    skus={r['seller_sku']:r for r in read('skus',previous)}
    titles=defaultdict(set)
    for r in skus.values():titles[r['asin']].add(r.get('product_name') or '')
    for r in read('sales',previous):titles[r['asin']].add(r.get('title') or '')
    weights=defaultdict(set)
    for f in sorted(cache.glob('storage_*.json')):
        for r in json.loads(f.read_text()):
            titles[r['asin']].add(r.get('product-name') or '')
            if r.get('weight-units')=='pounds' and num(r.get('weight')) and num(r['weight'])>0:weights[r['asin']].add(num(r['weight']))
    weights={a:median(v) for a,v in weights.items()}
    def game(asin,title=''):
        return any(classify_game(asin,t,identities)[0] for t in titles.get(asin,set())|{title or ''})
    # Also retain September charges only for August storage reconciliation.
    all_fees=fee_rows(read('fees'),'2025-01-01','2026-09-10')
    fees=[r for r in all_fees if start<=r['posted_date'][:10]<end]
    csv_write(output/'fee_transactions.csv',fees)
    charged=defaultdict(lambda:defaultdict(list))
    for r in fees:
        if r['shipment_id']:charged[r['shipment_id']][r['category']].append(r)
    stored={r['shipment_code']:r for r in read('shipments')}
    local_items=defaultdict(list)
    for r in read('shipment_items')+read('source_items'):
        if r['included']:local_items[r['fba_shipment_id']].append(r)
    shipments=[];details=[]
    for sid,costs in sorted(charged.items()):
        s=stored.get(sid,{})
        raw=(s.get('raw_tracking_json') or {}).get('raw') or {}
        boxes=raw.get('boxes') or []
        items=[];source=''
        if boxes:
            source='stored Amazon box contents'
            for box in boxes:
                for r in box.get('items') or []:
                    items.append({'asin':r.get('asin'),'sku':r.get('msku'),'quantity':int(r['quantity'])*int(box.get('quantity',1))})
        elif (cache/('items_'+sid+'.json')).exists():
            source='Amazon legacy shipment items'
            for r in read('items_'+sid):
                identity=skus.get(r['SellerSKU'],{})
                items.append({'asin':r.get('ASIN') or identity.get('asin'),'sku':r['SellerSKU'],'quantity':int(r['QuantityShipped'])})
        elif s:
            source='included MBOP shipment and recovery source items'
            for r in local_items[s['fba_shipment_id']]:
                items.append({'asin':r.get('asin'),'sku':r.get('seller_sku'),'quantity':int(r['quantity'])})
        units=sum(r['quantity'] for r in items)
        expected=s.get('units_sent')
        game_units=sum(r['quantity'] for r in items if game(r['asin']))
        unknown_units=sum(r['quantity'] for r in items if not r['asin'])
        weighted_ok=bool(items) and all(r['asin'] in weights for r in items if r['quantity'])
        total_weight=sum((weights.get(r['asin'],ZERO)*r['quantity'] for r in items),ZERO)
        game_weight=sum((weights.get(r['asin'],ZERO)*r['quantity'] for r in items if game(r['asin'])),ZERO)
        values={k:sum((r['cost_usd'] for r in costs[k]),ZERO) if costs[k] else None for k in ('carrier','placement')}
        combined=values['carrier']+values['placement'] if all(v is not None for v in values.values()) else None
        options=raw.get('transportationOptions') or []
        selected=(s.get('raw_amazon_shipment_json') or {}).get('selectedTransportationOptionId')
        option=next((o for o in options if o.get('transportationOptionId')==selected),{})
        row={'shipment_id':sid,'shipment_date':s.get('carrier_pickup_at') or '',
             'finalized_or_plan_created':s.get('finalized_at') or '',
             'first_charge_date':min(r['posted_date'][:10] for rs in costs.values() for r in rs),
             'units':units,'mbop_header_units':expected,'header_unit_difference':units-expected if expected is not None else None,
             'game_units':game_units,'unmapped_units':unknown_units,'quantity_source':source,
             'game_weight_share':ratio(game_weight,total_weight) if weighted_ok else None,
             'boxes':sum(int(b.get('quantity',1)) for b in boxes) or None,
             'carrier_name':s.get('carrier_name') or (option.get('carrier') or {}).get('name') or '',
             'selected_quote':num(((option.get('quote') or {}).get('cost') or {}).get('amount')),
             **values,'combined':combined,
             'carrier_per_unit':ratio(values['carrier'],D(units)) if values['carrier'] is not None else None,
             'placement_per_unit':ratio(values['placement'],D(units)) if values['placement'] is not None else None,
             'combined_per_unit':ratio(combined,D(units)) if combined is not None else None}
        shipments.append(row)
        for r in items:
            title=(skus.get(r['sku']) or {}).get('product_name') or next(iter(sorted(titles.get(r['asin'],set()))),'')
            details.append({'shipment_id':sid,**r,'title':title,'is_game':game(r['asin'])})
    csv_write(output/'shipment_costs.csv',shipments);csv_write(output/'shipment_units.csv',details)
    monthly=[];storage_detail=[];aged_detail=[]
    for f in sorted(cache.glob('storage_*.json')):
        month=f.stem.removeprefix('storage_')
        if not start[:7]<=month<end[:7]:continue
        rows=json.loads(f.read_text());seen=set()
        for i,r in enumerate(rows):
            if r['month-of-charge']!=month:raise ValueError('Wrong storage month')
            if r['country-code']!='US' or r['currency']!='USD':continue
            key=tuple(sorted(r.items()))
            if key in seen:raise ValueError('Duplicate storage row requires review')
            seen.add(key)
            storage_detail.append({'month':month,'source_row':i+1,'asin':r['asin'],'fnsku':r['fnsku'],
                'title':r['product-name'],'fc':r['fulfillment-center'],'is_game':game(r['asin'],r['product-name']),
                'avg_units':num(r['average-quantity-on-hand']),'base_cost':num(r['est-base-msf']),
                'utilization_surcharge':num(r['est-sus']),'total_estimated_cost':num(r['estimated-monthly-storage-fee']),
                'incentive':num(r['total-incentive-fee-amount']),'unit_volume_cuft':num(r['item-volume']),
                'unit_weight_lb':num(r['weight']) if r['weight-units']=='pounds' else None})
        lines=[r for r in storage_detail if r['month']==month]
        games=[r for r in lines if r['is_game']]
        total=sum((r['total_estimated_cost'] for r in lines),ZERO)
        posted=[r for r in all_fees if r['category']=='storage' and r['transaction_type']=='ServiceFee' and r['posted_date'][:7]==next_month(month)]
        cash=sum((r['cost_usd'] for r in posted),ZERO) if posted else None
        units=sum((r['avg_units'] for r in games),ZERO)
        game_base=sum((r['base_cost'] for r in games),ZERO)
        monthly.append({'month':month,'rows':len(lines),'asins':len({r['asin'] for r in lines}),
                        'average_units':sum((r['avg_units'] for r in lines),ZERO),'game_asins':len({r['asin'] for r in games}),
                        'game_average_units':units,'base_cost':sum((r['base_cost'] for r in lines),ZERO),
                        'utilization_surcharge':sum((r['utilization_surcharge'] for r in lines),ZERO),
                        'report_total':total,'posted_next_month':cash,'reconciliation_difference':cash-total if cash is not None else None,
                        'game_base_cost':game_base,'game_monthly_rate':ratio(game_base,units)})
    for f in sorted(cache.glob('aged_*.json')):
        month=f.stem.removeprefix('aged_')
        if not start[:7]<=month<end[:7]:continue
        for i,r in enumerate(json.loads(f.read_text())):
            if r['snapshot-date'][:7]!=month:raise ValueError('Wrong aged month')
            if r['country']!='US' or r['currency']!='USD':continue
            aged_detail.append({'month':month,'source_row':i+1,'asin':r['asin'],'sku':r['sku'],
                               'is_game':game(r['asin'],r['product-name']),'age_tier':r['surcharge-age-tier'],
                               'units_charged':num(r['qty-charged']),'cost':num(r['amount-charged'])})
    csv_write(output/'storage_monthly.csv',monthly);csv_write(output/'storage_detail.csv',storage_detail)
    csv_write(output/'aged_detail.csv',aged_detail)
    aged_monthly=[]
    for month in sorted({r['month'] for r in aged_detail}):
        lines=[r for r in aged_detail if r['month']==month]
        cost=sum((r['cost'] for r in lines),ZERO)
        cash=sum((r['cost_usd'] for r in fees if r['category']=='aged' and r['posted_date'][:7]==month),ZERO)
        aged_monthly.append({'month':month,'report_cost':cost,'posted_cost':cash,'difference':cost-cash,
                             'game_report_cost':sum((r['cost'] for r in lines if r['is_game']),ZERO),
                             'game_unit_assessments':sum((r['units_charged'] for r in lines if r['is_game']),ZERO)})
    csv_write(output/'aged_monthly.csv',aged_monthly)
    def season(rows):
        u=sum((r['game_average_units'] for r in rows),ZERO);c=sum((r['game_base_cost'] for r in rows),ZERO)
        # Median is per ASIN-month, not per fulfillment center row.
        grouped=defaultdict(lambda:[ZERO,ZERO])
        months={r['month'] for r in rows}
        for r in storage_detail:
            if r['is_game'] and r['month'] in months:
                grouped[(r['month'],r['asin'])][0]+=r['base_cost'];grouped[(r['month'],r['asin'])][1]+=r['avg_units']
        rates=[c/u for c,u in grouped.values() if u]
        return {'months':len(rows),'game_unit_months':u,'game_base_cost':c,'weighted_rate':ratio(c,u),
                'asin_months':len(rates),'median_asin_month_rate':median(rates) if rates else None}
    seasons={'all':season(monthly),'Jan-Sep':season([r for r in monthly if int(r['month'][5:])<=9]),
             'Q4':season([r for r in monthly if int(r['month'][5:])>=10])}
    holding=[]
    for days in (30,60,90,180,365):
        low,high=seasonal_holding(seasons['Jan-Sep']['weighted_rate'],seasons['Q4']['weighted_rate'],days)
        holding.append({'days':days,'inventory_weighted_history':holding_cost(seasons['all']['weighted_rate'],days),
                        'calendar_season_min':low,'calendar_season_max':high})
    csv_write(output/'holding_scenarios.csv',holding)
    aged_groups=defaultdict(lambda:[ZERO,ZERO,set()])
    for r in aged_detail:
        if r['is_game']:
            v=aged_groups[(r['asin'],r['age_tier'])];v[0]+=r['cost'];v[1]+=r['units_charged'];v[2].add(r['month'])
    csv_write(output/'aged_game_concentration.csv',[{'asin':k[0],'age_tier':k[1],'cost':v[0],'unit_assessments':v[1],'months':len(v[2])} for k,v in sorted(aged_groups.items(),key=lambda x:-x[1][0])])
    summary={'start':start,'end_exclusive':end,'posted_costs':{cat:sum((r['cost_usd'] for r in fees if r['category']==cat),ZERO) for cat in CATEGORIES.values()},
             'transaction_counts':{cat:sum(r['category']==cat for r in fees) for cat in CATEGORIES.values()},
             'inbound':{k:summarize_shipments(shipments,k) for k in ('carrier','placement','combined')},
             'storage':seasons,'holding_scenarios':holding,
             'storage_report_rows':len(storage_detail),'storage_game_asins':len({r['asin'] for r in storage_detail if r['is_game']}),
             'storage_report_total':sum((r['report_total'] for r in monthly),ZERO),
             'storage_utilization_surcharge':sum((r['utilization_surcharge'] for r in monthly),ZERO),
             'storage_months':[r['month'] for r in monthly],
             'aged':{'months':sorted({r['month'] for r in aged_detail}),'report_cost':sum((r['cost'] for r in aged_detail),ZERO),
                     'game_cost':sum((r['cost'] for r in aged_detail if r['is_game']),ZERO),
                     'game_asins':len({r['asin'] for r in aged_detail if r['is_game']}),
                     'game_unit_assessments':sum((r['units_charged'] for r in aged_detail if r['is_game']),ZERO)}}
    (output/'summary.json').write_text(json.dumps(summary,default=json_default,indent=2))
    source_files=[f for f in cache.glob('*.json') if f.name not in ('fee_candidates.json',)]
    source_files += [previous/(n+'.json') for n in ('skus','identities','sales')]
    (output/'source_manifest.json').write_text(json.dumps([{'source':str(f.relative_to(Path.cwd())) if f.is_absolute() else str(f),
                                                         'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
                                                        for f in sorted(source_files)],indent=2))
    print(json.dumps(summary,default=json_default,indent=2))
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,required=True);p.add_argument('--previous-cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.cache,args.previous_cache,args.output)
