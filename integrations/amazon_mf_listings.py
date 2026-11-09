"""Complete bounded Listings discovery beyond Amazon's 1,000-result page cap."""
import time
from datetime import datetime, timezone
from urllib.parse import quote


def discover_listings(client, seller, market, through, *, max_items=5000, max_calls=350):
    path='/listings/2021-08-01/items/'+quote(seller,safe='')
    base={'marketplaceIds':market,'includedData':'summaries,attributes,fulfillmentAvailability,issues',
          'pageSize':'20','sortBy':'createdDate','sortOrder':'ASC'}
    calls=0
    result={}

    def fetch(params):
        nonlocal calls
        if calls>=max_calls:raise ValueError('MF listing call budget exhausted; coverage incomplete')
        if calls:time.sleep(.3)
        calls+=1
        response=client.request('GET',path,params=params)
        if not isinstance(response.get('items'),list) or not isinstance(response.get('numberOfResults'),int):
            raise ValueError('Amazon listing result/count missing; coverage incomplete')
        return response

    def collect(lower,upper,depth=0):
        params={**base,'createdBefore':upper.isoformat()}
        if lower:params['createdAfter']=lower.isoformat()
        response=fetch(params)
        expected=response['numberOfResults']
        if expected>900:
            if depth>=30:raise ValueError('Listing date partition cannot fit Amazon search cap')
            if lower is None:
                stamps=[s.get('createdDate') for item in response['items'] for s in item.get('summaries',[]) if s.get('marketplaceId')==market and s.get('createdDate')]
                if not stamps:raise ValueError('Cannot partition listings without source creation dates')
                lower=min(datetime.fromisoformat(x.replace('Z','+00:00')) for x in stamps)
            middle=lower+(upper-lower)/2
            if (upper-lower).total_seconds()<.002:raise ValueError('More than 900 listings share a creation timestamp; coverage needs reconciliation')
            # Both date boundaries are inclusive: overlap and deduplicate by exact seller SKU.
            collect(lower,middle,depth+1);collect(middle,upper,depth+1)
            return
        seen_tokens=set();partition=set()
        while True:
            for item in response['items']:
                sku=item.get('sku')
                if not sku:raise ValueError('Listing SKU missing')
                partition.add(sku)
                previous=result.get(sku)
                if previous is None or str(item.get('summaries',[]))==str(previous.get('summaries',[])):
                    result[sku]=item
                else:
                    current_stamp=max((s.get('lastUpdatedDate','') for s in item.get('summaries',[]) if s.get('marketplaceId')==market),default='')
                    previous_stamp=max((s.get('lastUpdatedDate','') for s in previous.get('summaries',[]) if s.get('marketplaceId')==market),default='')
                    if current_stamp>=previous_stamp:result[sku]=item
                if len(result)>max_items:raise ValueError('MF listing item budget exhausted; coverage incomplete')
            token=(response.get('pagination') or {}).get('nextToken')
            if not token:break
            if token in seen_tokens:raise ValueError('Repeated listing pagination token; coverage incomplete')
            seen_tokens.add(token)
            response=fetch({**params,'pageToken':token})
        if len(partition)<expected:raise ValueError('Amazon listings ended before reported result count; coverage incomplete')

    collect(None,datetime.fromisoformat(through.replace('Z','+00:00')).astimezone(timezone.utc))
    return list(result.values()),calls
