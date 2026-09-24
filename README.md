# CheckWatt – Home Assistant Integration

Integrera ditt CheckWatt-batterisystem med Home Assistant via EnergyInBalance-portalen.

> **Obs:** Detta är en inofficiell integration och är inte kopplad till eller godkänd av CheckWatt AB.

---

## Funktioner

### Sensorer

Alla sensorer hamnar under en enhet namngiven efter din anläggning. Namnen nedan är de svenska; med engelska som språk i HA visas de engelska namnen.

**Effekt och batteri**

| Sensor | Enhet | Uppdateras |
|---|---|---|
| Solkraft | W | 60 s |
| Batterieffekt *(+ = laddning, − = urladdning)* | W | 60 s |
| Näteffekt *(+ = köper, − = säljer)* | W | 60 s |
| Batteri laddningsnivå | % | 60 s |
| Tillgänglig laddeffekt | kW | 60 s |
| Tillgänglig urladdningseffekt | kW | 60 s |
| Batteritemperatur högsta | °C | 5 min |
| Batteritemperatur lägsta | °C | 5 min |

**Intäkter och priser**

| Sensor | Enhet | Uppdateras |
|---|---|---|
| Dagens intäkt | SEK | 15 min |
| Månadsintäkt | SEK | 15 min |
| Aktiv nättjänst *(mFRR CM, FCR-D, …)* | – | 15 min |
| Spotpris *(exkl. moms)* | SEK/kWh | varje kvart *(priserna hämtas varje timme)* |
| Spotpris inkl. moms | SEK/kWh | varje kvart *(priserna hämtas varje timme)* |
| Priszon | – | 60 s |

**Energi (livstidsvärden för Energi-dashboarden)**

| Sensor | Enhet | Uppdateras |
|---|---|---|
| Total solenergi | kWh | 15 min |
| Total nätimport | kWh | 15 min |
| Total nätexport | kWh | 15 min |
| Total batteriladdning | kWh | 15 min |
| Total batteriurladdning | kWh | 15 min |

Energisensorerna har `state_class: total_increasing` och fungerar direkt med **HA:s Energi-dashboard**.

**Status**

| Sensor | Enhet | Uppdateras |
|---|---|---|
| CM10 Status | – | 60 s |
| CM10 senast sedd | tidsstämpel | 60 s |
| Växelriktare senast sedd | tidsstämpel | 60 s |
| Driftläge | – | 60 s |
| Firmware-version | – | 60 s |
| Internetanslutning | – | 5 min |
| Loggbok *(senaste händelsen; de fem senaste som attribut)* | – | 30 min |
| Senaste API-hämtning *(diagnostik, se [Felsökning](#sensorer-visar-otillgänglig))* | tidsstämpel | 60 s |

### Händelser

Händelseentiteter som kan användas som utlösare i automationer:

| Händelse | Utlöses när | Kontrolleras |
|---|---|---|
| CM10 Teststatus | CM10:ns teststatus ändras | 60 s |
| Logbokshändelse | en ny rad dyker upp i anläggningens loggbok | 30 min |
| Nyhet | EnergyInBalance publicerar en ny nyhet | 4 h |

### Autentisering

Integrationen loggar in **en gång** och återanvänder JWT-token, som är giltig i ~15 minuter. Token förnyas sedan automatiskt via refresh-token (giltig 14 dagar) utan att lösenordet behöver skickas på nytt. Full ominloggning sker automatiskt om refresh-token gått ut. Om inloggningen nekas, till exempel för att lösenordet har ändrats, ber HA dig att ange uppgifterna igen.

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
   - **Type** (*Category* i äldre HACS): Integration
4. Klicka **Add**

### Steg 2 – Installera integrationen

1. Sök efter **CheckWatt** i HACS
2. Klicka på integrationen → **Download**
3. Starta om Home Assistant

### Steg 3 – Konfigurera

1. Gå till **Inställningar → Enheter och tjänster → Lägg till integration**
2. Sök efter **CheckWatt**
3. Ange din **e-postadress** och **lösenord** för [energyinbalance.se](https://energyinbalance.se)
4. Klicka **Bekräfta**

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

Energisensorerna med livstids-kWh-värden kan läggas direkt till i HA:s inbyggda Energi-dashboard. Gå till **Inställningar → Kontrollpaneler → Energi** och lägg till:

- **Elnät → Lägg till nätanslutning**
  - *Energi importerat från nätet:* **Total nätimport**
  - *Energi exporterat till nätet:* **Total nätexport**
  - *Effektmätning* (valfritt): typ **Standard** med **Näteffekt**
- **Solpaneler → Lägg till solenergiproduktion**
  - *Solenergiproduktion:* **Total solenergi**
  - *Soleffektproduktion* (valfritt): **Solkraft**
- **Hembatteri → Lägg till batterisystem**
  - *Energi laddat in i batteriet:* **Total batteriladdning**
  - *Energi urladdat ifrån batteriet:* **Total batteriurladdning**
  - *Batteriets laddningssensor* (valfritt): **Batteri laddningsnivå**

Etiketterna är från Home Assistant 2026.9; äldre versioner kan kalla fälten något annat. Det kan ta upp till två timmar innan ny data syns i dashboarden.

---

## Felsökning

### Integrationen hittas inte i HACS

Kontrollera att du lade till repot med typen **Integration** (inte till exempel Dashboard eller Template).

### "Felaktig e-postadress eller lösenord"

Verifiera att du kan logga in på [energyinbalance.se](https://energyinbalance.se) med samma uppgifter. Står det i stället *Kunde inte ansluta till CheckWatt-API:et* nådde HA inte API:et; kontrollera nätverksanslutningen och försök igen.

### Sensorer visar "Otillgänglig"

Öppna diagnostiksensorn **Senaste API-hämtning** på CheckWatt-enheten. Dess värde är när API:et senast hämtades utan fel. Attributen visar senaste felet och, för varje långsam hämtning (`revenue`, `price`, `energy`, `logbook`, `diagnostics`, `news`), när den senast lyckades, vad som gick fel (till exempel `HTTP 404`) och när nästa försök görs.

Misslyckade hämtningar loggas också som varningar under **Inställningar → System → Loggar**. Debug-loggning visar dessutom bland annat anläggningens serienummer och site-id vid start samt energivärden som ignoreras. Slå på den under **Inställningar → Enheter och tjänster → CheckWatt → ⋮ → Aktivera felsökningsloggning**, eller i `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.checkwatt: debug
```

### Energisensorer står still

Integrationen ignorerar tomma svar, och minskningar jämfört med föregående värde sedan HA startade. HA tolkar annars en kraftig minskning som att mätaren nollställts och räknar nästa värde som ny energi i Energi-dashboarden. Om CheckWatt-API:et justerar historiska värden nedåt står sensorn därför still tills den verkliga summan passerat det tidigare värdet.

---

## Bidra

Pull requests och issues välkomnas på [GitHub](https://github.com/andreasthell/ha-cw/issues).

API-dokumentation finns i [`docs/api.md`](docs/api.md).
