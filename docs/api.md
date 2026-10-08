# CheckWatt / EnergyInBalance API Documentation

Base URL: `https://api.checkwatt.se`  
Web app: `https://energyinbalance.se`

> Reverse-engineered from browser traffic. Not an official API. Subject to change without notice.
>
> Last verified against a HAR export of the EnergyInBalance dashboard on **2026-10-08** (previously 2026-09-01). Changes found in that export are marked *2026-10*.
>
> All examples come from a **single site** (Goodwe inverter, SE4, enrolled in mFRR and FCR-D). Not all sites use the same grid services — a site may run FCR-D only, mFRR only, FCR-N, or none at all — so service-specific fields will differ: `Portfolios` on `/site/{site_id}`, `Service` on `/site/Statuses`, `ServiceName` in `/revenue/{site_id}`, and the mFRR/FCR fields in `/ems/ActivationSchedule` (`FrequencyPower`, `Schedule` activation types, mFRR SoC limits in `UserSetting`). Consumers must treat these as dynamic — never hardcode a service name or assume a field is populated.

---

## Authentication

### Login (username + password)

```
POST /user/Login?audience=eib
Authorization: Basic {base64(username:password)}
Content-Type: application/json

Body: {"OneTimePassword": ""}
```

**Response 200:**
```json
{
  "LoggedIn": true,
  "User": "user@example.com",
  "JwtToken": "eyJ...",
  "RefreshToken": "00000000-0000-0000-0000-000000000000",
  "RefreshTokenExpires": "2026-09-15T12:27:23.258+00:00",
  "Permissions": ["eib_active_service_status", "site_measurements_charts", "site_measurements_monetary"],
  "Role": null,
  "IsAdmin": false,
  "AdditionalProperties": null,
  "ClientId": null,
  "CesarId": null,
  "ResellerId": null,
  "Elhandelsbolag": null,
  "Koncern": null,
  "Country": ""
}
```

- ⚠️ **Changed 2026-09:** the `JwtTokenExpires` field has been removed from the response. Read the JWT expiry from the token's own `exp` claim instead.
- ⚠️ **Changed 2026-09:** `JwtToken` is now valid for only **~15 minutes** (was ~2.25 hours). Rely on the `exp` claim, not a hardcoded lifetime.
- `RefreshToken` is now valid for **14 days** (was 7).
- New (null for regular users): `AdditionalProperties`, `ClientId`, `CesarId`. New permission string `eib_active_service_status`.

**Errors:** `401 Unauthorized` on wrong credentials.

---

### Refresh JWT (preferred, avoids re-login)

```
GET /user/RefreshToken?audience=eib
Authorization: Bearer {refresh_token}
```

**Response 200:** Same structure as Login response, with a new `JwtToken` and the same `RefreshToken`.

> Use this endpoint when the JWT is close to expiry. Only fall back to full login if the refresh token is also expired.

---

### Authenticated requests

All subsequent API calls require:
```
Authorization: Bearer {jwt_token}
```

---

## Site & Device Discovery

### Get customer details

```
GET /controlpanel/CustomerDetail
Authorization: Bearer {jwt_token}
```

Returns customer info and all associated meters. The key meter types found in the `Meter` array are:

| `InstallationType` | Description |
|---|---|
| `SoC` | Battery state-of-charge meter (primary meter, carries `RpiSerial`) |
| `Charging` | Battery charging meter |
| `Discharging` | Battery discharging meter |
| `Solar` | Solar panel meter |
| `EDIEL_E17` | Grid import meter |
| `EDIEL_E18` | Grid export meter |

The `SoC` meter carries `RpiSerial` (the CM10 device serial), `RpiModel`, and a `Comments`/`Logbook` field with operational history.

Fields seen 2026-10 that were not documented before (they may be older): `InvoiceDetail` (null) at the top level, and on every meter `BatteryCapacityKwh` (set on the `SoC` meter, e.g. `13.1`; null elsewhere), `HasBattery`, `BatteryConf`, `MeterSolarAngles` (array), `MeterConnectedToMeter` (array), `RpiSystem`, `TimeZone`, `DisplayName` and `DatastreamId` (e.g. `aabbccddeeff_SoC`, `aabbccddeeff_energyImport`). `HasBattery` is `false` even on a site with a battery, so do not rely on it.

**Response excerpt:**
```json
{
  "Id": 10001,
  "FirstName": "...",
  "LastName": "...",
  "Meter": [
    {
      "Id": 100001,
      "InstallationType": "SoC",
      "RpiSerial": "aabbccddeeff",
      "RpiModel": "CM4-X500-MINI",
      "FacilityId": "730000000000000000",
      "NetAreaId": "RSJ",
      "StandBy": 0.03
    }
  ]
}
```

---

### Get site ID from serial

```
GET /Site/SiteIdBySerial?serial={rpi_serial}
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{"SiteId": 12345}
```

> Cache this – the site ID is stable and used in most subsequent requests.

---

### Get site details

```
GET /site/{site_id}
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "Id": 12345,
  "Country": "SE",
  "TimeZone": "Europe/Stockholm",
  "Currency": "SEK",
  "InverterModel": {
    "Brand": "Goodwe",
    "Model": "GW10K-ET",
    "PowerWatt": 10000
  },
  "Dso": {
    "Id": 72,
    "DisplayName": "Example Nät AB"
  },
  "ShouldHaveGeneratedEmsSchedule": true,
  "MainFuseSize": 20,
  "UnmeteredSolarWatt": 0,
  "TariffId": 3618,
  "NextTariffId": null,
  "NextTariffEffectiveFrom": null,
  "Portfolios": [
    {"DisplayName": "xx:se4:u", "ServiceId": "fcrdup"},
    {"DisplayName": "xx:se4:d", "ServiceId": "fcrddown"},
    {"DisplayName": "Example mFRR Up CM SE4", "ServiceId": "mfrrup"}
  ],
  "Reseller": {
    "Id": 338,
    "DisplayName": "Example Servicepartner AB",
    "PartnerType": "servicepartner",
    "Url": null,
    "SiteSupport": null
  },
  "GeneratedEmsSchedule": true
}
```

`Portfolios` lists the active grid services the site participates in (FCR-D up/down, mFRR, etc.).

New fields 2026-09: `ShouldHaveGeneratedEmsSchedule`, `NextTariffId`, `NextTariffEffectiveFrom` (upcoming tariff change, null when none), `Reseller.Url`, `Reseller.SiteSupport`.

New field 2026-10: `UnmeteredSolarWatt` (W; presumably solar capacity not measured by CheckWatt).

---

### Get site statuses (rich device status)

```
GET /site/Statuses?serial={rpi_serial}
Authorization: Bearer {jwt_token}
```

Preferred over the old `/register/checkrpiv2` and `/asset/status` endpoints.

**Response 200** (array):
```json
[
  {
    "SiteId": 12345,
    "MeterId": 100001,
    "ClientId": 10001,
    "RpiSerial": "aabbccddeeff",
    "DisplayName": "Example Site Name",
    "Mba": "SE4",
    "Email": "user@example.com",
    "StreetAddress": "Example Street 1",
    "Version": "2.3.104.83",
    "SvkVersion": "6.0",
    "Inverter": "goodwe",
    "OperationPreference": "co",
    "FpUpInKw": 2.88,
    "FpDownInKw": 7.871,
    "LastSeenCm10": "2026-06-08T14:24:07Z",
    "LastSeenInverter": "2026-06-08T14:53:32Z",
    "OperationDate": null,
    "Reseller": {"DisplayName": "...", "Id": 338},
    "Retailer": {"DisplayName": "Example Retailer AB", "Id": 90},
    "RelatedMeters": [
      {"Type": "Charging", "PeakAcKw": 10.0},
      {"Type": "Discharging", "PeakAcKw": 10.0}
    ],
    "TestInfo": {
      "Latest": "Deactivated",
      "Result": null,
      "FailedInARow": 0
    },
    "CompatibleRetailer": true,
    "Service": ["mfrrup", "mfrrdown"]
  }
]
```

New fields 2026-09: `ClientId`, `RpiSerial`, `Email`, `StreetAddress`. `Service` is now populated with the active service IDs (e.g. `"mfrrup"`, `"mfrrdown"`, matching `ServiceId` in site `Portfolios`).

Key fields for HA integration:
- `Version` – CM10 firmware version (`.83` suffix = device under test; e.g. `2.3.106` otherwise)
- `LastSeenCm10` – last contact from CM10 device
- `LastSeenInverter` – last data from inverter
- `FpUpInKw` / `FpDownInKw` – contracted FCR-D power up/down
- `OperationPreference` – `"co"` = Currently Optimized, `"sc"` = Self Consumption
- `TestInfo.Latest` – activation test result (`"Activated"`, `"Deactivated"`, …)
- `TestInfo.Result` – *2026-10:* now populated for an activated site with three percentages, e.g. `"(100.2 % / 0.3 % / 99.2 %)"` — the same figures as in the logbook's `ACTIVATED` lines

---

### Get operation preference

```
GET /site/{site_id}/operation-preference
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{"SiteId": 12345, "PreferenceId": "co"}
```

`PreferenceId` values: `"co"` (Currently Optimized), `"sc"` (Self Consumption).

---

### Get facilities (meter list, v2)

```
GET /user/FacilitiesV2?installationType=Solar&installationType=Electricity%20consumption&installationType=SoC&installationType=EV%20charging
Authorization: Bearer {jwt_token}
```

**Response 200** (array of facilities):
```json
[
  {
    "MeterId": 100002,
    "DatastreamId": "aabbccddeeff_energyPv",
    "InstallationType": "Solar",
    "Rpi": "aabbccddeeff",
    "Date": "2026-06-08T14:52:00.000+00:00",
    "InfoState": 1,
    "InfoType": 0,
    "PeakDC": 0.0,
    "PeakAC": 0.0,
    "Value": 0.0,
    "HasElcert": 1,
    "HasSold": 1,
    "HasBought": 1,
    "ResellerId": 338,
    "Name": null,
    "IrradianceMeter": null,
    "Units": {
      "WithTime": {"1000000": "MWh", "1000": "kWh", "1": "Wh"},
      "WithoutTime": {"1000000": "MW", "1000": "kW", "1": "W"}
    }
  }
]
```

New fields 2026-09: `Name`, `IrradianceMeter`.

---

## Real-time Energy Flow

### Get current energy flow

```
GET /ems/energyflow
Authorization: Bearer {jwt_token}
```

The primary real-time endpoint. Returns current power values in Watts and battery SoC.

**Response 200:**
```json
{
  "SolarNow": 0.0,
  "SolarPeak": 0.0,
  "SolarDate": "2026-06-08T14:52:00Z",
  "SolarIds": [100002],

  "BatteryNow": 0.0,
  "BatteryPeak": 10000.0,
  "BatteryDate": "2026-06-08T14:52:00Z",
  "BatterySoC": 84.0,
  "BatterySoCDate": "2026-06-08T14:52:00Z",
  "BatteryState": 2000,
  "BatteryStateDate": "0001-01-01T00:00:00Z",
  "BatteryChargeIds": [100003],
  "BatteryDischargeIds": [100004],
  "BatterySocIds": [100001],

  "GridNow": -5760.0,
  "GridPeak": 13800.0,
  "GridDate": "2026-06-08T14:52:00Z",
  "GridBoughtIds": [100005],
  "GridSoldIds": [100006],
  "LoggerGridDatastream": ["aabbccddeeff_energyImport"],
  "LoggerGridAdded": "2026-06-08T14:52:31Z",
  "DisplayName": null
}
```

- All `*Now` values are in **Watts**.
- `GridNow` is negative when exporting to grid.
- `BatterySoC` is in percent (0–100).
- `BatteryState`: `2000` = normal operation (value semantics unclear beyond this).
- `BatteryDate` (new 2026-10) – time of the `BatteryNow` reading.
- The `*Ids` arrays reference meter IDs that can be used in `/datagrouping/series`.

---

### Get current solar reading

> Not observed in the 2026-09 web traffic — the updated web app uses `/SiteMeasurements/{site_id}/Data` with `resolution=Minute` instead. May still work but should be considered deprecated.

```
GET /measurements/SolarNow
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "Id": 100002,
  "Datastream": "aabbccddeeff_energyPv",
  "Status": 0,
  "BestReading": 0.0,
  "LatestReading": 0.0,
  "LatestDateStr": "2026-06-08T14:52:00.000+00:00",
  "LatestDate": "2026-06-08T14:52:00Z",
  "TotalFacilities": 1
}
```

---

## Time-series Measurements

### Site measurements (new, preferred endpoint)

```
GET /SiteMeasurements/{site_id}/Data
  ?resolution=FifteenMinutes
  &from=2026-06-08
  &to=2026-06-09
  &timeZone=Europe/Stockholm
  &dataType=GridToLoad
  &dataType=DirectSolarToHome
  ...
Authorization: Bearer {jwt_token}
```

Flexible endpoint returning data for multiple data types in a single request.

**`resolution` values:**

| Value | Keys in `Data` |
|---|---|
| `Minute` (new 2026-09) | one per minute, local time |
| `FifteenMinutes` | one per 15 minutes, local time |
| `Day` (new 2026-10) | one per day, local midnight (`2026-10-05T00:00:00`) |
| `Month` (new 2026-10) | one per month, local (`2026-10-01T00:00:00`) |
| `Period` (new 2026-10) | **a single total** for the whole `from`–`to` range, keyed by the range start in **UTC** (`2026-10-07T22:00:00Z` for `from=2026-10-08`) |

Days or slots not yet reached are `null`. *2026-10:* the web app now also sends `forceRecalculate=false` on every call; responses look the same without it. It typically requests the same data types twice, once with `FifteenMinutes`/`Day` for the chart and once with `Period` for the headline total.

**Available `dataType` values:**

**Power/state data types (new 2026-09** — the updated web app now uses these for the live/day view instead of `/datagrouping/series` with `delta` grouping**):**

| dataType | Description |
|---|---|
| `SolarProductionPower` | Solar production (W) |
| `BatteryChargePower` | Battery charging (W) |
| `BatteryDischargePower` | Battery discharging (W) |
| `BoughtPower` | Grid import (W) |
| `SoldPower` | Grid export (W) |
| `Soc` | Battery state of charge (%) |

With `resolution=Minute` these return one instantaneous value per minute (in W, or % for `Soc`); the trailing not-yet-reported minute is `null`. `from`/`to` also accept full timestamps (`YYYY-MM-DDTHH:MM:SS`) for windowed polling.

**Energy data types:**

| dataType | Description |
|---|---|
| `GridToLoad` | Grid power consumed by home (W) |
| `DirectSolarToHome` | Solar power used directly in home (W) |
| `SoldSolarPower` | Solar power exported to grid (W) |
| `BatteryChargeFromSolar` | Battery charging from solar (W) |
| `BatteryChargeFromGrid` | Battery charging from grid (W) |
| `BatteryDischargeToLoad` | Battery power to home (W) |
| `BatteryDischargeToGrid` | Battery power exported to grid (W) |
| `DirectSolarToHomeMonetary` | Monetary value of direct solar use (currency/interval) |
| `SoldSolarPowerMonetary` | Monetary value of sold solar (currency/interval) |
| `BatteryChargeFromSolarMonetary` | Monetary value of solar→battery charge |
| `BatteryChargeFromGridMonetary` | Monetary value of grid→battery charge |
| `BatteryDischargeToLoadMonetary` | Monetary value of battery→load |
| `BatteryDischargeToGridMonetary` | Monetary value of battery→grid |

**Savings data types (new 2026-10** — the dashboard's "Local energy savings" card**):**

| dataType | Description |
|---|---|
| `LocalEnergySavingsMonetary` | Net local savings (currency); can be negative |
| `ValueOfBatteryChargeMonetary` | Value of the energy charged into the battery |
| `ValueOfBatteryDischargeMonetary` | Value of the energy discharged from the battery |
| `ValueOfSolarMonetary` | Value of the solar production |

In the observed data `LocalEnergySavingsMonetary` ≈ `ValueOfBatteryDischargeMonetary` − `ValueOfBatteryChargeMonetary` + `ValueOfSolarMonetary` (e.g. 11.05 − 18.24 + 0.05 ≈ −7.19 SEK for a month), so a battery that buys more than it sells back locally shows a negative saving. Requested with `Day`, `Month` and `Period`.

**EV data type (new 2026-10):** `EvChargingPower` (W) is now requested along with the other `Minute` power types; it is `null` for every minute on a site without an EV charger.

**Response 200:**
```json
{
  "Data": {
    "GridToLoad": {
      "2026-06-08T00:00:00": 151,
      "2026-06-08T00:15:00": 130,
      ...
    },
    "DirectSolarToHome": {
      "2026-06-08T00:00:00": 0,
      ...
    }
  },
  "TimeZone": "Europe/Stockholm"
}
```

For the energy data types, values are in **Wh** per 15-minute interval (not W). Timestamps are in the requested `timeZone`, which is echoed back in the response's `TimeZone` field (new 2026-09).

---

### Grid import/export data

```
GET /SiteMeasurements/{site_id}/GridData
  ?resolution=FifteenMinutes
  &from=2026-06-08
  &to=2026-06-09
  &timeZone=Europe/Stockholm
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "Import": {
    "2026-06-08T00:00:00Z": 0.002561,
    "2026-06-08T00:15:00Z": 0.002620,
    ...
  },
  "Export": {
    "2026-06-08T00:00:00Z": 0.0,
    ...
  }
}
```

Values are in **kWh** per 15-minute interval. Timestamps in UTC (note: `Z` suffix unlike the Data endpoint). `resolution=Minute` is accepted but still returns 15-minute buckets.

---

### Data grouping / series (flexible historical)

```
GET /datagrouping/series
  ?grouping={grouping}
  &fromdate={from}
  &todate={to}
  &meterId={id1}
  &meterId={id2}
  ...
Authorization: Bearer {jwt_token}
```

**`grouping` values:**

| Value | Resolution | `fromdate`/`todate` format |
|---|---|---|
| `0` or `hour` | Hourly | `YYYY-MM-DD` |
| `1` or `day` | Daily | `YYYY-MM-DD` |
| `2` or `month` | Monthly | `YYYY-MM` |
| `3` or `year` | Yearly | `YYYY` |
| `delta` | Per-minute | `YYYY-MM-DDTHH:MM:SS` |

**Response 200:**
```json
{
  "DateFrom": "2026-06-08",
  "DateTo": "2026-06-08",
  "Grouping": "hour",
  "Meters": [
    {
      "MeterId": 100001,
      "InstallationType": "SoC",
      "DatastreamId": "aabbccddeeff_SoC",
      "DateFromUTC": "2026-06-07T22:00:00",
      "DateToUTC": "2026-06-08T22:00:00",
      "DateFromLocal": "2026-06-08T00:00:00",
      "DateToLocal": "2026-06-09T00:00:00",
      "Measurements": [
        {"Value": 4902.0, "Date": "2026-06-08T00:00:00"},
        {"Value": 5160.0, "Date": "2026-06-08T01:00:00"}
      ]
    }
  ]
}
```

- For `SoC` meters, values are in **Wh** battery capacity (not percent).
- For energy meters, values are in **Wh**.
- The `delta` grouping was used for the live "today" view (per-minute resolution); as of 2026-09 the web app uses `/SiteMeasurements/{site_id}/Data` with `resolution=Minute` for that instead. The endpoint itself is still in use (the web app fetches all-time yearly totals with `grouping=3`, one request per meter; *2026-10:* with `fromdate` set to 100 years back, e.g. `1926`, instead of a fixed year).

---

## Revenue

### Get revenue for date range

```
GET /revenue/{site_id}?from={YYYY-MM-DD}&to={YYYY-MM-DD}&resolution={day|month}
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "SiteId": 12345,
  "Currency": "SEK",
  "Resolution": "Day",
  "Revenue": [
    {
      "ServiceName": "mFRR CM",
      "Date": "2026-06-08",
      "NetRevenue": 84.48,
      "Estimate": true
    }
  ]
}
```

- `ServiceName` reflects the actual grid service (e.g. `"mFRR CM"`, `"FCR-D"`) – do not hardcode. A day can have **several entries**, one per service.
- *2026-10:* a new service name **`"mFRR EAM"`** (mFRR energy activation market) appears on days the battery was actually activated for mFRR, next to the `"mFRR CM"` (capacity market) entry. Older settled months use `"mFRR"` without suffix.
- `Estimate: true` means the value is preliminary / not yet settled.
- To get current month: `from=YYYY-MM-01&to=YYYY-MM-DD` (last day of month or today+1).
- Revenue entries only appear for days with data; missing days = no revenue.

**Monthly resolution** (`resolution=month`, observed 2026-10): one entry per service and month, `Date` is the first of the month and the response's `Resolution` is `"Month"`. The dashboard fetches all-time revenue with `from=2023-01-01&to={today}&resolution=month`:

```json
{
  "SiteId": 12345,
  "Currency": "SEK",
  "Resolution": "Month",
  "Revenue": [
    {"ServiceName": "FCR-D", "Date": "2024-03-01", "NetRevenue": 997.52, "Estimate": false},
    {"ServiceName": "mFRR", "Date": "2026-08-01", "NetRevenue": 561.78, "Estimate": false},
    {"ServiceName": "mFRR CM", "Date": "2026-10-01", "NetRevenue": 470.50, "Estimate": true},
    {"ServiceName": "mFRR EAM", "Date": "2026-10-01", "NetRevenue": 23.76, "Estimate": true}
  ]
}
```

Settled months have `Estimate: false`; the current and previous month may still be estimates.

---

## Pricing

### Get price zone

```
GET /ems/pricezone
Authorization: Bearer {jwt_token}
```

**Response 200:** Plain text, e.g. `SE4`

Swedish price zones: SE1 (north) → SE4 (south).

> ⚠️ **Changed 2026-09-23:** the web app no longer calls this endpoint, and it returns an HTTP error for at least one site. The price zone is the site's market balance area, `Mba` in [`/site/Statuses`](#get-site-statuses-rich-device-status) — use that instead.

---

### Get spot prices

```
GET /ems/spotprice?zone={zone}&fromDate={YYYY-MM-DD}&toDate={YYYY-MM-DD}&siteId={site_id}
Authorization: Bearer {jwt_token}
```

The `siteId` parameter is new (2026-09) but optional — the web app also calls with `siteId=0` before the site is known, and the response is identical without it.

**Response 200:**
```json
{
  "Currency": "SEK",
  "Prices": [
    {"Value": 1.42951, "Date": "2026-06-08T00:00:00.000"},
    {"Value": 1.47635, "Date": "2026-06-08T00:15:00.000"},
    ...
  ]
}
```

- Resolution is **15 minutes** (96 entries per day), not hourly.
- Values are in **SEK/kWh excluding VAT**.
- Multiply by 1.25 for incl. VAT.
- Fetch `fromDate=today&toDate=tomorrow` to get current day's prices.

---

### Get grid tariff

> Not observed in the 2026-09 web traffic. May still work.

```
GET /ems/gridtariff?siteId={site_id}&fromDate={YYYY-MM-DD}&toDate={YYYY-MM-DD}
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "Currency": "SEK",
  "Prices": []
}
```

Returns grid tariff prices per interval. May be empty if no time-variable tariff applies.

---

### Get tariff details

```
GET /Tariff/{tariff_id}
Authorization: Bearer {jwt_token}
```

The `tariff_id` comes from `GET /site/{site_id}` → `TariffId`.

**Response 200:**
```json
{
  "Id": 3618,
  "DisplayName": "20 A",
  "DsoDisplayName": "Example Nät AB",
  "Components": [
    {
      "Type": "fixed",
      "Prices": [
        {
          "PriceExVat": 864.0,
          "DisplayName": "20 A",
          "FixedPricePeriod": "P1M",
          "ValidFromIncluding": "2025-06-01"
        }
      ]
    },
    {
      "Type": "energy",
      "Prices": [
        {
          "PriceExVat": 0.16,
          "DisplayName": "Säkringsabonnemang",
          "EnergyPriceModel": "FIXED_PLUS_SPOT_HOURLY_PERCENTAGE",
          "SpotPricePercentage": 5.0,
          "ValidFromIncluding": "2025-06-01"
        }
      ]
    }
  ]
}
```

### Get assignable tariffs (new 2026-09)

```
GET /Tariff/assignableTariffsForSite?siteId={site_id}&mainFuse={amps}&customerType=private
Authorization: Bearer {jwt_token}
```

**Response 200:** `{"Tariffs": [ ... ]}` — an array of tariff objects with the same structure as `GET /Tariff/{tariff_id}`, listing the tariffs selectable for the site's DSO and fuse size.

---

### Get electricity agreement type

```
GET /Site/ElectricityAgreementType?siteId={site_id}
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "SiteId": 12345,
  "ElectricityAgreementType": "hourly",
  "EffectiveFrom": "2024-12-31T23:00:00Z"
}
```

`ElectricityAgreementType`: `"hourly"` = timavräkning, `"fixed"` = fast pris.

---

## EMS (Energy Management System)

### Get activation schedule

```
GET /ems/ActivationSchedule
Authorization: Bearer {jwt_token}
```

> ⚠️ **Greatly expanded 2026-09.** The response now includes the full EMS schedule, spot/energy prices, and device settings.

**Response 200 (excerpt):**
```json
{
  "FrequencyPower": [
    {
      "Time": null,
      "Up": 2880,
      "Down": 7871,
      "Fcrn": 0,
      "MfrrUp": 9000,
      "MfrrDown": 9000
    }
  ],
  "PowerConsumption": [
    {"DateTime": "2026-06-08T02:00:00Z", "Power": 575.0},
    {"DateTime": "2026-06-08T03:00:00Z", "Power": 376.0}
  ],
  "SpotPriceRaw": [
    {"DurationMin": 15, "Time": "2026-08-31T12:00:00Z", "Price": 44.75}
  ],
  "TotalEnergyPrice": {
    "DurationMinutes": 15,
    "Prices": [
      {"Time": "2026-08-31T12:30:00Z", "BuyPriceInEurMwh": 141.14, "SellPriceInEurMwh": 63.31}
    ]
  },
  "Intraday": [],
  "SystemSetting": {
    "GRID_AREA_CODE_MBA": "SE4",
    "MULTIPLIER_BATT": "1",
    "MULTIPLIER_BOUGHT": "1",
    "STREAM_BATT": "energyDischarge",
    "STREAM_BOUGHT": "energyImport",
    "DISCHARGE_MAX": "10000",
    "CHARGE_MAX": "10000",
    "BATTERY_CAPACITY": "13.1",
    "EMS_SCRIPT": ["main_ems_goodwe.py"]
  },
  "Updated": "2026-08-19T04:24:09Z",
  "DateFormat": "'M'MM'H'HH",
  "HardwareId": null,
  "GridLimit": null,
  "UserSetting": {
    "SoC Max": "90",
    "SoC Min": "10",
    "Grid Limit": "13800",
    "Manual Power": "10000",
    "Peak Shaving": "0",
    "Frequency Power": "8300",
    "Sub-tests to run": "mfrr_up_endurance,mfrr_down_endurance",
    "SvKControllerType": "6.0",
    "mFRR Up SOC Limit Lower": "25",
    "mFRR Up SOC Limit Upper": "85",
    "mFRR Down SOC Limit Lower": "25",
    "mFRR Down SOC Limit Upper": "85"
  },
  "AllowedActivationTypes": ["NONE", "PS", "LS_DCHG", "LS_CHG", "MANUAL", "FR_FCRD", "FR_FFR", "CELL_BALANCE", "FR_FCR_TEST", "SC", "FR_FCRD_SC", "FR_FCRN", "FR_IDLE", "FR_LF_CHG", "FR_LF_DCHG", "FR_MFRR_UP", "FR_MFRR_DOWN", "PREP_CHG_DCHG"],
  "Schedule": {
    "D1H00": "SC",
    "D1H01": "SC",
    "D2H00": "FR_MFRR_UP"
  },
  "MfrrUpActivation": [
    {
      "Time": "2026-10-07T04:34:00Z",
      "EndTime": "2026-10-07T05:05:00Z",
      "Power": 5614.48,
      "RampUpTime": 600,
      "RampDownTime": 600
    }
  ],
  "MfrrDownActivation": null
}
```

- `FrequencyPower.Up/Down` – FCR-D power in Watts.
- `FrequencyPower.MfrrUp/Down` – mFRR power in Watts.
- `PowerConsumption` – scheduled/forecasted household consumption per hour.
- `SpotPriceRaw` – 15-minute spot price in **EUR/MWh**. *2026-10:* the hourly `SpotPrice` array has been **removed**.
- `TotalEnergyPrice` – effective buy/sell prices in EUR/MWh per 15-minute interval.
- `Schedule` – planned EMS activation per hour, keyed `D{day}H{hour}` where D1 = today (see `DateFormat`); values are `AllowedActivationTypes` entries (`SC` = self consumption, `FR_MFRR_UP` = mFRR up reserve, etc.). *2026-10:* covers 7 days (168 keys).
- `MfrrUpActivation` / `MfrrDownActivation` – *2026-10:* now populated with the site's **actual mFRR activations** (null or absent when there are none):
  - `Time` / `EndTime` – start and end of the activation (UTC)
  - `Power` – activated power in W (≈ 5.6 kW for an `MfrrUp` bid of 6 kW)
  - `RampUpTime` / `RampDownTime` – ramp durations in seconds
  
  A response at 13:54 UTC listed activations from 04:34 UTC the previous day, so the list covers at least the past day. These activations are what the `"mFRR EAM"` revenue pays for. How soon after its start an activation is listed is not known.
- `UserSetting` – SoC limits, grid limit and other per-site EMS settings (string values). *2026-10:* new `"Sub-tests to run"` (comma-separated, e.g. `mfrr_up_endurance,mfrr_down_endurance`).
- `SystemSetting` – device-level EMS configuration (battery capacity, charge/discharge caps, EMS script). *2026-10:* new `MULTIPLIER_BATT` and `MULTIPLIER_BOUGHT`.
- `FrequencyPower.MfrrUp` and `MfrrDown` can differ (e.g. 6000 and 9000 W).
- `Updated` – when the schedule was last regenerated.

---

### Get DSO meter IDs

```
GET /ems/SiteDso?serial={rpi_serial}
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
[
  {
    "Bought": "730000000000000001",
    "Sold": "730000000000000002"
  }
]
```

EDIEL meter IDs for grid import (`Bought`) and export (`Sold`).

---

### Get EMS pending settings

> Not observed in the 2026-09 web traffic. May still work.

```
GET /ems/service/Pending?Serial={rpi_serial}
Authorization: Bearer {jwt_token}
```

Returns pending EMS configuration changes. Response is an array of service strings (e.g. `["fcrd"]` or `["sc"]`).

---

## Diagnostics

### Get connection status (new 2026-09)

```
GET /diag/{site_id}/connectionStatus?from={iso_utc}&to={iso_utc}
Authorization: Bearer {jwt_token}
```

Backs the EIB "Internet connection" and "Battery temperature" panels. The web
app queries a 5-minute window ending now (ISO 8601 UTC with milliseconds, e.g.
`2026-09-16T09:20:46.097Z`).

**Response 200:**
```json
{
  "SiteId": 12345,
  "From": "2026-09-16T09:20:46.097Z",
  "To": "2026-09-16T09:25:46.097Z",
  "Current": {"Timestamp": "2026-09-16T08:13:35Z", "Blob": "{...json string...}"},
  "History": []
}
```

`Current.Blob` is a **JSON-encoded string** with CM10 diagnostics:

```json
{
  "eth": {"eth0": {"rx_packets": 4527, "carrier_changes": 0}, "eth1": {}, "win_s": 4197},
  "topics": {
    "ems/inverter_stat": {
      "goodwe": [
        {
          "id": "192.168.5.128",
          "soc": 85.0,
          "model": "GW10KN-ET",
          "serial": "...",
          "fw_ver": "master:13-slave:13 /arm:33",
          "temp_h": 36.4,
          "temp_l": 20.8,
          "grid": 186.0,
          "pv_power": 0.0,
          "ev_power": null,
          "battery_power": -12.0,
          "battery_capacity": null,
          "set_point": 0.0,
          "master_inverter_stat": null,
          "slave_inverter_stats": null
        }
      ]
    },
    "ems/datastream_energyPv": 0.0,
    "ems/datastream_energyImport": 186.0,
    "ems/datastream_energyDischarge": -12.0
  },
  "freq_hz": null,
  "screens": ["15814.sender", "15811.goodwe", "..."],
  "arp_eth1": [{"ip": "192.168.5.128", "mac": "...", "state": ["REACHABLE"]}],
  "uptime_s": 1114187,
  "linux_ips": [{"ip": "...", "iface": "eth0"}],
  "hello_eth0": true,
  "modem_stat": {"ts": "2026-09-16 04:05:04", "status": "modem"},
  "default_route": ["ppp0", "eth0"]
}
```

Key fields:
- `topics."ems/inverter_stat".{vendor}[].temp_h` / `temp_l` – battery temperature highest/lowest (°C)
- `hello_eth0` – LAN1 internet check succeeded (EIB shows "Primary – Network cable (LAN1): Connected")
- `default_route` – active route interfaces (`eth0` = LAN1, `ppp0` = 4G modem)
- `uptime_s` – CM10 uptime in seconds
- `eth1` / `arp_eth1` – the inverter-facing LAN port
- `modem_stat.status` – `"modem"` or, *2026-10*, `"lan"` (seen on a site connected via LAN1)

New fields 2026-10: per inverter `grid` (W, grid power as the inverter sees it), `ev_power`, `battery_capacity`, `master_inverter_stat` and `slave_inverter_stats` (null on a single inverter); top-level `freq_hz` (null); per interface error counters in `eth` (`rx_errors`, `tx_errors`, `rx_dropped`, `tx_dropped`, `rx_crc_errors`, `tx_packets`); `flags` on `linux_ips` entries.

The "Available power" panel (Can charge / Can discharge) comes from
`RelatedMeters[].PeakAcKw` in `/site/Statuses`, not from this endpoint.

---

## Misc

### Get energy providers list

```
GET /controlpanel/elhandelsbolag
```

No auth required. Returns all energy retailers across SE/NO/DK/FI with Id and DisplayName. Used to resolve `ElhandelsbolagId` from customer details to a display name.

---

## Notes for HA Integration

### Recommended update intervals

| Data | Suggested interval | Endpoint |
|---|---|---|
| Real-time power flow | 60 s | `/ems/energyflow` |
| Battery SoC | 60 s | `/ems/energyflow` |
| Today's revenue | 15 min | `/revenue/{siteId}` |
| Monthly revenue | 15 min | `/revenue/{siteId}` |
| Spot price | 60 min (or at :00 when tomorrow's prices arrive ~13:00) | `/ems/spotprice` |
| Site status / CM10 seen | 5 min | `/site/Statuses` |
| Diagnostics (battery temp, connectivity) | 5 min | `/diag/{siteId}/connectionStatus` |
| mFRR activations | 5 min | `/ems/ActivationSchedule` (~40 kB) |
| All-time revenue | 15 min | `/revenue/{siteId}?resolution=month` |
| Site details / tariff | On setup + daily | `/site/{siteId}`, `/Tariff/{id}` |

### Token lifecycle

```
JWT token:       valid ~15 minutes (was ~2.25 hours; changed 2026-09)
Refresh token:   valid 14 days (was 7 days; changed 2026-09)

Strategy:
  read jwt expiry from the JWT's own exp claim
  (the JwtTokenExpires response field was removed 2026-09)
  if jwt_expiry - now < 5 min:
      GET /user/RefreshToken  (uses refresh token)
  if refresh_expiry - now < 1 day:
      POST /user/Login        (full re-login, store new refresh token)
```

With a ~15-minute JWT and a 5-minute buffer this means a token refresh roughly every 10 minutes — cheap, but do not assume a multi-hour JWT lifetime anywhere.

### Site ID vs RPI serial

Many endpoints accept either the numeric `SiteId` (e.g. `12345`) or the `RpiSerial` (e.g. `aabbccddeeff`). Fetch the site ID once at setup via `/Site/SiteIdBySerial` and cache it alongside the serial.

### Service name agnosticism

The `ServiceName` in revenue responses (`"FCR-D"`, `"mFRR CM"`, etc.) depends on the portfolio the site is enrolled in. Do not hardcode `"FCR-D"` — use `ServiceName` from the response directly as a label.
