# Read-only Yamato CLI

[![CI](https://github.com/raitoxlol/yamato-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/raitoxlol/yamato-cli/actions/workflows/ci.yml)

Experimental Python client for the public Yamato parcel search API, derived from Yamato’s public frontend JavaScript; see [protocol notes](https://github.com/raitoxlol/yamato-cli/blob/main/docs/protocol-notes.md). It uses HTTP directly through `httpx`, keeps cookies within a client session, and has no browser dependency.

## Install

Requires Python 3.10 or newer.

```sh
pipx install yamato-cli
```

Or with pip:

```sh
python -m pip install yamato-cli
```

```sh
yamato --help
yamato track YOUR_TRACKING_NUMBER
yamato probe
yamato detail YOUR_TRACKING_NUMBER
yamato slots YOUR_TRACKING_NUMBER
```

For a local checkout:

```sh
git clone https://github.com/raitoxlol/yamato-cli.git
cd yamato-cli
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Supply only tracking numbers you are authorized to access. `track` accepts 11 or 12 ASCII digits, or groups separated by hyphens such as `dddd-dddd-dddd`. It checks the final digit against the preceding digits modulo 7 before making a request. Output is the complete JSON response on stdout. A failure exits with status 2 and prints a JSON error to stderr, retaining the HTTP status and server response when available. Argument syntax errors use argparse's standard text error output.

`probe` sends `myNmtJho.nmtJhoLst: []`. It never substitutes a parcel number. An HTTP 400 validation response is an expected useful probe outcome, and remains a failure exit status rather than being presented as successful parcel tracking. A live empty-list probe returned HTTP 400 with code `CMCM004BEM` on 2026-10-23; evidence is in `docs/evidence/live-empty-search.json`. This proves that the server received and validated that request. The CLI probe reproduced HTTP 400 validation.

Live CLI checks on 2026-10-23 used the all-zero dummy `000000000000`. `track` returned HTTP 200 with a special-product record, which does not establish that a shipment exists. `detail` returned HTTP 200 and seven date entries, while the overall date-change eligibility flag was `"0"` and the response directed the recipient to telephone support. `slots` preserved the seven raw dates and correctly reported `eligible_for_date_change: false`. Evidence is in `docs/evidence/cli-zero-track.json`, `cli-zero-detail.json`, and `cli-zero-slots.json`. Neither a genuine shipment response nor a definitive not-found response has been verified.

The client sends the current screen metadata, a new trace UUID per request, a device UUID stable for the life of the client, and a UTC millisecond timestamp. Existing session token and XSRF cookies are forwarded as headers if present. No account login or durable cookie store is implemented. The default timeout is 20 seconds per HTTP operation; change it with `yamato --timeout 30 probe`. Redirects and automatic retries are disabled.

`detail` returns the raw detail response. `slots` extracts only the server-returned date/time and receiving-method lists, parcel identity and the raw date-change eligibility flag. Missing lists produce empty lists. `eligible_for_date_change` is true only when the overall server eligibility flag equals `"1"`; available-looking date/time lists can also appear for an ineligible parcel. Both commands remain unverified against a user-owned real parcel. Availability flags are not interpreted as an accepted delivery change. Search accepts at most 100 numbers. The modulo-7 check comes from frontend `isOkjNo`, chunk 30 offset 126981.

There are no redelivery, cancellation, registration, or other delivery-change commands. API POSTs are restricted to read-only `receive_parcel/v1/getParcelInfo` and `receive_parcel/v1/getParcelDetailInfo`. No user-owned shipment has been queried during implementation.

Offline tests use `httpx.MockTransport` and do not contact Yamato:

```sh
python -m unittest discover -s tests -v
```

## License

[MIT License](https://github.com/raitoxlol/yamato-cli/blob/main/LICENSE). Copyright (c) 2026 wright williams.
