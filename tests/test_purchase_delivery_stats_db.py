"""Execute the actual aggregate in disposable networking-disabled PostgreSQL."""
import json
from pathlib import Path
import subprocess
import time

def main():
    name = 'mbop-purchase-stats-regression'
    subprocess.run(['docker','run','--rm','-d','--name',name,'--network','none','-e','POSTGRES_PASSWORD=local-test-only','postgres:17-alpine'],check=True,capture_output=True)
    def sql(value):
        return subprocess.run(['docker','exec','-i',name,'psql','-U','postgres','-qAt','-v','ON_ERROR_STOP=1'],input=value,text=True,encoding='utf-8',check=True,capture_output=True).stdout.strip()
    try:
        for _ in range(40):
            if subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True).returncode==0:break
            time.sleep(.25)
        sql('create role anon; create role authenticated; create role service_role; create table purchase_items(item_id int primary key,exclude_from_purchase_reporting boolean); create table source(item_id int,current_status text,quantity numeric,unit_cost numeric); create view vw_purchases_dashboard as select * from source; grant select on purchase_items,vw_purchases_dashboard to service_role;')
        sql(Path('supabase/migrations/20260915145955_mbop_purchase_delivery_stats.sql').read_text(encoding='utf-8'))
        empty=json.loads(sql('set role service_role; select purchase_delivery_stats();'))
        assert empty['notDelivered']['units']==empty['deliveredNotReceived']['units']==0
        statuses=['no_tracking','shipped_no_tracking','awaiting_carrier_scan','in_transit','partially_delivered','multi_package_in_transit','available_for_pickup','out_for_delivery','exception','delivered','received','listed','cancelled','return_opened','return_pending']
        for i,status in enumerate(statuses,1):
            sql(f"insert into purchase_items values({i},false); insert into source values({i},'{status}',3,12.34);")
        sql("insert into source select * from source where item_id=1; insert into purchase_items values(30,true),(31,null); insert into source values(30,'delivered',100,999),(31,'delivered',2,null);")
        result=json.loads(sql('set role service_role; select purchase_delivery_stats();'))
        assert result=={'notDelivered':{'units':27,'purchaseDollars':333.18,'unpricedUnits':0},'deliveredNotReceived':{'units':5,'purchaseDollars':37.02,'unpricedUnits':2}},result
        assert sql("select has_function_privilege('anon','purchase_delivery_stats()','execute') or has_function_privilege('authenticated','purchase_delivery_stats()','execute');")=='f'
        print('PASS: all inbound statuses; received/listed/cancelled/returns excluded; deduplication; quantity x authoritative cost; reporting exclusion; null cost; empty groups; service-only permissions')
    finally:
        subprocess.run(['docker','stop',name],check=True,capture_output=True)

if __name__=='__main__':main()
