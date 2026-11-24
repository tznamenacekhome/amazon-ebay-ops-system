"""Account-scoped Browse admission and short-lived detail reuse across MBOP jobs."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import sys
from urllib.parse import unquote, urlparse
import requests
from ebay_api_limits import fetch_rate_limits

RESOURCE = 'buy.browse'
BULK_RESOURCE = 'buy.browse.item.bulk'
TRADING_RESOURCE = 'trading'

def utcnow(): return dt.datetime.now(dt.UTC)
def parsed(value): return dt.datetime.fromisoformat(str(value).replace('Z','+00:00')) if value else None

class EbayQuotaPaused(RuntimeError):
    def __init__(self, reason, retry_at=None, resource=RESOURCE):
        super().__init__(f'eBay {resource} paused: {reason}; retry at {retry_at or "next quota check"}')
        self.retry_at,self.resource,self.reason=retry_at,resource,reason

class BrowseBudget:
    def __init__(self,db,job=None):
        self.db=db
        self.app=hashlib.sha256(os.environ['EBAY_CLIENT_ID'].encode()).hexdigest()[:24]
        self.job=job or os.environ.get('MBOP_EBAY_JOB_NAME') or os.path.basename(sys.argv[0])
    def rpc(self,name,**args): return self.db.rpc(name,args).execute().data
    def refresh(self):
        payload=fetch_rate_limits()
        found=False
        trading=[]
        for api in payload.get('rateLimits',[]):
            for resource in api.get('resources',[]):
                if str(api.get('apiName','')).lower()=='tradingapi':
                    trading.extend(resource.get('rates') or [])
                if resource.get('name') not in (RESOURCE,BULK_RESOURCE,'developer.analytics.app_rate_limit'): continue
                rates=resource.get('rates') or []
                if not rates: continue
                # Do not mistake a healthy short window for an exhausted daily window.
                rate=min(rates,key=lambda r:(int(r.get('remaining',0)), -int(r.get('timeWindow',0))))
                self.rpc('ebay_quota_observe',p_app=self.app,p_resource=resource['name'],p_rate=rate)
                found=found or resource['name']==RESOURCE
        if trading:
            rate=dict(min(trading,key=lambda r:(int(r.get('remaining',0)), -int(r.get('timeWindow',0)))))
            # Per-method counts differ, but all methods share the same remainder.
            rate['count']=max(int(rate['limit'])-int(rate['remaining']),0)
            self.rpc('ebay_quota_observe',p_app=self.app,p_resource=TRADING_RESOURCE,p_rate=rate)
        if not found: raise EbayQuotaPaused('quota evidence unavailable', (utcnow()+dt.timedelta(minutes=5)).isoformat())
    def reserve(self,resource=RESOURCE,*,peek=False,operation='detail',priority=None):
        priority=priority or ('manual' if self.job=='import_flipmine.py' else 'catalog')
        job=('essential:'+self.job) if priority=='essential' else self.job
        for _ in range(2):
            state=self.rpc('ebay_quota_admit',p_app=self.app,p_resource=resource,p_job=job,p_operation=operation,p_priority=priority,p_peek=peek)
            if state.get('refresh'):
                try: self.refresh()
                except EbayQuotaPaused: raise
                except Exception as error:
                    raise EbayQuotaPaused('quota refresh unavailable',(utcnow()+dt.timedelta(minutes=5)).isoformat(),resource) from error
                continue
            if not state.get('allowed'):
                self.notify_pause(resource,state)
                raise EbayQuotaPaused(state.get('reason') or 'quota unavailable',state.get('retry_at'),resource)
            return state
        raise EbayQuotaPaused('quota refresh incomplete',(utcnow()+dt.timedelta(minutes=1)).isoformat(),resource)
    def check(self):
        return self.reserve(peek=True)
    def event(self,event,resource=RESOURCE):
        self.rpc('ebay_api_event',p_app=self.app,p_resource=resource,p_job=self.job,p_event=event)
    def block(self,resource,reason,status=None):
        until=(utcnow()+dt.timedelta(minutes=5)).isoformat()
        self.rpc('ebay_quota_block',p_app=self.app,p_resource=resource,p_until=until,p_reason=reason,p_status=status)
        return EbayQuotaPaused(reason,until,resource)
    def notify_pause(self,resource,state):
        if state.get('reason') not in ('daily_quota_exhausted','protected_operational_capacity','sourcing_fair_share_reached'):return
        key=f'ebay-capacity:{self.app}:{resource}:{utcnow().astimezone(__import__("zoneinfo").ZoneInfo("America/Los_Angeles")).date()}'
        try:
            self.db.table('mbop_notifications').upsert({'dedupe_key':key,'severity':'warning','category':'integration_health',
                'title':f'eBay {resource} sourcing capacity paused','message':f'{state.get("reason")}. Saved work is retained. Next retry: {state.get("retry_at") or "unknown"}.',
                'href':'/system-health'},on_conflict='dedupe_key',ignore_duplicates=True).execute()
        except Exception:
            # Notifications are advisory; quota admission must remain authoritative.
            pass
    def after_429(self,response,delay,resource=RESOURCE,*,exhausted=False):
        # Fetch authoritative daily evidence once, rather than retry each saved row.
        try: self.refresh()
        except Exception: pass
        rows=self.db.table('ebay_api_resource_limits').select('remaining,reset_at,blocked_until').eq('app_key',self.app).eq('resource',resource).limit(1).execute().data or []
        state=rows[0] if rows else {}
        if exhausted:state['remaining']=0
        retry=utcnow()+dt.timedelta(seconds=delay)
        if state.get('remaining',1)<=0 and parsed(state.get('reset_at')):
            retry=max(retry,parsed(state['reset_at']))
        elif exhausted:
            retry=max(retry,utcnow()+dt.timedelta(minutes=5))
        existing=parsed(state.get('blocked_until'))
        if existing: retry=max(retry,existing)
        reason='daily_quota_exhausted' if state.get('remaining',1)<=0 else 'temporary_throttle'
        try: errors=response.json().get('errors',[])[:3]
        except (ValueError,AttributeError): errors=[]
        safe_errors=[{key:error.get(key) for key in ('errorId','domain','category','message','longMessage')} for error in errors if isinstance(error,dict)]
        self.db.table('ebay_api_resource_limits').update({'blocked_until':retry.isoformat(),'reason':reason,'last_http_status':response.status_code,
            'last_error_json':safe_errors,'last_retry_after':response.headers.get('Retry-After'),'last_response_at':utcnow().isoformat()}).eq('app_key',self.app).eq('resource',resource).execute()
        return EbayQuotaPaused(reason,retry.isoformat(),resource)
    def cache_key(self,url,kwargs):
        path=unquote(urlparse(url).path)
        params=kwargs.get('params') or {}
        if path.endswith('/get_item_by_legacy_id'):
            legacy=str(params.get('legacy_item_id') or '')
            if not legacy.isdigit() or params.get('legacy_variation_id'): return None
            item_id=f'v1|{legacy}|0'
        elif '/buy/browse/v1/item/v1|' in path: item_id=path.rsplit('/',1)[-1]
        else: return None
        if params.get('fieldgroups') or params.get('field_groups'): return None
        headers={k.lower():v for k,v in (kwargs.get('headers') or {}).items()}
        quantity=str(params.get('quantity_for_shipping_estimate','1'))
        context=headers.get('x-ebay-c-enduserctx','')
        if quantity!='1':context+=f'|quantity={quantity}'
        return {'app_key':self.app,'marketplace':headers.get('x-ebay-c-marketplace-id','EBAY_US'),
                'item_id':item_id,'buyer_context':context}
    def cached(self,key):
        if not key:return None
        query=self.db.table('ebay_listing_detail_cache').select('payload,fetched_at,expires_at')
        for name,value in key.items():query=query.eq(name,value)
        rows=query.limit(1).execute().data or []
        if not rows or parsed(rows[0]['expires_at'])<=utcnow(): return None
        payload=rows[0]['payload']
        if payload.get('itemId')!=key['item_id'] or not payload.get('title'): return None
        response=requests.Response();response.status_code=200;response._content=json.dumps(payload).encode();response.headers['X-MBOP-Detail-Cache']='hit'
        return response
    def save(self,key,response):
        if not key or response.status_code!=200:return
        payload=response.json()
        if payload.get('itemId')!=key['item_id'] or not payload.get('title'):return
        now=utcnow()
        ttl=max(30,min(int(os.getenv('MBOP_EBAY_EVIDENCE_TTL_SECONDS','900')),900))
        self.db.table('ebay_listing_detail_cache').upsert({**key,'payload':payload,'fetched_at':now.isoformat(),
             'expires_at':(now+dt.timedelta(seconds=ttl)).isoformat()},on_conflict='app_key,marketplace,item_id,buyer_context').execute()

_budget=None
def production_budget():
    global _budget
    enabled=os.environ.get('MBOP_EBAY_QUOTA_GUARD',os.environ.get('CLOUD_DEPLOYMENT','false')).lower() in ('true','1')
    if not enabled:return None
    if _budget is None:
        from sourcing_common import get_supabase_client
        _budget=BrowseBudget(get_supabase_client())
    return _budget

def pending_import_reserve():
    gate=production_budget()
    return int(gate.rpc('ebay_pending_flipmine_calls') or 0) if gate else 0
