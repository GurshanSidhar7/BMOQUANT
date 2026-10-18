-- Full trailing 20/30 observed log returns; sample std, sqrt(252) annualization.
-- Analytics were computed before the date filter, preserving prior history.
SELECT symbol, source, date, realized_vol_20, realized_vol_30, average_volume_20
FROM prices
WHERE date >= DATE '2025-01-01'
ORDER BY symbol, source, date;
