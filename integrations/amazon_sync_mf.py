"""Read Amazon MF offers/orders; persist atomic inventory effects without PII or marketplace writes."""
import logging,os,time,uuid
from datetime import datetime,timedelta,timezone
from dotenv import load_dotenv
from supabase import create_client
from amazon_spapi_client import AmazonSPAPIClient
from amazon_mf import order_items,offer
from amazon_mf_listings import discover_listings
from sourcing_database_guard import wait_for_database

LOG=logging.getLogger('amazon_mf_sync')
def now(): return datetime.now(timezone.utc)
def stamp(d): return d.isoformat()
def rpc(db,name,**args): return db.rpc(name,args).execute().data

def pages(client,path,params,key,token_param,*,delay,max_pages=100):
    seen=set()
    for _ in range(max_pages):
        response=client.request('GET',path,params=params)
        if not isinstance(response.get(key),list): raise ValueError(f'Amazon {key} missing; sync incomplete')
        yield from response[key]
        token=(response.get('pagination') or {}).get('nextToken')
        if not token:return
        if token in seen:raise ValueError('Repeated Amazon pagination token')
        seen.add(token);params={**params,token_param:token};time.sleep(delay)
    raise ValueError('MF sync page budget exhausted; checkpoint not advanced')

def synchronize(db,client,run_id):
    seller=client.config.seller_id;market=client.config.marketplace_id
    if not seller:raise ValueError('Missing AMAZON_SP_API_SELLER_ID (or AMAZON_SELLER_ID / AMAZON_MERCHANT_ID) in scheduler configuration')
    configured_rows=db.table('amazon_mf_accounts').select('seller_id,marketplace_id').eq('configured',True).limit(1).execute().data
    configured=configured_rows[0] if configured_rows else None
    if configured and (configured['seller_id']!=seller or configured['marketplace_id']!=market):raise ValueError('Configured MF seller/marketplace differs from scheduler credentials; no inventory was reassigned')
    account=db.table('amazon_mf_accounts').upsert({'seller_id':seller,'marketplace_id':market},on_conflict='seller_id,marketplace_id').execute().data[0]
    aid=account['id'];started=db.table('amazon_mf_sync_runs').select('started_at').eq('id',run_id).single().execute().data['started_at']
    db.table('amazon_mf_sync_runs').update({'account_id':aid}).eq('id',run_id).execute()
    db.table('amazon_mf_accounts').update({'last_attempt_at':started}).eq('id',aid).execute()
    rpc(db,'mbop_mf_register_lots')
    through=now()-timedelta(minutes=3)
    lower=datetime.fromisoformat(account['orders_through'])-timedelta(minutes=10) if account.get('orders_through') else now()-timedelta(days=30)
    stats={'orders':0,'items':0,'offers':0};seen_orders=set()
    order_params={'marketplaceIds':market,'fulfilledBy':'MERCHANT','lastUpdatedAfter':stamp(lower),'lastUpdatedBefore':stamp(through),'maxResultsPerPage':'100','includedData':'FULFILLMENT,CANCELLATION'}
    for order in pages(client,'/orders/2026-01-01/orders',order_params,'orders','paginationToken',delay=180):
        seen_orders.add(order.get('orderId'));stats['orders']+=1
        for item in order_items(order,market):rpc(db,'mbop_mf_apply_order',p_account=aid,p_item=item);stats['items']+=1
    if not account.get('last_success_at'):
        open_params={**order_params,'lastUpdatedAfter':stamp(now()-timedelta(days=729)),'fulfillmentStatuses':'PENDING_AVAILABILITY,PENDING,UNSHIPPED,PARTIALLY_SHIPPED'}
        for order in pages(client,'/orders/2026-01-01/orders',open_params,'orders','paginationToken',delay=180):
            if order.get('orderId') in seen_orders:continue
            seen_orders.add(order.get('orderId'));stats['orders']+=1
            for item in order_items(order,market):rpc(db,'mbop_mf_apply_order',p_account=aid,p_item=item);stats['items']+=1
    # Explicitly revisit older outstanding orders too; a rolling lookback is not a cancellation strategy.
    offset=0;open_ids=set()
    while True:
        rows=db.table('amazon_mf_order_items').select('amazon_order_id').eq('account_id',aid).gt('reservation_demand',0).order('id').range(offset,offset+499).execute().data
        open_ids.update(x['amazon_order_id'] for x in rows)
        if len(rows)<500:break
        offset+=500
    for oid in sorted(open_ids-seen_orders):
        order=client.get_order(oid)
        for item in order_items(order,market):rpc(db,'mbop_mf_apply_order',p_account=aid,p_item=item);stats['items']+=1
        time.sleep(2.2)
    observed=stamp(now());stats['offers_observed_at']=observed
    listings,calls=discover_listings(client,seller,market,observed)
    stats['listings_read']=len(listings);stats['listing_api_calls']=calls
    for item in listings:
        row=offer(item,market,observed,run_id)
        if row:rpc(db,'mbop_mf_apply_offer',p_account=aid,p_offer=row);stats['offers']+=1
    rpc(db,'mbop_mf_allocate',p_account=aid)
    rpc(db,'mbop_mf_sync_finish',p_run=run_id,p_through=stamp(through),p_error=None,p_stats=stats)
    LOG.info('MF synchronization completed: %s',stats)
    return stats

def main():
    logging.basicConfig(level=logging.INFO);logging.getLogger('httpx').setLevel(logging.WARNING)
    load_dotenv();load_dotenv('.env.local');db=None;run_id=None
    try:
        db=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
        run_id=str(uuid.uuid4());db.table('amazon_mf_sync_runs').insert({'id':run_id}).execute()
        wait_for_database(db,attempts=1)
        client=AmazonSPAPIClient.from_env()
        synchronize(db,client,run_id);return 0
    except Exception as error:
        LOG.exception('MF synchronization failed: %s',error)
        if db and run_id:
            try:rpc(db,'mbop_mf_sync_finish',p_run=run_id,p_through=None,p_error=str(error)[:2000],p_stats={})
            except Exception:LOG.exception('Could not persist MF failure')
        return 1
if __name__=='__main__':raise SystemExit(main())
