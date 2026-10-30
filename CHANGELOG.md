# Changelog

## 0.1.0 — 2026-10-30

First release of the experimental read-only Yamato parcel CLI.

- `yamato` command with `track`, `detail`, `slots`, and `probe`
- Browser-free `httpx` client limited to the public read-only parcel search and detail endpoints
- Offline `unittest` suite; no delivery-change, cancellation, or registration commands
- MIT license and package metadata for a PyPI install

This release is unverified against a user-owned real parcel. The all-zero dummy number and the empty-list `probe` do not establish that shipment lookup works.
