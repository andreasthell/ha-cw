# CheckWatt – Home Assistant Integration

Integrera ditt CheckWatt-batterisystem med Home Assistant via EnergyInBalance-portalen.

> **Obs:** Detta är en inofficiell integration och är inte kopplad till eller godkänd av CheckWatt AB.

---

## Funktioner

### Sensorer (19 st)

| Sensor | Enhet | Uppdateringsintervall |
|---|---|---|
| Solkraft | W | 60 s |
| Batterieffekt *(+ = laddning, − = urladdning)* | W | 60 s |
| Näteffekt *(+ = köper, − = säljer)* | W | 60 s |
| Batteri laddningsnivå | % | 60 s |
| Dagens intäkt | SEK | 15 min |
| Månadsintäkt | SEK | 15 min |
| Aktiv nättjänst *(mFRR CM, FCR-D, …)* | – | 15 min |
| Spotpris exkl. moms | SEK/kWh | 60 min |
| Spotpris inkl. moms | SEK/kWh | 60 min |
| Total solenergi | kWh | 15 min |
| Total nätimport | kWh | 15 min |
| Total nätexport | kWh | 15 min |
| Total batteriladdning | kWh | 15 min |
| Total batteriurladdning | kWh | 15 min |
| CM10 senast sedd | tidsstämpel | 60 s |
| Växelriktare senast sedd | tidsstämpel | 60 s |
| Driftläge | – | 60 s |
| Priszon | – | 60 min |

Energisensorerna har `state_class: total_increasing` och fungerar direkt med **HA:s Energi-dashboard**.

### Autentisering

Integrationen loggar in **en gång** och återanvänder JWT-token i ~2 timmar. Token förnyas sedan automatiskt via refresh-token (giltig 7 dagar) utan att lösenordet behöver skickas på nytt. Full ominloggning sker automatiskt om refresh-token gått ut.

---

## Installation via HACS

### Förutsättningar

- Home Assistant 2024.11 eller senare
- [HACS](https://hacs.xyz) installerat

### Steg 1 – Lägg till som custom repository

1. Öppna HACS i Home Assistant
2. Klicka på **⋮** (tre punkter) längst upp till höger → **Custom repositories**
3. Fyll i:
   - **Repository:** `https://github.com/andreasthell/ha-cw`
   - **Category:** Integration
4. Klicka **Add**

### Steg 2 – Installera integrationen

1. Sök efter **CheckWatt** i HACS
2. Klicka på integrationen → **Download**
3. Starta om Home Assistant

### Steg 3 – Konfigurera

1. Gå till **Inställningar → Enheter & tjänster → Lägg till integration**
2. Sök efter **CheckWatt**
3. Ange din **e-postadress** och **lösenord** för [energyinbalance.se](https://energyinbalance.se)
4. Klicka **Skicka**

Alla sensorer visas nu under en enhet namngiven efter din anläggning.

---

## Manuell installation

Om du föredrar att installera utan HACS:

1. Ladda ner eller klona detta repo
2. Kopiera mappen `custom_components/checkwatt` till din HA-konfigurationsmapp:
   ```
   <config>/custom_components/checkwatt/
   ```
3. Starta om Home Assistant
4. Följ steg 3 ovan

---

## HA Energi-dashboard

Energisensorerna med livstids-kWh-värden kan läggas direkt till i HA:s inbyggda Energi-dashboard:

1. Gå till **Energi** i sidomenyn → **Konfigurera Energi**
2. Lägg till:
   - **Solproduktion:** *Total solenergi*
   - **Nätkonsumption:** *Total nätimport*
   - **Nätåtermatning:** *Total nätexport*
   - **Batterilagring:** *Total batteriladdning* + *Total batteriurladdning*

---

## Felsökning

### Integrationen hittas inte i HACS

Kontrollera att du lade till repot som category **Integration** (inte Automation).

### "Invalid email address or password"

Verifiera att du kan logga in på [energyinbalance.se](https://energyinbalance.se) med samma uppgifter.

### Sensorer visar "Unavailable"

Aktivera debug-loggning i `configuration.yaml` för att se detaljerade felmeddelanden:

```yaml
logger:
  default: warning
  logs:
    custom_components.checkwatt: debug
```

### Energisensorer backar i värde

Om `total_increasing`-sensorerna ibland minskar beror det troligen på att CheckWatt-API:et returnerar justerade historiska värden. HA hanterar detta automatiskt och ignorerar minskningar.

---

## Bidra

Pull requests och issues välkomnas på [GitHub](https://github.com/andreasthell/ha-cw/issues).

API-dokumentation finns i [`docs/api.md`](docs/api.md).
