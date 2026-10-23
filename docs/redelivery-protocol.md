# Source-derived redelivery protocol

Inspected README and downloaded chunks 24, 26 and 28; no network requests or submissions. These are client observations, not a server-validated schema. Main references: chunk 24 date selection (`V=...scnHttKboDayJhoLst`, `pt`, `bt`, `kt`, `gt`); chunk 26 module 839 confirmation button; chunk 28 module 844 detail navigation.

## Eligibility and response state

The detail response is stored as `ParcelReducer.NRCWBRP0610Mdl.result0020`; it contains `nmtJho`, `henKahHntKkaJho`, `scnHttKboDayJhoLst`, `scnHttKboBsyJhoLst`, and other data. Raw API responses have a `result` wrapper before this reducer assignment. In chunk 28, date-change action `"1"` refuses navigation when `result0020.henKahHntKkaJho.jtkNaiUktHenKahFlg === "0"`; the rendered change button requires the flag to equal `"1"`. Place-change uses `jtkGaiUktHenKahFlg` separately. Do not infer date eligibility from a successful tracking lookup alone.

Chunk 28 also handles transfer parcels using separate `result0020Before` and `result0020After` and switches the active `result0020`. Always associate options and identity with the same active `nmtJho.okjNo`. Confirmation checks that this tracking number matches the saved form tracking number before constructing the request. Detail initialization can set absent `nrkSrkFlg` to `"0"` for the guest login classification (`result0150.lgiJho.lgiKbn1 === "0"`).

## Exact slot fields

Each element of `result.scnHttKboDayJhoLst` has these consumed fields:

| Field | Client use |
| --- | --- |
| `scnHttDay` | Actual date value; converted to `YYYYMMDD` at confirmation |
| `scnHttDayNm` | Display label, also used internally to find the selected date |
| `scnHttDayHttKnoFlg` | Date radio disabled exactly when equal to string `"0"`; fallback chooser requires `"1"` |
| `scnHttHdkDftStkFlg` | Default selected date when equal to `"1"` |
| `scnHttDayHenMaeStkFlg` | Marks previous date for before/after display |
| `scnHttKboJktJhoLst` | Per-date time windows |

Each nested time element consumes `scnHttJktCd` (opaque submission code), `scnHttJktNm` (label), `scnHttJktHttKnoFlg` (disabled exactly for `"0"`, fallback requires `"1"`), `scnHttZkntDftStkFlg` (default `"1"`), and `scnHttJktHenMaeStkFlg` (previous choice `"1"`). The UI resolves time labels to codes inside the selected date, never from a global list. Preserve codes as strings. Do not hardcode nationwide delivery windows.

Receiving methods come from `scnHttKboBsyJhoLst`: `scnHttBsyCd`, `scnHttBsyNm`, `scnHttBsyHenMaeStkFlg`. Previous method is preferred; otherwise first method is selected. A saved history method can override it.

Date/time choice is hidden for `(nmtJho.syhKbnCd !== "12" && method === "02")` or `(nmtJho.npsHtmOkhKnoFlg === TARGET && nmtJho.sisStsKbn === DELIVERY)`. In those cases `kt()` selects the first date with date availability `"1"` and first nested time with time availability `"1"`. This does not mean the user can choose arbitrary slots. `DELIVERY` is `"20"` in shared chunk 6. The delivery-box method `"02"` is explicitly described by the UI as disallowing date/time designation.

## Confirmation request

POST `receive_parcel/v1/registChangeReceiveParcel` takes an object rooted at `uktHenTrkJho`. The shared HTTP interceptor adds transport metadata described in README.

Always initialized by the button:

- `iriCd`: `"3"` when detail `nmtJho.tksySyhFlg === "1"`, otherwise `"1"`.
- `dnpNo`: active detail `nmtJho.okjNo` or empty string.
- `tucYouNisKey`: route `params.enc` or empty string.
- `uktHenSniMtoSitKbn`: route `params.refererType` or empty string.
- `iriSyaUktHenKkuMlKboFlg`: selected `mailSousinYohi` or `"0"`.
- `scnHttKboBsyJho`: nested object holding truthy selected `scnHttBsyCd`, `scnHttDay` formatted `YYYYMMDD`, `scnHttJktCd`, `scnHttDayNm`, `scnHttJktNm`.
- `httKboBsyJho`: initialized empty object in this date workflow.
- `kdkKbn`: selected auto-unlock setting for eligible digital-key methods; `"9"` for a digital-key target with other method; otherwise empty string.
- `iriSyaMlAdr`: selected email only when mail option equals `"1"` and email exists; otherwise empty string.

Conditional fields: `angMailAddr` and `nmtId` copied from detail when truthy; `frCmntTxt` from selected delivery request text; `digitalKeyFlg` from separately fetched digital-key state. If either notification parameter exists, `uktHenSniRiyCd = (notifCh ? notifCh.padStart(2,"0") : "") + "-" + (notifType || "")`.

For `nmtJho.nrkSrkFlg === "1"`, identity is copied from detail: `sendSei -> iriSyaSei`, `sendMei -> iriSyaNm`, `sendTel -> iriSyaTel`, `dstZipCd`, `dstAddress1..4`, `dstMachiazaCd`, `dstBanchiNo`, `dstGouNo`. The address1..4 assignments are guarded by truthiness of **dstZipCd** in the actual client, not each individual address field.

For `nrkSrkFlg === "0"`, form mappings are `simeiSei -> iriSyaSei`, `simeiNm -> iriSyaNm`, `tel -> iriSyaTel`, `yuubinBango -> dstZipCd`, `todouHuken -> dstAddress1`; `dstAddress2` concatenates `sikukunCyousou + ooziTuusyou + ziCyoumei`; `dstAddress3` concatenates nonempty `bannTi + "番地"` and `number + "号"`; `heyaNumber -> dstAddress4`, `cazCd -> dstMachiazaCd`, `bannTi -> dstBanchiNo`, `number -> dstGouNo`. Most assignments are conditional on truthy values. Guest address state is resolved separately from postcode and validated against the entered postcode. The detail response alone therefore does not provide a complete guest submission request.

The form removes whitespace from telephone and line breaks from delivery-request text before saving. On successful submission callback it saves display data and navigates to completion. It marks `repeatSubmit` before dispatch, resetting on error; a CLI must not interpret a timeout as permission to blindly retry a write.

## CLI feasibility and limits

A read-only slot-extraction CLI **can be implemented now** against saved detail JSON: unwrap `result`, expose identity, explicit eligibility flag, receiving methods, date fields and per-date windows, and preserve all availability/default/previous flags. An empty/missing list must produce no options, never invented slots. A conservative selectable list should require both date and time availability to equal `"1"`; report unknown/missing flags separately because the UI only explicitly disables `"0"`.

This proves extraction logic from the source, not working browser-free retrieval. Live response shape, session/CSRF requirements, backend validation, code/date formats, and current slot expiry remain unverified. Normal slot enumeration does not require My Calendar or digital-key API calls; reproducing all method-specific behavior and submission does. A read-only CLI should make its method dependencies visible and avoid claiming a time is user-selectable when the date/time controls would be hidden. No sample detail response or parcel query was available for runtime verification.
