# CheckWatt / EnergyInBalance API Documentation

Base URL: `https://api.checkwatt.se`  
Web app: `https://energyinbalance.se`

> Reverse-engineered from browser traffic. Not an official API. Subject to change without notice.
>
> Last verified against a HAR export from the updated EnergyInBalance web app on **2026-09-01**.
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
- `Version` – CM10 firmware version (`.83` suffix = device under test)
- `LastSeenCm10` – last contact from CM10 device
- `LastSeenInverter` – last data from inverter
- `FpUpInKw` / `FpDownInKw` – contracted FCR-D power up/down
- `OperationPreference` – `"co"` = Currently Optimized, `"sc"` = Self Consumption
- `TestInfo.Latest` – activation test result

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

**`resolution` values:** `Minute` (new 2026-09), `FifteenMinutes`.

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
- The `delta` grouping was used for the live "today" view (per-minute resolution); as of 2026-09 the web app uses `/SiteMeasurements/{site_id}/Data` with `resolution=Minute` for that instead. The endpoint itself is still in use (the web app fetches all-time yearly totals with `grouping=3`).

---

## Revenue

### Get revenue for date range

```
GET /revenue/{site_id}?from={YYYY-MM-DD}&to={YYYY-MM-DD}&resolution=day
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

- `ServiceName` reflects the actual grid service (e.g. `"mFRR CM"`, `"FCR-D"`) – do not hardcode.
- `Estimate: true` means the value is preliminary / not yet settled.
- To get current month: `from=YYYY-MM-01&to=YYYY-MM-DD` (last day of month or today+1).
- Revenue entries only appear for days with data; missing days = no revenue.

---

## Pricing

### Get price zone

```
GET /ems/pricezone
Authorization: Bearer {jwt_token}
```

**Response 200:** Plain text, e.g. `SE4`

Swedish price zones: SE1 (north) → SE4 (south).

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
  "SpotPrice": [
    {"Time": "2026-08-31T12:00:00Z", "Price": 54.18}
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
  "MfrrUpActivation": null,
  "MfrrDownActivation": null
}
```

- `FrequencyPower.Up/Down` – FCR-D power in Watts.
- `FrequencyPower.MfrrUp/Down` – mFRR power in Watts.
- `PowerConsumption` – scheduled/forecasted household consumption per hour.
- `SpotPrice` – hourly spot price in **EUR/MWh**; `SpotPriceRaw` – 15-minute resolution.
- `TotalEnergyPrice` – effective buy/sell prices in EUR/MWh per 15-minute interval.
- `Schedule` – planned EMS activation per hour, keyed `D{day}H{hour}` where D1 = today (see `DateFormat`); values are `AllowedActivationTypes` entries (`SC` = self consumption, `FR_MFRR_UP` = mFRR up reserve, etc.).
- `UserSetting` – SoC limits, grid limit and other per-site EMS settings (string values).
- `SystemSetting` – device-level EMS configuration (battery capacity, charge/discharge caps, EMS script).
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
