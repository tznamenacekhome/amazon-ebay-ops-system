"""Shared listing evidence router. Matching and economics stay in the sourcing engine."""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import time
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

import requests

from ebay_browse_budget import production_budget, EbayQuotaPaused, RESOURCE, TRADING_RESOURCE
from ebay_trading import call, text, elements, TradingError


class ListingUnavailable(ValueError):
    pass


class EvidenceUnavailable(RuntimeError):
    pass


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, TypeError):
        return None


def integer(value):
    value = number(value)
    return int(value) if value is not None and value == int(value) else None


def money(node):
    if node is None or number(node.text) is None or not node.get('currencyID'):
        return None
    return {'value':str(number(node.text)), 'currency':node.get('currencyID')}


def child(node, path):
    values = elements(node, path)
    return values[0] if values else None


def buyer(settings):
    return (str(getattr(settings,'buyer_country','US')), str(getattr(settings,'buyer_zip','')),
            max(int(getattr(settings,'quantity_for_shipping_estimate',1)),1))


def shipping_options(root, settings, *, quoted=False):
    country, zipcode, quantity = buyer(settings)
    detail = child(root,'ShippingDetails')
    if detail is None:
        return []
    exclusions = [e.text for e in elements(detail,'ExcludeShipToLocation')]
    # Flat domestic rates are reusable only when applicability is established.
    included={str(e.text or '').casefold() for e in elements(root,'ShipToLocations')}
    if not quoted and (country != 'US' or text(root,'Country') != 'US' or exclusions or not included.intersection({'us','worldwide'})):
        return []
    shipping_type = text(detail,'ShippingType','')
    if not quoted and shipping_type not in ('Flat','FlatDomesticCalculatedInternational'):
        return []
    options=[]
    for service in elements(detail,'ShippingServiceOptions'):
        name=text(service,'ShippingService','')
        if 'pickup' in name.lower():
            continue
        surcharge=number(text(service,'ShippingSurcharge'))
        if not quoted and surcharge is not None and surcharge>0:continue
        cost=money(child(service,'ShippingServiceCost'))
        if cost is None or cost['currency']!='USD':
            continue
        if quantity>1 and not quoted:
            extra=money(child(service,'ShippingServiceAdditionalCost'))
            if extra is None or extra['currency'] != cost['currency']:
                continue
            cost={**cost,'value':str(Decimal(cost['value'])+(quantity-1)*Decimal(extra['value']))}
        import_cost=money(child(service,'ImportCharge'))
        if import_cost and Decimal(import_cost['value'])>0:
            continue  # Imports require buyer-specific Browse verification.
        options.append({'shippingCost':cost,'shippingCostType':'FIXED', 'shippingServiceCode':name,
                        'mbopBuyerContext':{'country':country,'postalCode':zipcode,'quantity':quantity}})
    return options


def normalize_item(root, settings):
    """Convert public Trading fields into the existing Browse evidence contract."""
    item=child(root,'Item')
    if item is None:
        raise EvidenceUnavailable('Trading response has no item')
    legacy=text(item,'ItemID')
    if not legacy or not legacy.isdigit():
        raise EvidenceUnavailable('Trading response has invalid listing identity')
    quantity,sold=integer(text(item,'Quantity')),integer(text(item,'SellingStatus/QuantitySold'))
    available=max(quantity-sold,0) if quantity is not None and sold is not None else None
    status=text(item,'SellingStatus/ListingStatus')
    ended=status in ('Completed','Ended') or available==0 or text(item,'ListingOnHold')=='true' or text(item,'SellingStatus/ListingOnHold')=='true'
    try:
        end=dt.datetime.fromisoformat(text(item,'ListingDetails/EndTime','').replace('Z','+00:00'))
        if end.tzinfo and end<=dt.datetime.now(dt.UTC):ended=True
    except ValueError:
        pass
    listing_type=text(item,'ListingType')
    options=[]
    auction=listing_type in ('Chinese','Dutch')
    if auction:options.append('AUCTION')
    if listing_type in ('FixedPriceItem','StoresFixedPrice') or text(item,'ListingDetails/BuyItNowAvailable')=='true':options.append('FIXED_PRICE')
    if text(item,'BestOfferDetails/BestOfferEnabled')=='true':options.append('BEST_OFFER')
    images=[{'imageUrl':e.text} for e in elements(item,'PictureDetails/PictureURL') if e.text]
    gallery=text(item,'PictureDetails/GalleryURL')
    if not images and gallery:images=[{'imageUrl':gallery}]
    aspects=[{'name':text(e,'Name'),'value':'; '.join(v.text or '' for v in elements(e,'Value'))}
             for e in elements(item,'ItemSpecifics/NameValueList') if text(e,'Name')]
    price=money(child(item,'SellingStatus/CurrentPrice'))
    bin_price=money(child(item,'BuyItNowPrice'))
    payload={'itemId':f'v1|{legacy}|0','legacyItemId':legacy,'title':text(item,'Title'),
      'description':text(item,'Description'),'conditionId':text(item,'ConditionID'),
      'condition':text(item,'ConditionDisplayName'),'conditionDescription':text(item,'ConditionDescription'),
      'localizedAspects':aspects,'categoryId':text(item,'PrimaryCategory/CategoryID'),
      'categories':[{'categoryId':text(item,'PrimaryCategory/CategoryID'),'categoryName':text(item,'PrimaryCategory/CategoryName')}],
      'categoryPath':text(item,'PrimaryCategory/CategoryName'),'image':images[0] if images else {},
      'additionalImages':images[1:],'seller':{'username':text(item,'Seller/UserID'),
        'feedbackScore':integer(text(item,'Seller/FeedbackScore')),'feedbackPercentage':text(item,'Seller/PositiveFeedbackPercent')},
      'itemLocation':{'country':text(item,'Country'),'postalCode':text(item,'PostalCode'),'city':text(item,'Location')},
      'price':bin_price if auction and 'FIXED_PRICE' in options else price,
      'buyingOptions':options,'itemEndDate':text(item,'ListingDetails/EndTime'),
      'itemWebUrl':text(item,'ListingDetails/ViewItemURL'),
      'estimatedAvailabilities':[{'estimatedAvailabilityStatus':'OUT_OF_STOCK' if ended else 'IN_STOCK' if status=='Active' and available is not None else 'UNKNOWN',
                                 'estimatedAvailableQuantity':available}],
      'shippingOptions':shipping_options(item,settings), 'shipToLocations':{'regionIncluded':[{'regionName':e.text} for e in elements(item,'ShipToLocations')],
         'regionExcluded':[{'regionName':e.text} for e in elements(item,'ShippingDetails/ExcludeShipToLocation')]},
      'mbopEvidence':{'provider':'trading','schemaVersion':1,'listingStatus':status,'ended':ended,'shippingType':text(item,'ShippingDetails/ShippingType'),
                      'revision':text(item,'ReviseStatus/ItemRevised'),'variationUnverified':child(item,'Variations') is not None}}
    if auction:
        payload['currentBidPrice']=price
        payload['bidCount']=integer(text(item,'SellingStatus/BidCount'))
    if child(item,'Variations') is not None:
        payload['itemGroupHref']='trading:variation-requires-browse'
    return payload


SELECTORS=('ItemID','Title','Description','ConditionID','ConditionDisplayName','ConditionDescription','ItemSpecifics',
 'PrimaryCategory','PictureDetails','Seller','Country','PostalCode','Location','SellingStatus','Quantity','ListingType',
 'ListingDetails','BestOfferDetails','BuyItNowPrice','Variations','ShippingDetails','ShipToLocations','ListingOnHold','ReviseStatus')


class ListingRouter:
    def __init__(self, token, settings, *, gate=None):
        self.token,self.settings=token,settings
        self.gate=gate if gate is not None else production_budget()
        self.user_token=None
        self.cache={}

    def event(self,event,resource=RESOURCE):
        if self.gate:self.gate.event(event,resource)

    def check(self):
        if not self.gate:return
        pauses=[]
        resources=[TRADING_RESOURCE,RESOURCE] if self.enabled() else [RESOURCE]
        for resource in resources:
            try:return self.gate.reserve(resource,peek=True)
            except EbayQuotaPaused as error:pauses.append(error)
        raise self.pause(pauses)

    def enabled(self):
        return os.getenv('MBOP_EBAY_TRADING_ENRICHMENT','false').lower() in ('1','true')

    @staticmethod
    def pause(pauses):
        from ebay_browse_budget import parsed
        return min(pauses,key=lambda e:parsed(e.retry_at) if e.retry_at else __import__('datetime').datetime.max.replace(tzinfo=__import__('datetime').UTC))

    def key(self,item_id):
        from ebay_sourcing_search import end_user_context_header
        country,zipcode,quantity=buyer(self.settings)
        context=end_user_context_header(self.settings)
        if quantity!=1:context+=f'|quantity={quantity}'
        return {'app_key':self.gate.app if self.gate else '', 'marketplace':'EBAY_US','item_id':item_id,'buyer_context':context}

    def browse(self,item_id):
        from ebay_sourcing_search import get_with_retries, end_user_context_header
        quantity=buyer(self.settings)[2]
        response,metrics=get_with_retries(f'https://api.ebay.com/buy/browse/v1/item/{item_id}',call_type='detail',
          headers={'Authorization':f'Bearer {self.token}','X-EBAY-C-MARKETPLACE-ID':'EBAY_US',
                   'X-EBAY-C-ENDUSERCTX':end_user_context_header(self.settings)},
          params={'quantity_for_shipping_estimate':str(quantity)},timeout=30)
        if response.status_code in (404,410):raise ListingUnavailable('Listing unavailable from eBay')
        if not response.ok:raise EvidenceUnavailable(f'Browse HTTP {response.status_code}')
        return response.json(),metrics

    def trading(self,legacy):
        if self.user_token is None:
            from refresh_sourcing_listing_availability_trading_fallback import get_access_token
            self.user_token=get_access_token()
        fields=f'<ItemID>{legacy}</ItemID><DetailLevel>ReturnAll</DetailLevel><IncludeItemSpecifics>true</IncludeItemSpecifics>'
        fields+=''.join(f'<OutputSelector>{s}</OutputSelector>' for s in SELECTORS)
        return normalize_item(call(self.user_token,'GetItem',fields),self.settings)

    @staticmethod
    def terminal(payload):
        from refresh_sourcing_listing_availability import listing_is_available
        return bool((payload.get('mbopEvidence') or {}).get('ended')) or not listing_is_available(payload)[0]

    @staticmethod
    def missing(payload,required):
        from ebay_availability import quantity_evidence
        if payload.get('itemGroupHref') and (str(payload.get('itemId','')).endswith('|0') or (payload.get('mbopEvidence') or {}).get('variationUnverified')):
            return ['exact_variation']
        missing=[]
        paths={'conditionId':payload.get('conditionId'),'seller':(payload.get('seller') or {}).get('username'),
               'country':(payload.get('itemLocation') or {}).get('country'),'price':(payload.get('price') or {}).get('value'),
               'availability':quantity_evidence(payload)[0]}
        for key,value in paths.items():
            if value is None or value=='':missing.append(key)
        if (payload.get('price') or {}).get('currency')!='USD':missing.append('currency')
        if not payload.get('buyingOptions'):missing.append('buying_options')
        availability=next(iter(payload.get('estimatedAvailabilities') or [{}]))
        if availability.get('estimatedAvailabilityStatus')=='UNKNOWN':missing.append('availability_status')
        aspects={a.get('name','').lower():a.get('value') for a in payload.get('localizedAspects') or []}
        for key in required:
            if key.startswith('localizedAspects.') and not aspects.get(key.split('.',1)[1].lower()):missing.append(key)
        return missing

    def shipping_verified(self, payload):
        from decimal import Decimal, InvalidOperation
        country,zipcode,_ = buyer(self.settings)
        for option in payload.get('shippingOptions') or []:
            cost = option.get('shippingCost') or {}
            if cost.get('value') is None:
                continue
            try:
                amount = Decimal(str(cost['value']))
            except (InvalidOperation,ValueError):
                return False
            destination = option.get('shipToLocationUsedForEstimate') or {}
            return (cost.get('currency') == 'USD' and amount.is_finite() and amount >= 0
                    and (not destination.get('country') or destination['country'] == country)
                    and (not destination.get('postalCode') or str(destination['postalCode']) == str(zipcode)))
        return False

    def get(self,item_id,*,summary=None,required=(),viable=None,shipping=True):
        from ebay_sourcing_search import EbayRateLimitedError, EbayTransientError
        if str(item_id).isdigit():item_id=f'v1|{item_id}|0'
        match=re.fullmatch(r'v1\|(\d+)\|(\d+)',str(item_id))
        if not match:raise EvidenceUnavailable('Invalid eBay listing ID')
        key=self.key(item_id);memory_key=json.dumps(key,sort_keys=True)
        metrics={};entry=self.cache.get(memory_key)
        cached=entry[1] if entry and time.monotonic()-entry[0]<max(30,min(int(os.getenv('MBOP_EBAY_EVIDENCE_TTL_SECONDS','900')),900)) else None
        if cached is None and self.gate:
            response=self.gate.cached(key)
            if response is not None:cached=response.json()
        if cached and (cached.get('mbopEvidence') or {}).get('provider')=='trading' and cached['mbopEvidence'].get('schemaVersion')!=1:cached=None
        # Fresh contradictory search evidence invalidates the full cached observation.
        if cached and summary and any(summary.get(k) is not None and summary.get(k)!=cached.get(k) for k in ('title','conditionId','price')):cached=None
        if cached and not cached.get('itemGroupHref') and not self.missing(cached,required) and (not shipping or self.shipping_verified(cached) or self.terminal(cached)):
            self.event('cache_hit');metrics['duplicate_detail_calls_prevented_count']=1
            return copy.deepcopy(cached),metrics
        preferred=[TRADING_RESOURCE,RESOURCE] if self.enabled() and match[2]=='0' else [RESOURCE]
        pauses=[];failures=[]
        for provider in preferred:
            try:
                if self.gate:
                    state=self.gate.reserve(provider,peek=True)
                    expected=2 if provider==TRADING_RESOURCE and shipping and not (cached or summary or {}).get('shippingOptions') else 1
                    if isinstance(state,dict) and state.get('remaining',expected)-state.get('protected',0)<expected:
                        raise EbayQuotaPaused('Insufficient headroom for detail and shipping',state.get('reset'),provider)
                if provider==TRADING_RESOURCE:
                    if cached and (cached.get('mbopEvidence') or {}).get('provider')=='trading':
                        payload=copy.deepcopy(cached);self.event('cache_hit',provider)
                    else:
                        payload=self.trading(match[1]);metrics['trading_get_item_count']=metrics.get('trading_get_item_count',0)+1
                else:
                    payload,calls=self.browse(item_id)
                    for k,v in calls.items():metrics[k]=metrics.get(k,0)+v
                if payload.get('itemId')!=item_id or not payload.get('title'):
                    raise EvidenceUnavailable('Provider returned mismatched or missing listing identity')
                # Never apply identity/economic screening to an unverified parent
                # variation or treat a foreign currency as US dollars.
                if payload.get('itemGroupHref') and match[2]=='0' and not (
                    (payload.get('mbopEvidence') or {}).get('listingStatus') in ('Completed','Ended')):
                    if provider==TRADING_RESOURCE:
                        self.event('fallback_missing_exact_variation',provider)
                        failures.append('Trading variation requires Browse verification')
                        continue
                    raise EvidenceUnavailable('Exact purchasable variation requires review')
                if (payload.get('price') or {}).get('currency')!='USD' and not self.terminal(payload):
                    if provider==TRADING_RESOURCE:
                        self.event('fallback_missing_currency',provider)
                        failures.append('Trading currency requires Browse verification')
                        continue
                    raise EvidenceUnavailable('US pricing currency remains unverified')
                if self.terminal(payload):
                    self.cache[memory_key]=(time.monotonic(),payload)
                    return payload,metrics
                # Never inherit a summary's stale commercial values over Trading unknowns.
                reject=viable is not None and not viable(payload)
                if provider==TRADING_RESOURCE:self.cache[memory_key]=(time.monotonic(),copy.deepcopy(payload))
                if reject:
                    self.event('preliminary_exclusion',provider)
                    return payload,metrics
                missing=self.missing(payload,required)
                if provider==TRADING_RESOURCE and not missing and shipping and not self.shipping_verified(payload):
                    if 'Calculated' in (payload.get('mbopEvidence') or {}).get('shippingType',''):
                        country,zipcode,quantity=buyer(self.settings)
                        if zipcode:
                            fields=f'<ItemID>{match[1]}</ItemID><DestinationCountryCode>{escape(country)}</DestinationCountryCode><DestinationPostalCode>{escape(zipcode)}</DestinationPostalCode><QuantitySold>{quantity}</QuantitySold>'
                            quote=call(self.user_token,'GetItemShipping',fields)
                            metrics['trading_get_shipping_count']=metrics.get('trading_get_shipping_count',0)+1
                            payload['shippingOptions']=shipping_options(quote,self.settings,quoted=True)
                    if not self.shipping_verified(payload):missing.append('buyer_shipping')
                if missing and provider==TRADING_RESOURCE:
                    self.event('fallback_missing_'+missing[0],provider)
                    failures.append('Trading incomplete: '+','.join(missing))
                    continue
                if shipping and not self.shipping_verified(payload):
                    missing.append('buyer_shipping')
                if payload.get('itemGroupHref') and match[2]=='0':
                    raise EvidenceUnavailable('Exact purchasable variation requires review')
                if missing:raise EvidenceUnavailable('Required evidence remains unknown: '+','.join(missing))
                self.cache[memory_key]=(time.monotonic(),copy.deepcopy(payload))
                if self.gate:
                    response=requests.Response();response.status_code=200;response._content=json.dumps(payload).encode()
                    self.gate.save(key,response)
                return payload,metrics
            except (EbayQuotaPaused,EbayRateLimitedError) as error:
                pauses.append(error);self.event('fallback_capacity',provider)
            except (TradingError,requests.RequestException,EbayTransientError,EvidenceUnavailable) as error:
                failures.append(str(error));self.event('fallback_provider_failure',provider)
        if pauses:
            error=self.pause(pauses)
            self.event('awaiting_capacity',error.resource)
            raise EbayRateLimitedError('Listing evidence pending: '+'; '.join(failures+[str(error)]),metrics,
                                       retry_at=error.retry_at,resource=error.resource)
        raise EvidenceUnavailable('; '.join(failures) or 'Required listing evidence unavailable')


_routers={}


def router_for(token,settings):
    key=(token,buyer(settings))
    if key not in _routers:
        if len(_routers)>4:_routers.clear()
        _routers[key]=ListingRouter(token,settings)
    return _routers[key]
