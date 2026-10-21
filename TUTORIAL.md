# PeopleGator — uživatelský návod / user tutorial

[Česky](#cesky) · [English](#english)

<a id="cesky"></a>

## Česky

Ve sdílené živé ukázce máme zpracováno **7 dokumentů**.
Pro vyzkoušení můžete otevřít následující dokumenty přímo v aplikaci:

| Knihovna | Dokument |
| --- | --- |
| svkhk | [6c50c29e-1994-46e6-b2ac-0289006fb764](https://live-preview.peoplegator.dev/scans?library=svkhk&document=6c50c29e-1994-46e6-b2ac-0289006fb764) |
| knav | [2e31b2f2-7936-4234-bede-a6a2f9c452b5](https://live-preview.peoplegator.dev/scans?library=knav&document=2e31b2f2-7936-4234-bede-a6a2f9c452b5) |
| svkhk | [6c466752-a299-4bde-a8b0-92a560976826](https://live-preview.peoplegator.dev/scans?library=svkhk&document=6c466752-a299-4bde-a8b0-92a560976826) |
| svkhk | [1faae15d-13ed-4ca5-ac61-6a085a48de33](https://live-preview.peoplegator.dev/scans?library=svkhk&document=1faae15d-13ed-4ca5-ac61-6a085a48de33) |
| svkhk | [e5acee37-b093-41aa-9656-d7477f8c2730](https://live-preview.peoplegator.dev/scans?library=svkhk&document=e5acee37-b093-41aa-9656-d7477f8c2730) |
| knav | [3aa8d947-24a8-40b0-981c-a3b9cea401e6](https://live-preview.peoplegator.dev/scans?library=knav&document=3aa8d947-24a8-40b0-981c-a3b9cea401e6) |
| knav | [b67494e1-4eb3-4ecd-bc99-405721f778e9](https://live-preview.peoplegator.dev/scans?library=knav&document=b67494e1-4eb3-4ecd-bc99-405721f778e9) |

### 1. Otevření aplikace

Otevřete [živou ukázku PeopleGator](https://live-preview.peoplegator.dev).
V této ukázce není nutné přihlášení ani registrace. Dostupnost úprav závisí na
oprávněních daného prostředí; sloučení osob vyžaduje oprávnění správce.

Screenshoty ukazují syntetická data, například Ada Novak a knihovnu
`preview-mzk`. Jde o záběry z počítače (1440 × 900 CSS px). Postupy jsou stejné
i pro dokumenty v živé ukázce.

Začít můžete na [připravené anotované stránce](https://live-preview.peoplegator.dev/libraries/svkhk/documents/6c50c29e-1994-46e6-b2ac-0289006fb764/pages/2a484f45-2393-11ed-afbf-00155d01210b):

- **Knihovna:** `svkhk`
- **Dokument:** `6c50c29e-1994-46e6-b2ac-0289006fb764`
- **Stránka:** `2a484f45-2393-11ed-afbf-00155d01210b`

### 2. Hledání dokumentů a osob

- V **Documents** zadejte do hledání název dokumentu, jméno osoby nebo UUID.
  Pro ukázku zkuste UUID dokumentu uvedené výše. Otevřete náhled stránky
  příslušného dokumentu; dostanete se ke skenu a přepisu textu.
- V **People** hledejte podle jména nebo aliasu. Otevřete nalezený profil:
  **Faces** obsahuje přiřazené tváře, **Mentions** textové zmínky a **Discover**
  návrhy podobných tváří a osob.
- **Scan search** slouží k vyhledávání jednotlivých stránek. Na otevřeném skenu
  můžete obraz přibližovat a posouvat. Kliknutím na označenou tvář nebo jméno
  v přepisu vyberete anotaci. Další stránky dokumentu otevřete v pásu
  **Document pages** pod skenem.

Hledání dokumentu podle názvu.

![Hledání dokumentu podle názvu. / Search for a document by title. — desktop](docs/images/tutorial/01-document-search-desktop.png)

Stránky vybraného dokumentu.

![Stránky vybraného dokumentu. / Pages of the selected document. — desktop](docs/images/tutorial/03-document-pages-desktop.png)

Hledání osoby podle jména.

![Hledání osoby podle jména. / Search for a person by name. — desktop](docs/images/tutorial/04-person-search-desktop.png)

Sken, označené tváře a textové zmínky.

![Sken, označené tváře a textové zmínky. / Scan, marked faces and text mentions. — desktop](docs/images/tutorial/08-scan-and-mentions-desktop.png)

### 3. Filtrování výsledků

V **Documents** zkuste vybrat knihovnu `svkhk` v **Libraries**. V **People**
můžete použít **Documents**, **Assignment** nebo **Link state**. Další filtry
omezují výsledky podle uživatele, API klíče a data; rozlišujte popisky
**Document processing**, **Person record** a **Annotation last** — vztahují se
k různým záznamům a změnám.

Na mobilu otevřete filtry tlačítkem s ikonou posuvníků vedle hledání.
Aktivní filtry jsou zobrazené jako štítky pod panelem. Křížkem odstraníte
jednotlivý filtr; **Clear all filters** zruší filtry a zachová hledaný text.
Text vymažete samostatným křížkem v hledání. Pokud výsledky chybí, nejprve
zkontrolujte aktivní štítky. Filtry se mezi obrazovkami zatím nepřenášejí vždy
jednotně; po přechodu zkontrolujte jejich nastavení.

Hledání s aktivním filtrem knihovny.

![Hledání s aktivním filtrem knihovny. / Search with an active library filter. — desktop](docs/images/tutorial/02-active-filters-desktop.png)

### 4. Přiřazení tváře k osobě

Na skenu vyberte tvář a v panelu **Faces** zkontrolujte její přiřazení:

- **Link** otevře výběr existující osoby; vyhledejte jméno a u kandidáta zvolte
  **Assign**.
- **Reassign** umožní vybrat jinou osobu a potvrdit změnu u kandidáta tlačítkem
  **Reassign**.
- **Unlink** zruší přiřazení, ale zachová detekci tváře.
- **New** umožní zadat jméno, případně krátký popis. Tlačítkem **Save**
  vytvoříte profil a přiřadíte k němu vybranou tvář; **Cancel** úpravu zruší.

Po uložení zkontrolujte jméno a stav u vybrané tváře. Kliknutím na jméno
otevřete profil. Textové zmínky lze prohlížet a ověřovat v **Mentions**;
výše uvedené akce popisují ovládání tváří, nikoli editor textových úseků.

Výběr osoby a tlačítko Assign.

![Výběr osoby a tlačítko Assign. / Choose a person and use Assign. — desktop](docs/images/tutorial/13-link-candidate-desktop.png)

Ruční přeřazení tváře k jiné osobě.

![Ruční přeřazení tváře k jiné osobě. / Manually reassign a face to another person. — desktop](docs/images/tutorial/09-reassignment-desktop.png)

Po Unlink zůstane tvář nepřiřazená.

![Po Unlink zůstane tvář nepřiřazená. / After Unlink, the face remains unassigned. — desktop](docs/images/tutorial/12-unassigned-desktop.png)

Vytvoření nové osoby pomocí New → Save a její přiřazená tvář.

![Nový profil / New profile — desktop](docs/images/tutorial/19-new-profile-desktop.png)

Výsledek najdete v záložce Faces nového profilu.

![Vytvořený profil / Created profile — desktop](docs/images/tutorial/20-new-profile-result-desktop.png)

### 5. Dohledání podobných tváří

V profilu osoby otevřete **Discover → Similar faces to review**. Osoba potřebuje
alespoň jednu přiřazenou tvář použitelnou pro porovnání. Filtrem
**Discovery assignment** lze vybrat **Unassigned** nebo **Assigned elsewhere**.

Nejprve otevřete náhled a porovnejte tvář v původním skenu. Potom vyberte
vhodné tváře zaškrtávacími políčky a klikněte na **Assign to [jméno]**.
Tváře přiřazené jinam se tím přeřadí. Výsledek zkontrolujte v **Faces**;
skóre podobnosti je návrh, nikoli potvrzení totožnosti.

Výběr podobné tváře a přiřazení k otevřené osobě.

![Výběr podobné tváře a přiřazení k otevřené osobě. / Select a similar face and assign it to the open person. — desktop](docs/images/tutorial/16-discover-assignment-desktop.png)

### 6. Sloučení duplicitních osob

Otevřete profil, který chcete **zachovat**, a přejděte do
**Discover → Other similar people**. Podle potřeby upravte hledání
**Search by name or alias**. Prohlédněte si kandidáty a jejich podklady,
potom výběrovým tlačítkem označte pouze skutečně duplicitní osoby.

Tlačítko **Merge into [jméno]** přesune jejich tváře a zmínky do otevřeného
profilu a odstraní vybrané původní záznamy osob. Zkontrolujte jméno cíle před
kliknutím: akce se odesílá přímo, bez dalšího potvrzovacího dialogu a bez
tlačítka pro vrácení sloučení. Po dokončení ověřte **Faces** a **Mentions**
zachovaného profilu. Pro přiřazení jedné tváře použijte **Assign**, nikoli merge.
Přesunutá přiřazení budou mít stav **Manual** a případné původní ověření se
zruší; po kontrole je můžete znovu ověřit.

Vybraná duplicita a cílová osoba v tlačítku Merge into.

![Vybraná duplicita a cílová osoba v tlačítku Merge into. / Selected duplicate and destination in the Merge into button. — desktop](docs/images/tutorial/17-merge-selection-desktop.png)

Tváře zachovaného profilu po sloučení.

![Tváře zachovaného profilu po sloučení. / Faces on the retained profile after merging. — desktop](docs/images/tutorial/18-merge-result-desktop.png)

### 7. Ověření a oprava přiřazení

| Stav | Význam |
| --- | --- |
| **Automatic** | Automatické přiřazení. |
| **Manual** | Ruční přiřazení. |
| **Verified** | Přiřazení potvrzené uživatelem. |
| **Unassigned** | Tvář nebo zmínka nemá přiřazenou osobu. |

Po porovnání tváře s podklady klikněte na **Verify link** u vybrané tváře
na skenu. Textovou zmínku ověříte stejným tlačítkem v profilu v **Mentions**.
Stav se změní na **Verified**; u ověřeného přiřazení lze zobrazit autora a čas
ověření, pokud jsou zaznamenány. Ověřujete vazbu k osobě, nikoli celý sken
nebo správnost přepisu OCR.

Pro hromadné ověření v **Faces** označte tváře a použijte
**Verify selected (počet)**. Chybné přiřazení tváře nejprve opravte pomocí
**Reassign**, případně **Unlink**; v profilu lze použít **Unassign selected**.
Změna na jinou osobu vytváří ruční přiřazení, které můžete po kontrole znovu
ověřit. Po chybové hlášce zkontrolujte obnovený výsledek před opakováním akce.

Stavy přiřazení na profilu osoby.

![Stavy přiřazení na profilu osoby. / Assignment states on a person profile. — desktop](docs/images/tutorial/05-person-states-desktop.png)

Výběr tváře a hromadné Verify selected.

![Výběr tváře a hromadné Verify selected. / Face selection and batch Verify selected. — desktop](docs/images/tutorial/06-batch-verification-desktop.png)

Ověřené přiřazení s autorem a časem.

![Ověřené přiřazení s autorem a časem. / Verified assignment with its actor and timestamp. — desktop](docs/images/tutorial/11-verified-link-desktop.png)

Ověření textové zmínky v Mentions.

![Ověření textové zmínky v Mentions. / Verify a text mention in Mentions. — desktop](docs/images/tutorial/14-mention-verification-desktop.png)

### Další obrázky

[Přehled všech screenshotů a ověřených postupů](docs/images/tutorial/README.md)
obsahuje i stav před ověřením a výsledek hromadného ověření.

<a id="english"></a>

## English

The shared live demo contains **7 processed documents**.
Use these links to open the following documents directly in the application:

| Library | Document |
| --- | --- |
| svkhk | [6c50c29e-1994-46e6-b2ac-0289006fb764](https://live-preview.peoplegator.dev/scans?library=svkhk&document=6c50c29e-1994-46e6-b2ac-0289006fb764) |
| knav | [2e31b2f2-7936-4234-bede-a6a2f9c452b5](https://live-preview.peoplegator.dev/scans?library=knav&document=2e31b2f2-7936-4234-bede-a6a2f9c452b5) |
| svkhk | [6c466752-a299-4bde-a8b0-92a560976826](https://live-preview.peoplegator.dev/scans?library=svkhk&document=6c466752-a299-4bde-a8b0-92a560976826) |
| svkhk | [1faae15d-13ed-4ca5-ac61-6a085a48de33](https://live-preview.peoplegator.dev/scans?library=svkhk&document=1faae15d-13ed-4ca5-ac61-6a085a48de33) |
| svkhk | [e5acee37-b093-41aa-9656-d7477f8c2730](https://live-preview.peoplegator.dev/scans?library=svkhk&document=e5acee37-b093-41aa-9656-d7477f8c2730) |
| knav | [3aa8d947-24a8-40b0-981c-a3b9cea401e6](https://live-preview.peoplegator.dev/scans?library=knav&document=3aa8d947-24a8-40b0-981c-a3b9cea401e6) |
| knav | [b67494e1-4eb3-4ecd-bc99-405721f778e9](https://live-preview.peoplegator.dev/scans?library=knav&document=b67494e1-4eb3-4ecd-bc99-405721f778e9) |

### 1. Open the application

Open the [PeopleGator live demo](https://live-preview.peoplegator.dev).
This demo requires no login or registration. Editing depends on the permissions
available in that environment; merging people requires administrator permission.

Screenshots use synthetic data, such as Ada Novak and the `preview-mzk` library.
The images show the desktop view (1440 × 900 CSS px). The same workflows apply
to the documents in the live demo.

Start with the [prepared annotated page](https://live-preview.peoplegator.dev/libraries/svkhk/documents/6c50c29e-1994-46e6-b2ac-0289006fb764/pages/2a484f45-2393-11ed-afbf-00155d01210b):

- **Library:** `svkhk`
- **Document:** `6c50c29e-1994-46e6-b2ac-0289006fb764`
- **Page:** `2a484f45-2393-11ed-afbf-00155d01210b`

### 2. Find documents and people

- In **Documents**, search for a document title, person's name or UUID.
  Try the document UUID above. Open a page preview in the matching document
  to view its scan and transcription.
- In **People**, search by name or alias. Open a matching profile:
  **Faces** contains linked faces, **Mentions** contains text mentions, and
  **Discover** offers similar faces and people.
- **Scan search** searches individual pages. You can zoom and pan an open scan.
  Click a marked face or a name in the transcription to select an annotation.
  Open other pages using the **Document pages** strip below the scan.

Search for a document by title.

![Hledání dokumentu podle názvu. / Search for a document by title. — desktop](docs/images/tutorial/01-document-search-desktop.png)

Pages of the selected document.

![Stránky vybraného dokumentu. / Pages of the selected document. — desktop](docs/images/tutorial/03-document-pages-desktop.png)

Search for a person by name.

![Hledání osoby podle jména. / Search for a person by name. — desktop](docs/images/tutorial/04-person-search-desktop.png)

Scan, marked faces and text mentions.

![Sken, označené tváře a textové zmínky. / Scan, marked faces and text mentions. — desktop](docs/images/tutorial/08-scan-and-mentions-desktop.png)

### 3. Filter results

In **Documents**, try selecting `svkhk` under **Libraries**. In **People**, use
**Documents**, **Assignment** or **Link state**. Other filters narrow results
by user, API key and date; distinguish the labels **Document processing**,
**Person record** and **Annotation last** — they refer to different records
and changes.

On mobile, open filters with the sliders button beside search. Active filters
appear as tags below the panel. Remove one with its X button;
**Clear all filters** removes filters while preserving the search text.
Clear the text separately with the X inside search. If results are missing,
check the active tags first. Filters are not yet transferred consistently
between screens; check their settings after navigating.

Search with an active library filter.

![Hledání s aktivním filtrem knihovny. / Search with an active library filter. — desktop](docs/images/tutorial/02-active-filters-desktop.png)

### 4. Link a face to a person

Select a face on the scan and inspect its assignment in the **Faces** panel:

- **Link** opens the existing-person selection; search for a name and choose
  **Assign** on the candidate.
- **Reassign** lets you select another person and confirm with **Reassign**
  on the candidate.
- **Unlink** removes the assignment while keeping the face detection.
- **New** lets you enter a name and optionally a short description. **Save**
  creates the profile and links the selected face; **Cancel** discards the edit.

After saving, check the selected face's name and state. Click the name to open
the profile. Text mentions can be inspected and verified in **Mentions**;
the actions above describe face controls rather than a text-span editor.

Choose a person and use Assign.

![Výběr osoby a tlačítko Assign. / Choose a person and use Assign. — desktop](docs/images/tutorial/13-link-candidate-desktop.png)

Manually reassign a face to another person.

![Ruční přeřazení tváře k jiné osobě. / Manually reassign a face to another person. — desktop](docs/images/tutorial/09-reassignment-desktop.png)

After Unlink, the face remains unassigned.

![Po Unlink zůstane tvář nepřiřazená. / After Unlink, the face remains unassigned. — desktop](docs/images/tutorial/12-unassigned-desktop.png)

Create a new person with New → Save and inspect its linked face.

![Nový profil / New profile — desktop](docs/images/tutorial/19-new-profile-desktop.png)

The result appears in the new profile's Faces tab.

![Vytvořený profil / Created profile — desktop](docs/images/tutorial/20-new-profile-result-desktop.png)

### 5. Find similar faces

In a person's profile, open **Discover → Similar faces to review**. The person
needs at least one linked face usable for comparison. Use **Discovery assignment**
to choose **Unassigned** or **Assigned elsewhere**.

First open a preview and compare the face in its source scan. Then select
suitable faces with their checkboxes and click **Assign to [name]**.
Faces linked elsewhere will be reassigned. Check the result in **Faces**;
the similarity score is a suggestion, not proof of identity.

Select a similar face and assign it to the open person.

![Výběr podobné tváře a přiřazení k otevřené osobě. / Select a similar face and assign it to the open person. — desktop](docs/images/tutorial/16-discover-assignment-desktop.png)

### 6. Merge duplicate people

Open the profile you want to **keep**, then go to
**Discover → Other similar people**. Adjust **Search by name or alias** if needed.
Inspect the candidates and their evidence, then use their selection buttons
to select only genuine duplicate people.

**Merge into [name]** moves their faces and mentions into the open profile
and deletes the selected source person records. Check the destination name
before clicking: the action is submitted directly, with no additional
confirmation dialog or undo button. Afterwards, check **Faces** and **Mentions**
on the retained profile. Use **Assign** to link a single face rather than merge.
Moved assignments become **Manual** and any previous verification is cleared;
you can verify them again after review.

Selected duplicate and destination in the Merge into button.

![Vybraná duplicita a cílová osoba v tlačítku Merge into. / Selected duplicate and destination in the Merge into button. — desktop](docs/images/tutorial/17-merge-selection-desktop.png)

Faces on the retained profile after merging.

![Tváře zachovaného profilu po sloučení. / Faces on the retained profile after merging. — desktop](docs/images/tutorial/18-merge-result-desktop.png)

### 7. Verify and correct assignments

| State | Meaning |
| --- | --- |
| **Automatic** | Automatically assigned. |
| **Manual** | Manually assigned. |
| **Verified** | Assignment confirmed by a user. |
| **Unassigned** | The face or mention has no assigned person. |

After comparing a face with the evidence, click **Verify link** for the selected
face on the scan. Verify a text mention using the same button under **Mentions**
in the person's profile. The state becomes **Verified**; verification details
show who verified it and when, if recorded. Verification confirms the link to
a person, rather than the whole scan or the accuracy of OCR text.

To verify several faces, select them in **Faces** and choose
**Verify selected (count)**. Correct a wrong face assignment with **Reassign**
or **Unlink** first; the profile also provides **Unassign selected**.
Changing to another person creates a manual assignment, which you can verify
again after review. If an error appears, inspect the refreshed result before
repeating the action.

Assignment states on a person profile.

![Stavy přiřazení na profilu osoby. / Assignment states on a person profile. — desktop](docs/images/tutorial/05-person-states-desktop.png)

Face selection and batch Verify selected.

![Výběr tváře a hromadné Verify selected. / Face selection and batch Verify selected. — desktop](docs/images/tutorial/06-batch-verification-desktop.png)

Verified assignment with its actor and timestamp.

![Ověřené přiřazení s autorem a časem. / Verified assignment with its actor and timestamp. — desktop](docs/images/tutorial/11-verified-link-desktop.png)

Verify a text mention in Mentions.

![Ověření textové zmínky v Mentions. / Verify a text mention in Mentions. — desktop](docs/images/tutorial/14-mention-verification-desktop.png)

### More screenshots

The [screenshot and checked-workflow index](docs/images/tutorial/README.md)
also includes the state before verification and the batch-verification result.
