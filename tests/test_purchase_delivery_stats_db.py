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
        sql('create role anon; create role authenticated; create role service_role; create table purchases(purchase_id int primary key,raw_import_json jsonb); create table purchase_items(item_id int primary key,purchase_id int,exclude_from_purchase_reporting boolean,expected_delivery date); create table source(item_id int,purchase_id int,current_status text,quantity numeric,unit_cost numeric,estimated_delivery_date timestamptz); create view vw_purchases_dashboard as select * from source; grant select on purchases,purchase_items,vw_purchases_dashboard to service_role;')
        sql(Path('supabase/migrations/20260915145955_mbop_purchase_delivery_stats.sql').read_text(encoding='utf-8'))
        sql(Path('supabase/migrations/20260918235202_mbop_purchase_saturday_delivery_stats.sql').read_text(encoding='utf-8'))
        sql(Path('supabase/migrations/20260922144931_mbop_purchase_daily_delivery_stats.sql').read_text(encoding='utf-8'))
        empty=json.loads(sql('set role service_role; select purchase_delivery_stats();'))
        assert empty['notDelivered']['units']==empty['deliveredNotReceived']['units']==0
        statuses=['no_tracking','shipped_no_tracking','awaiting_carrier_scan','in_transit','partially_delivered','multi_package_in_transit','available_for_pickup','out_for_delivery','exception','delivered','received','listed','cancelled','return_opened','return_pending']
        for i,status in enumerate(statuses,1):
            sql(f"insert into purchases values({i},'{{}}'); insert into purchase_items values({i},{i},false,null); insert into source values({i},{i},'{status}',3,12.34,null);")
        sql("insert into source select * from source where item_id=1; insert into purchases values(30,'{}'),(31,'{}'); insert into purchase_items values(30,30,true,null),(31,31,null,null); insert into source values(30,30,'delivered',100,999,null),(31,31,'delivered',2,null,null);")
        result=json.loads(sql('set role service_role; select purchase_delivery_stats();'))
        assert result=={'notDelivered':{'units':27,'purchaseDollars':333.18,'unpricedUnits':0},'deliveredNotReceived':{'units':5,'purchaseDollars':37.02,'unpricedUnits':2}},result
        # Friday keeps the next day; Sunday rolls to the following Saturday.
        sql("insert into purchases values(40,'{}'),(41,'{\"Order\":{\"EstimatedDeliveryTimeMax\":\"2026-09-26T23:59:59Z\"}}'),(42,'{}'),(43,'{}'); insert into purchase_items values(40,40,false,null),(41,41,false,null),(42,42,false,'2026-09-27'),(43,43,false,null); insert into source values(40,40,'in_transit',2,10,'2026-09-19T23:00Z'),(41,41,'shipped_no_tracking',3,5,null),(42,42,'in_transit',4,2,null),(43,43,'in_transit',9,1,null);")
        friday=json.loads(sql("set role service_role; select purchase_saturday_delivery_stats('2026-09-18');"))
        sunday=json.loads(sql("set role service_role; select purchase_saturday_delivery_stats('2026-09-20');"))
        assert friday=={'throughDate':'2026-09-19','units':2,'purchaseDollars':20.00,'unpricedUnits':0},friday
        assert sunday=={'throughDate':'2026-09-26','units':5,'purchaseDollars':35.00,'unpricedUnits':0},sunday
        daily=json.loads(sql("set role service_role; select purchase_daily_delivery_stats('2026-09-18',7);"))
        assert daily['startDate']=='2026-09-18'
        assert [day['dueDate'] for day in daily['days']]==[f'2026-09-{day:02d}' for day in range(18,25)]
        assert daily['days'][0]=={'dueDate':'2026-09-18','units':0,'purchaseDollars':0,'unpricedUnits':0},daily
        assert daily['days'][1]=={'dueDate':'2026-09-19','units':2,'purchaseDollars':20.00,'unpricedUnits':0},daily
        assert sum(day['units'] for day in daily['days'])==2,daily
        assert sql("select has_function_privilege('anon','purchase_saturday_delivery_stats(date)','execute') or has_function_privilege('authenticated','purchase_saturday_delivery_stats(date)','execute');")== 'f'
        assert sql("select has_function_privilege('anon','purchase_delivery_stats()','execute') or has_function_privilege('authenticated','purchase_delivery_stats()','execute');")=='f'
        assert sql("select has_function_privilege('anon','purchase_daily_delivery_stats(date,integer)','execute') or has_function_privilege('authenticated','purchase_daily_delivery_stats(date,integer)','execute');")=='f'
        print('PASS: all inbound statuses; received/listed/cancelled/returns excluded; deduplication; quantity x authoritative cost; reporting exclusion; null cost; empty groups; service-only permissions')
    finally:
        subprocess.run(['docker','stop',name],check=True,capture_output=True)

if __name__=='__main__':main()
