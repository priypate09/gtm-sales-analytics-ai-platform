{{ config(materialized="table") }}

select
    order_date,
    segment,
    product,
    region,
    subregion,
    sum(cast(sales as double))        as total_sales,
    sum(cast(profit as double))       as total_profit,
    count(*)                          as order_count,
    avg(cast(sales as double))        as avg_deal_size
from {{ ref("stg_sales") }}
group by 1, 2, 3, 4, 5