{{ config(materialized="table") }}

select
    segment                               as segment,
    count(*)                              as total_orders,
    sum(cast(sales as double))            as total_sales,
    sum(cast(profit as double))           as total_profit,
    avg(cast(sales as double))            as avg_deal_size,
    sum(cast(profit as double)) /
        nullif(sum(cast(sales as double)), 0) as profit_margin
from {{ ref("stg_sales") }}
group by 1