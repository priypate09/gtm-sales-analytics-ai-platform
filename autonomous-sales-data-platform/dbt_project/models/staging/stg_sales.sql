{{ config(materialized="view") }}

select * from {{ source("saas", "raw_sales") }}
