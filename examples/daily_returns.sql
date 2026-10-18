-- SYNTHETIC demo prices are unadjusted price returns, not total shareholder returns.
SELECT symbol, source, date, close, simple_return, log_return
FROM prices
WHERE date BETWEEN DATE '2025-01-01' AND DATE '2025-01-31'
ORDER BY symbol, source, date;
