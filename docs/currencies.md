# Supported currencies

The bot supports 156 current non-fund codes with zero, two, or three decimal places.
The explicit, immutable registry is `src/splitnshare/domain/currencies.py`.
Run `/currencies` in Telegram to see every accepted code grouped by decimal precision.
This command also works during amount entry without clearing the draft.

The source is the ISO 4217 Maintenance Agency, SIX:
[List One XML](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml),
published 2026-01-01 and retrieved 2026-09-08.
Downloaded XML SHA-256: `838dfb991648cf36df939edd5fe3811737962b75a32252847d239cedd1e291c9`.

Selection: retain entries with a currency code and minor-unit value of 0, 2, or 3,
excluding entries whose `CcyNm` has `IsFund="true"`; deduplicate by code.
Historical codes, fund codes, four-decimal accounting units, and entries with an
undefined (`N.A.`) minor unit are unsupported. This excludes BGN, CLF, UYW, XAU,
XTS, and XXX, as well as cryptocurrencies and invented codes such as BTC and ZZZ.
No runtime network request or exchange-rate conversion is performed.

## Input and amounts

All entry points share the same registry: the environment's `DEFAULT_CURRENCY`,
user settings, `Money` construction, expense totals, exact shares, and settlements.
ASCII lowercase codes and surrounding whitespace are normalized. Unknown codes are
rejected with a pointer to `/currencies`. There is no default precision for unknown codes.

Examples:

| Code | Precision | Input | Stored minor units |
| --- | --- | --- | --- |
| KRW | 0 | 123 | 123 |
| EUR | 2 | 12.34 | 1234 |
| TND | 3 | 1.234 | 1234 |

Nonzero digits beyond the allowed precision are rejected, never rounded. Trailing
zeros are accepted. Precision means ISO accounting minor units, not a country's
cash-rounding increment. Equal splits continue to distribute integer remainders.

## Upgrading an existing database

Stop the old bot process, take a database backup, and run `python -m alembic upgrade head`
before starting the new version. Do not run old and new versions against the database
at the same time. The bot restart also discards drafts using the old precision.

Revision `20260908_0010` checks existing currency codes, including user defaults,
soft-deleted expenses, debts, and settlements. Unsupported codes stop the upgrade;
the operator must investigate and explicitly correct or otherwise resolve those
records. The migration never substitutes a currency or discards history.

Previously, currencies missing from the small exception table used two decimals.
For affected zero-decimal currencies, the migration divides stored totals, every
share, debts, and settlements by 100. For LYD and TND, it multiplies them by 10.
For example, a legacy KRW amount of 12300 (displayed as 123.00 KRW) becomes 123
(displayed as 123 KRW). The monetary value stays the same.

Every amount is validated before any amount changes. A fractional legacy share
such as 50 old KRW minor units cannot be represented in whole won; the upgrade
stops for review instead of rounding it. Potential integer overflow also stops
the upgrade. Other currencies and record timestamps are unchanged.

Downgrading restores the old scales only if every amount remains representable
without rounding or overflow. Newly recorded three-decimal amounts may prevent
a downgrade; stop the bot and review the reported data instead of forcing it.

## Maintaining the list

Check SIX's current List One and amendment notices when updating the registry.
Review additions, withdrawals, and exponent changes explicitly. Record the source
publication/retrieval dates and hash. Recheck preset buttons and currency tests.
Any removal or exponent change needs an explicit plan for existing data; never
replace the registry automatically on startup. The migration's code list is frozen
independently of the live registry so later changes cannot rewrite migration history.
