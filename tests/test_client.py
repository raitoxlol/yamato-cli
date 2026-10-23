"""Offline protocol checks. All shipment identifiers stay inside MockTransport."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from yamato_cli import __main__
from yamato_cli.client import API_BASE, SEARCH_PATH, YamatoClient, YamatoError


class ClientTests(unittest.TestCase):
    def client(self, handler):
        session = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(session.close)
        return YamatoClient(client=session)

    def test_success_posts_only_search_and_normalizes_numbers(self):
        requests = []
        result = {"result": {"parcelInfoList": [{"okjNo": "123456789013"}]}}

        def handler(request):
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url).split("?")[0], API_BASE + SEARCH_PATH)
            payload = json.loads(request.content)
            self.assertEqual(payload["myNmtJho"]["nmtJhoLst"], [
                {"okjNo": "123456789013", "uktHasKbn": "01", "kroMchFlg": "0"},
                {"okjNo": "12345678903", "uktHasKbn": "01", "kroMchFlg": "0"},
            ])
            self.assertEqual(request.headers["X-SYSTEM-ID"], "NRC")
            self.assertTrue(request.url.params["X-NEKO-DEVICE"])
            self.assertTrue(request.url.params["X-NEKO-TRACE"])
            return httpx.Response(200, json=result)

        self.assertEqual(self.client(handler).track(["1234-5678-9013", "12345678903"]), result)
        self.assertEqual(len(requests), 1)

    def test_probe_preserves_real_validation_error(self):
        body = {"errors": [{"field": "myNmtJho.nmtJhoLst", "code": "CMCM004BEM",
                            "message": "1桁から100桁までの値を指定してください。"}]}

        def handler(request):
            self.assertEqual(json.loads(request.content)["myNmtJho"]["nmtJhoLst"], [])
            return httpx.Response(400, json=body)

        with self.assertRaises(YamatoError) as caught:
            self.client(handler).probe()
        self.assertEqual(caught.exception.details["kind"], "http")
        self.assertEqual(caught.exception.details["http_status"], 400)
        self.assertEqual(caught.exception.details["response"], body)

    def test_application_error_at_http_200_is_failure(self):
        body = {"errors": [{"code": "BLOCKED", "message": "Denied"}], "result": None}
        with self.assertRaises(YamatoError) as caught:
            self.client(lambda _: httpx.Response(200, json=body)).probe()
        self.assertEqual(caught.exception.details["kind"], "application")
        self.assertEqual(caught.exception.details["response"], body)

    def test_html_and_unexpected_json_are_not_success(self):
        for response in [httpx.Response(200, text="<html>blocked</html>"),
                         httpx.Response(200, json=[]), httpx.Response(200, json={})]:
            with self.subTest(response=response.content):
                with self.assertRaises(YamatoError) as caught:
                    self.client(lambda _, response=response: response).probe()
                self.assertEqual(caught.exception.details["kind"], "protocol")

    def test_http_block_preserves_html(self):
        with self.assertRaises(YamatoError) as caught:
            self.client(lambda _: httpx.Response(403, text="<html>Access denied</html>")).probe()
        self.assertEqual(caught.exception.details["http_status"], 403)
        self.assertEqual(caught.exception.details["response"], "<html>Access denied</html>")

    def test_timeout_is_reported_and_never_retried(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("timed out", request=request)

        with self.assertRaises(YamatoError) as caught:
            self.client(handler).probe()
        self.assertEqual(caught.exception.details["kind"], "transport")
        self.assertEqual(caught.exception.details["exception"], "ReadTimeout")
        self.assertEqual(len(calls), 1)

    def test_invalid_tracking_numbers_never_reach_network(self):
        def forbidden(_):
            self.fail("Invalid input reached the network")

        client = self.client(forbidden)
        for numbers in [[], [""], ["123"], ["１２３４５６７８９０１２"],
                        ["123456789014"], ["1234 5678 9013"], ["123456789013", "bad"]]:
            with self.subTest(numbers=numbers):
                with self.assertRaises(YamatoError) as caught:
                    client.track(numbers)
                self.assertEqual(caught.exception.details["kind"], "validation")

    def test_invalid_timeout_rejected(self):
        for timeout in [0, -1, float("inf"), float("nan")]:
            with self.subTest(timeout=timeout), self.assertRaises(YamatoError):
                YamatoClient(timeout=timeout)

    def test_injected_session_stays_open(self):
        client = self.client(lambda _: httpx.Response(200, json={"result": {}}))
        client.close()
        self.assertFalse(client.client.is_closed)

    def test_detail_posts_read_only_endpoint(self):
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/api/receive_parcel/v1/getParcelDetailInfo")
            self.assertEqual(request.headers["X-PG-ID"], "NRCWBRP0610")
            self.assertEqual(json.loads(request.content)["nmtJho"],
                             {"okjNo": "123456789013", "uktHasKbn": "01"})
            return httpx.Response(200, json={"result": {"nmtJho": {"okjNo": "123456789013"}}})
        self.assertIn("result", self.client(handler).detail("1234-5678-9013"))

    def test_slots_preserves_server_options_and_flags_without_writes(self):
        days = [{"scnHttKboDay": "20261024", "availability": "0"}]
        times = [{"timeCode": "0812", "availability": "1"}]
        requests = []

        def handler(request):
            requests.append(request)
            self.assertTrue(request.url.path.endswith("getParcelDetailInfo"))
            return httpx.Response(200, json={"result": {
                "henKahHntKkaJho": {"jtkNaiUktHenKahFlg": "0"},
                "scnHttKboDayJhoLst": days, "scnHttKboBsyJhoLst": times,
            }})

        slots = self.client(handler).slots("123456789013")
        self.assertEqual(slots["date_change_eligibility"], "0")
        self.assertEqual(slots["scnHttKboDayJhoLst"], days)
        self.assertEqual(slots["scnHttKboBsyJhoLst"], times)
        self.assertEqual(len(requests), 1)

    def test_slots_does_not_invent_missing_options(self):
        slots = self.client(lambda _: httpx.Response(200, json={"result": {}})).slots("123456789013")
        self.assertEqual(slots["scnHttKboDayJhoLst"], [])
        self.assertEqual(slots["scnHttKboBsyJhoLst"], [])
        self.assertIsNone(slots["date_change_eligibility"])
        self.assertFalse(slots["eligible_for_date_change"])

    def test_live_zero_fixture_does_not_make_ineligible_slots_selectable(self):
        fixture = Path(__file__).parent / "fixtures" / "zero-detail.json"
        body = json.loads(fixture.read_text())
        slots = self.client(lambda _: httpx.Response(200, json=body)).slots("000000000000")
        self.assertEqual(slots["date_change_eligibility"], "0")
        self.assertFalse(slots["eligible_for_date_change"])
        self.assertEqual(slots["henKahHntKkaJho"], body["result"]["henKahHntKkaJho"])
        self.assertEqual(slots["scnHttKboDayJhoLst"], body["result"]["scnHttKboDayJhoLst"])
        self.assertTrue(all(day["scnHttDayHttKnoFlg"] == "1"
                            for day in slots["scnHttKboDayJhoLst"]))

    def test_more_than_100_numbers_rejected_before_network(self):
        def forbidden(_):
            self.fail("Oversized request reached the network")
        with self.assertRaises(YamatoError) as caught:
            self.client(forbidden).track(["123456789013"] * 101)
        self.assertEqual(caught.exception.details["kind"], "validation")

    def test_slots_rejects_non_object_detail_result(self):
        for result in [None, [], "invalid"]:
            with self.subTest(result=result), self.assertRaises(YamatoError) as caught:
                self.client(lambda _: httpx.Response(200, json={"result": result})).slots("123456789013")
            self.assertEqual(caught.exception.details["kind"], "protocol")

    def test_detail_and_slots_validate_before_network(self):
        def forbidden(_):
            self.fail("Invalid input reached the network")
        client = self.client(forbidden)
        for operation in [client.detail, client.slots]:
            with self.assertRaises(YamatoError):
                operation("bad")

    def test_cli_failure_is_json_on_stderr_and_exit_two(self):
        failure = YamatoError("http", "Rejected", http_status=400, response={"errors": ["bad"]})
        with patch.object(__main__, "YamatoClient") as factory:
            factory.return_value.__enter__.return_value.probe.side_effect = failure
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = __main__.main(["probe"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue()), {"error": failure.details})


if __name__ == "__main__":
    unittest.main()
