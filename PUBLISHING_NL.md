# Publiceren en bijwerken

## Aanbevolen opzet

Gebruik **GitHub als hoofdbron** voor versiebeheer, documentatie en losse releases. Gebruik **CivitAI als vindbare showcase en downloadspiegel** met voorbeelden, tags en een link naar GitHub.

GitHub bewaart iedere wijziging als commit. Een release-tag zoals `v1.2.0` maakt daarvan een vaste downloadbare versie. CivitAI is geschikter om de workflow te presenteren aan gebruikers die al naar ComfyUI-resources zoeken.

## Wat hoort in een openbare release?

- De opgeschoonde `*_PUBLIC.json`.
- `README.md` met installatie en downloadlinks.
- `GUIDE.md` met gebruiksinstructies.
- `CHANGELOG.md` met alleen veranderingen sinds de vorige versie.
- De twee eigen helper-nodefolders onder `custom_nodes/`.
- Optioneel: één korte voorbeeldvideo en één duidelijke workflow-screenshot.
- `LICENSE` met de CC0 1.0-publiekdomeinverklaring.

Publiceer geen modellen, muziek, referentiebeelden of andere media waarvoor je geen distributierechten hebt.

## Zelf de workflow opschonen

1. Bewaar je werkbestand onder `work/`; die map staat in `.gitignore`.
2. Sla in ComfyUI eerst een versie op die je werkelijk hebt getest.
3. Maak de openbare kopie met `tools/New-PublicWorkflow.ps1`.
4. Controleer de openbare JSON op lokale schijfletters, gebruikersnamen en oude media.
5. Open de openbare JSON opnieuw in ComfyUI en controleer missing nodes, rode nodes en verbindingen.
6. Vul tijdelijke testmedia in, draai minstens één korte preview en test daarna de selectie/final-pass.
7. Sla testmedia niet terug in de openbare JSON; voer de cleaner opnieuw uit na de test.

De cleaner verwijdert of neutraliseert:

- lokale bronvideo- en outputpaden;
- namen van referentiebeelden en audiobestanden;
- oude videopreviewmetadata;
- de projectspecifieke generatieprompt;
- niet-nodige lokale model-hashmetadata;
- interne namen van oude bronworkflows.

Hij laat modelnamen, instellingen, verbindingen, groepen, nodeposities en instructienodes intact.

## Controlecommando's

Zoek vóór publicatie naar Windows-paden:

```powershell
Select-String -Path .\H3_SeedHunter_Long_Form_Video_v1.2_PUBLIC.json -Pattern '[A-Za-z]:\\\\'
```

Controleer of de JSON geldig is:

```powershell
Get-Content .\H3_SeedHunter_Long_Form_Video_v1.2_PUBLIC.json -Raw |
  ConvertFrom-Json -Depth 100 | Out-Null
```

Bekijk welke bestanden Git gaat publiceren:

```powershell
git status --short
```

## Eerste GitHub-publicatie

1. De release gebruikt CC0 1.0 voor jouw eigen workflow, documentatie en helpercode. Externe onderdelen behouden hun eigen licenties.
2. Maak een lege openbare repository aan, bijvoorbeeld `ComfyUI-H3-SeedHunter-LongForm`.
3. Initialiseer deze map lokaal en koppel de lege repository.
4. Commit de bestanden.
5. Push de `main`-branch.
6. Maak een release met tag `v1.2.0` en voeg het ZIP-pakket als releasebestand toe.

Voor volgende versies:

```powershell
git add .
git commit -m "Release v1.3.0"
git push
git tag v1.3.0
git push origin v1.3.0
```

Maak daarna op GitHub een nieuwe release bij die tag en schrijf korte release notes vanuit `CHANGELOG.md`.

## CivitAI-publicatie

Maak een nieuwe resource van het type workflow en gebruik dezelfde versienaam, bijvoorbeeld `1.2.0`. Upload de openbare JSON of het ZIP-pakket, voeg representatieve eigen voorbeeldmedia toe en neem minimaal op:

- benodigde ComfyUI- en custom-nodeversies;
- model- en LoRA-links;
- aanbevolen VRAM en bekende beperkingen;
- de drie audiomodi;
- de preview/select/final/extend-volgorde;
- credits en licentie;
- een link naar de GitHub-repository als technische hoofdbron.

Maak bij iedere update een nieuwe versie aan in plaats van het oude bestand stilzwijgend te vervangen. Zo kunnen gebruikers terug naar een werkende release.

## Versienummers

Gebruik bij voorkeur `MAJOR.MINOR.PATCH`:

- `PATCH` (`1.2.1`): documentatie, paden of kleine reparaties zonder gewijzigde werkwijze.
- `MINOR` (`1.3.0`): nieuwe nodes, modi of functies die oude projecten niet bewust breken.
- `MAJOR` (`2.0.0`): ingrijpende wijzigingen die installatie of gebruik incompatibel maken.
