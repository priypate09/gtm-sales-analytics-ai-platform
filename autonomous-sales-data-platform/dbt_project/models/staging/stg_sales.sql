{{ config(materialized="view") }}

select
    "Order Date"::date              as order_date,
    "Segment"                       as segment,
    "Product"                       as product,
    "Region"                        as region,
    "Subregion"                     as subregion,
    cast("Sales" as double)         as sales,
    cast("Profit" as double)        as profit,
    cast("Quantity" as integer)     as quantity
from {{ source("saas", "raw_sales") }}