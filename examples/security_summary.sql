SELECT symbol, source, count(*) AS observations,
       avg(simple_return) AS avg_daily_price_return,
       stddev_samp(simple_return) AS daily_price_return_volatility,
       avg(volume) AS avg_daily_volume,
       avg(dollar_volume) AS avg_daily_dollar_volume
FROM prices
WHERE date >= DATE '2025-01-01'
GROUP BY symbol, source
ORDER BY avg_daily_price_return DESC, symbol, source;
