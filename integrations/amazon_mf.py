"""Non-PII MF operational projections from current Amazon Orders/Listings APIs."""
from datetime import datetime, timezone

ACTIVE = {'PendingAvailability','Pending','Unshipped','PartiallyShipped'}
STATUSES = {'PENDING_AVAILABILITY':'PendingAvailability','PENDING':'Pending','UNSHIPPED':'Unshipped','PARTIALLY_SHIPPED':'PartiallyShipped','SHIPPED':'Shipped','CANCELLED':'Canceled','UNFULFILLABLE':'Unfulfillable'}

def condition(value, subtype=None):
    value=(value or 'unknown').lower()
    if value in {'new_new','newitem'}: value='new'
    value={'used_like_new':'used_mint','used_very_good':'used_verygood','collectible_like_new':'collectible_mint','collectible_very_good':'collectible_verygood'}.get(value,value)
    if value in {'used','collectible','refurbished'} and subtype:
        return value+'_'+subtype.lower().replace('_','')
    return value

def quantity(value):
    if isinstance(value,bool) or not isinstance(value,int) or value<0: raise ValueError('Amazon omitted/returned an invalid fulfillment quantity')
    return value

def iso(value):
    if not value: raise ValueError('Amazon source timestamp missing')
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()

def order_items(order, marketplace):
    if (order.get('salesChannel') or {}).get('marketplaceId') != marketplace: raise ValueError('Amazon order marketplace mismatch')
    if (order.get('fulfillment') or {}).get('fulfilledBy') != 'MERCHANT': return []
    status=STATUSES.get((order.get('fulfillment') or {}).get('fulfillmentStatus'))
    if not status: raise ValueError('Unrecognized Amazon fulfillment status')
    items=order.get('orderItems')
    if not isinstance(items,list): raise ValueError('Amazon omitted orderItems')
    result=[]
    for item in items:
        product=item.get('product') or {}; cond=product.get('condition') or {}; fulfill=item.get('fulfillment') or {}
        ordered=quantity(item.get('quantityOrdered')); shipped=quantity(fulfill.get('quantityFulfilled'))
        unfulfilled=quantity(fulfill.get('quantityUnfulfilled')) if status in ACTIVE else 0
        if not order.get('orderId') or not item.get('orderItemId'): raise ValueError('Amazon order/item identity missing')
        result.append({'amazon_order_id':order['orderId'],'amazon_order_item_id':item['orderItemId'],'marketplace_id':marketplace,'fulfillment_channel':'MFN',
            'seller_sku':product.get('sellerSku'),'asin':product.get('asin'),'title':product.get('title'),
            'condition':condition(cond.get('conditionType'),cond.get('conditionSubtype')),'status':status,'ordered':ordered,'shipped':shipped,'unfulfilled':unfulfilled,
            'source_updated_at':iso(order.get('lastUpdatedTime')),'purchased_at':iso(order.get('createdTime')),
            'replacement_for':[{'order_id':a.get('orderId'),'type':a.get('associationType')} for a in order.get('associatedOrders',[]) if a.get('associationType') in {'REPLACEMENT_ORIGINAL_ID','EXCHANGE_ORIGINAL_ID'}]})
    return result

def offer(item,marketplace,observed,run):
    summaries=[x for x in item.get('summaries',[]) if x.get('marketplaceId')==marketplace]
    if len(summaries)!=1: raise ValueError('Listings summary marketplace is missing or ambiguous')
    summary=summaries[0]
    availability=item.get('fulfillmentAvailability') or []
    mf=[x for x in availability if x.get('fulfillmentChannelCode')=='DEFAULT']
    attributes=item.get('attributes') or {}
    submitted=[x for x in attributes.get('fulfillment_availability',[]) if x.get('fulfillment_channel_code')=='DEFAULT']
    if not mf and not submitted: return None # Never classify FBA as MF from a title/quantity guess.
    if len(mf)>1: raise ValueError('Multi-source MF availability requires reconciliation')
    brand=next((x.get('value') for x in attributes.get('brand',[]) if x.get('marketplace_id',marketplace)==marketplace),None)
    return {'seller_sku':item['sku'],'asin':summary.get('asin'),'title':summary.get('itemName'),
        'condition':condition(summary.get('conditionType')),'quantity':quantity(mf[0]['quantity']) if mf and 'quantity' in mf[0] else None,
        'source_updated_at':summary.get('lastUpdatedDate'),'observed_at':observed,'status':summary.get('status',[]),'brand':brand,'run_id':run}
