# Browser client protocol notes

Static analysis of downloaded artifacts only, 2026-10-23. No network calls or shipment queries performed for these notes. Offsets below are zero-based Unicode character offsets in the unmodified minified files (ASCII source makes these byte offsets for the quoted regions).

## Requests

API base is `https://member.kms.kuronekoyamato.co.jp/api/`; real API mode is enabled (`6.bfe34573.chunk.js`, offset 29261). Both operations use POST. Endpoint wrappers appear in `30.246d78de.chunk.js` at 16396 (`getParcelInfo`) and 23080 (`getParcelDetailInfo`).

Search screen constructs:

```json
{"myNmtJho":{"nmtJhoLst":[{"okjNo":"TRACKING_NUMBER","uktHasKbn":"01","kroMchFlg":"0"}]}}
```

Evidence: `30.246d78de.chunk.js`, offset 168222 region. Hyphens are removed before transport. The UI calls this with one number at a time and accumulates at most ten results locally; an array in the wire format alone does not establish supported batch sizes. The callback consumes `response.data.result.nmtJhoLst` and treats an absent/empty list as no match (offset 168350 region; thunk at 31569).

Detail screen constructs:

```json
{"nmtJho":{"okjNo":"TRACKING_NUMBER","uktHasKbn":"01"}}
```

Evidence: `28.9cc36d32.chunk.js`, offset 185526. `okjNo` comes from URL/state `pno`, `uktHasKbn` from URL/state or empty string. Optional URL `enc` becomes `nmtJho.tucYouNisKey`. The normal detail screen ID is `NRCWBRP0610`, mapped to `/parcel/detail` in `6.bfe34573.chunk.js`, offset 48500 region. Search ID is `NRCWBRP0200`, mapped to `/parcel/search` at 48065 region.

Special transfer handling can issue a second detail call with the same payload fields plus a replacement `okjNo` from `result.nmtJho.hmdkDpInfo.hmdkOkjNo`, `hyjKmkSgyKbn` (`"02"` if result.kroMchFlg is `"1"`, else `"01"`), and `hmdkKbn:"02"` (`28.9cc36d32.chunk.js`, offset 192000 region). Date selection also retrieves details using `{nmtJho:{okjNo,nmtId,amzFlg: value||null,skyKkkCdHjn,skyKkkCdEdbHjn}}` from already loaded parcel state (`24.cd715c91.chunk.js`, offset 241250). These are distinct call sites, not evidence that every field is mandatory in the basic detail request.

## Shared metadata, headers, and device code

`30.246d78de.chunk.js`, offsets 12853–15380 contain the complete shared client. It sets `withCredentials:true`; timeout 60000 ms and retry count 0 come from `6.bfe34573.chunk.js`, offset 6764 region.

Unless query `X-NEKO-TRACE` already exists, the interceptor adds:

- Headers `X-SYSTEM-ID:NRC`, `X-PG_ID:SCREEN_ID`, and `X-PG-ID:SCREEN_ID`.
- Query `X-NEKO-TRACE`: fresh UUID and `X-NEKO-DEVICE`: UUID persisted under localStorage `deviceId` (key evidence in `6.bfe34573.chunk.js`, offset 14632).
- JSON `ktuJho:{iriTs,tnmSbtCd}`. Timestamp format is `YYYY-MM-DDTHH:mm:ss.SSSZ`, with explicit numeric UTC offset.
- If cookie `token` exists, header `Authorization:Bearer TOKEN` and `ktuJho.kroId` from cookie `web_service_id` (cookie names at `6.bfe34573.chunk.js`, offset 22252).

An explicit query `tnmSbtCd` overrides automatic detection; it also remains a query parameter. Module 153 in `6.bfe34573.chunk.js`, offset 3028, resolves device type exactly:

```js
function mobile() {
  const ua = navigator.userAgent.toLowerCase();
  return ua.includes('iphone;') || ua.includes('ipod') ||
    (ua.includes('android') && ua.includes('mobile'));
}
// officialApp means /kuronekoyamatoofficialapp/.test(lowercaseUA)
return officialApp ? '4' : mobile() ? '3' : '1';
```

The official-app flag definition is in `6.bfe34573.chunk.js`, offset 6950 region. For a normal desktop client use string `"1"`.

Axios defaults are `Accept: application/json, text/plain, */*`, JSON serialization and `Content-Type:application/json;charset=utf-8`, cookie `XSRF-TOKEN` and header `X-XSRF-TOKEN` (`0.43ec7882.chunk.js`, offsets 3900–4400). This proves client support, not a server requirement for CSRF or any particular cookie.

## Initialization and response handling

No mandatory guest login/session-init operation was observed before the search screen's `getParcelInfo` call. The shared interceptor initializes only local device identity. The browser may already have cookies from initial page loading; these artifacts cannot establish which cookies the backend requires. Token absence does not prevent construction or dispatch of either request. A cookie-preserving initial public-page GET is a reasonable experiment, not a proven protocol requirement.

The detail screen first invokes the detail thunk, then its callback invokes the member `checkStatus` thunk to obtain login information (`28.9cc36d32.chunk.js`, offsets 185850 and 191700 regions). Therefore this call site does not show `checkStatus` as a prerequisite for the first detail call. Endpoint wrapper `/member/v1/checkStatus` follows the search wrapper in the shared API module (30 chunk offset 16550 region).

Success handling returns raw Axios response; no application-level success-code check exists in the interceptor. Search thunk unwraps `.data.result`. Detail thunk passes `.data` (`30.246d78de.chunk.js`, offset 137177). The detail UI reads `{result,timestamp}` where `result` includes `nmtJho`, `nmtHttJkyLst`, `henKahHntKkaJho`, `httKboBsyJho`, `uktBsyHenRrkJhoLst` (`28.9cc36d32.chunk.js`, offsets 185850–188000). These are observed consumers, not a complete response schema.

On Axios errors (`30.246d78de.chunk.js`, offset 14500 region):

- Query `CUSTOM-ERROR` suppresses normal handling and rejects null.
- An HTTP status other than 400 maps `response.data.errors || []` entries by `.code` into messages, saves them in sessionStorage, redirects to the common error page, and rejects null.
- HTTP 400, or no HTTP response, passes `response.data.errors` (possibly undefined) to the common error transformer and rejects the transformed value.
- Non-Axios errors reject unchanged.

A transport HTTP 200 is thus insufficient evidence of a meaningful parcel result; callers must check the actual response structure. Backend error schemas and status semantics remain unverified.

## Tracking-number validation

The composed UI validator requires a value, numeric characters, length 11 or 12, then `isOkjNo` (`30.246d78de.chunk.js`, offset 133267 region). `isOkjNo` compares `Number(all-but-last-digit) % 7 === Number(last-digit)` (offset 126981). Duplicate numbers already in the local result list raise `NRCRP023FEM` (offset 168087). The low-level checksum helper accepts empty values so it must be combined with the required validator.

## Available delivery slots

`result.scnHttKboDayJhoLst[]` contains day entries with `scnHttDay`, `scnHttDayNm`, `scnHttDayHttKnoFlg`, and nested `scnHttKboJktJhoLst[]`. Time entries include `scnHttJktNm`, `scnHttJktHttKnoFlg`, and `scnHttZkntDftStkFlg`. The UI disables a day exactly when its `scnHttDayHttKnoFlg === "0"`, disables a time exactly when `scnHttJktHttKnoFlg === "0"`, and picks the default time when `scnHttZkntDftStkFlg === "1"`. Evidence: `24.cd715c91.chunk.js`, offsets 250131, 261405, 264159. Preserve the backend-provided codes and labels rather than inferring slots from public service hours.
